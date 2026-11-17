"""Samples Dashboard: who uploaded how many samples, and when.

No widgets here. One paginated NOMAD query (perotf_utils.api_calls.query_all) reads every
sample entry together with its upload's name, creation time and main author. The admin
notebook this replaces asked NOMAD once per upload and once per author and needed a local
cache for that.

Attribution overrides credit an upload to someone other than its NOMAD main author (uploads
made from a shared account, for example). They are kept in a CSV file next to the usage log,
in the format of the old notebook's attribution_overrides.csv, and are never written to NOMAD.
"""

import csv
import hashlib
import io
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from perotf_utils.access_token import usage_log_dir
from perotf_utils.api_calls import _resolve_user_names, query_all
from perotf_utils.config import ENTRY_TYPES

logger = logging.getLogger(__name__)

SAMPLE_FIELDS = [
    "entry_id",
    "entry_name",
    "upload_id",
    "upload_name",
    "upload_create_time",
    "main_author",
    "results.eln.lab_ids",
]
SAMPLE_COLUMNS = [
    "entry_id",
    "entry_name",
    "lab_id",
    "upload_id",
    "upload_name",
    "upload_date",
    "author_id",
    "author_name",
]
SCOPE_ADMIN = "admin"
SCOPE_VISIBLE = "visible"

OVERRIDES_FILENAME = "sample_attribution_overrides.csv"
OVERRIDE_COLUMNS = ["upload_id", "author_id", "author_display_name", "override_date"]
OVERRIDES_HEADER = (
    "# NOMAD Sample Attribution Overrides\n"
    "# This file contains manual corrections to sample attributions.\n"
)


# ── Samples from NOMAD ───────────────────────────────────────────────────────


@dataclass
class SampleLoad:
    samples: pd.DataFrame
    scope: str
    """SCOPE_ADMIN: every upload of the Oasis; SCOPE_VISIBLE: only what this account sees."""


def _author(main_author):
    """(user_id, name) of an entry's main_author: a user object on some NOMAD versions, a
    bare user id on others."""
    if isinstance(main_author, dict):
        name = main_author.get("name") or main_author.get("username") or ""
        return str(main_author.get("user_id") or ""), str(name)
    if isinstance(main_author, str):
        return main_author, ""
    return "", ""


def _query(owner):
    return {
        "owner": owner,
        "query": {"entry_type": ENTRY_TYPES["sample"]},
        "required": {"include": SAMPLE_FIELDS},
    }


def load_samples(url, token) -> SampleLoad:
    """Every sample entry, one row each. Asks with owner "admin" first (only NOMAD's admin
    account may) and falls back to what this account can see."""
    scope = SCOPE_ADMIN
    try:
        entries = query_all(url, token, "entries/query", _query("admin"))
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status is None or not 400 <= status < 500:
            raise
        logger.info("Admin query refused (%s); loading the visible samples instead", status)
        scope = SCOPE_VISIBLE
        entries = query_all(url, token, "entries/query", _query("visible"))
    return SampleLoad(samples_frame(entries, url, token), scope)


def samples_frame(entries, url=None, token=None) -> pd.DataFrame:
    """The DataFrame of SAMPLE_COLUMNS from NOMAD's entries/query data. Author ids NOMAD
    returned without a name are looked up (/users) when url and token are given."""
    rows, unnamed = [], set()
    for entry in entries:
        user_id, name = _author(entry.get("main_author"))
        if user_id and not name:
            unnamed.add(user_id)
        lab_ids = ((entry.get("results") or {}).get("eln") or {}).get("lab_ids") or []
        rows.append(
            {
                "entry_id": entry.get("entry_id"),
                "entry_name": entry.get("entry_name") or "",
                "lab_id": lab_ids[0] if lab_ids else "",
                "upload_id": entry.get("upload_id") or "",
                "upload_name": entry.get("upload_name") or "",
                "upload_date": entry.get("upload_create_time"),
                "author_id": user_id,
                "author_name": name,
            }
        )
    names = _resolve_user_names(url, token, unnamed) if unnamed and url and token else {}
    samples = pd.DataFrame(rows, columns=SAMPLE_COLUMNS)
    samples["author_name"] = [
        name or names.get(uid) or uid or "Unknown"
        for uid, name in zip(samples["author_id"], samples["author_name"], strict=True)
    ]
    dates = pd.to_datetime(samples["upload_date"], utc=True, errors="coerce", format="ISO8601")
    samples["upload_date"] = dates.dt.tz_convert(None)
    return samples


# ── Attribution overrides ────────────────────────────────────────────────────


def override_name(override):
    """The name an override credits ('' for none)."""
    if not override:
        return ""
    return str(override.get("author_display_name") or override.get("author_id") or "").strip()


def effective_authors(samples, overrides) -> pd.Series:
    """Per sample: the override's name for its upload, else its NOMAD main author."""
    names = {uid: override_name(o) for uid, o in overrides.items() if override_name(o)}
    return samples["upload_id"].map(names).fillna(samples["author_name"])


def uploads_table(samples, overrides) -> pd.DataFrame:
    """One row per upload: name, date, NOMAD author, number of samples, override."""
    if samples.empty:
        return pd.DataFrame(
            columns=[
                "upload_id",
                "upload_name",
                "upload_date",
                "author_name",
                "samples",
                "override",
            ]
        )
    table = (
        samples.groupby("upload_id", sort=False)
        .agg(
            upload_name=("upload_name", "first"),
            upload_date=("upload_date", "min"),
            author_name=("author_name", "first"),
            samples=("entry_id", "count"),
        )
        .reset_index()
    )
    table["override"] = [override_name(overrides.get(uid)) for uid in table["upload_id"]]
    return table.sort_values("upload_date", ascending=False, na_position="last").reset_index(
        drop=True
    )


def filter_uploads(table, author="", upload_name="", upload_id="", date_from=None, date_to=None):
    """The rows of uploads_table matching every given filter (text filters ignore case; the
    author filter looks at the NOMAD author and the override; dates include both ends)."""
    if table.empty:
        return table
    mask = pd.Series(True, index=table.index)
    if author.strip():
        text = author.strip().lower()
        mask &= table["author_name"].str.lower().str.contains(text, regex=False) | table[
            "override"
        ].str.lower().str.contains(text, regex=False)
    if upload_name.strip():
        mask &= (
            table["upload_name"].str.lower().str.contains(upload_name.strip().lower(), regex=False)
        )
    if upload_id.strip():
        mask &= table["upload_id"].str.lower().str.contains(upload_id.strip().lower(), regex=False)
    days = table["upload_date"].dt.normalize()
    if date_from is not None:
        mask &= days >= pd.Timestamp(date_from)
    if date_to is not None:
        mask &= days <= pd.Timestamp(date_to)
    return table[mask]


def known_authors(samples, overrides) -> list[str]:
    """Names to offer for an override: the ones overrides use first, then all NOMAD authors."""
    used = sorted({override_name(o) for o in overrides.values()} - {""})
    others = sorted(set(samples["author_name"]) - set(used)) if not samples.empty else []
    return used + others


def set_override(overrides, upload_ids, author, today=None) -> dict:
    """A copy of overrides crediting upload_ids to author ('' removes their overrides)."""
    author = (author or "").strip()
    stamp = (today or date.today()).isoformat()
    result = dict(overrides)
    for upload_id in upload_ids:
        if author:
            result[upload_id] = {
                "author_id": author,
                "author_display_name": author,
                "override_date": stamp,
            }
        else:
            result.pop(upload_id, None)
    return result


def changed_uploads(saved, current) -> list[str]:
    return sorted(
        uid
        for uid in set(saved) | set(current)
        if override_name(saved.get(uid)) != override_name(current.get(uid))
    )


def parse_overrides_csv(text) -> dict:
    """Overrides from CSV text (lines starting with # are comments). Reads the old column
    names main_author / main_author_name too."""
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    overrides = {}
    for row in csv.DictReader(lines):
        upload_id = (row.get("upload_id") or "").strip()
        if not upload_id:
            continue
        author_id = (row.get("author_id") or row.get("main_author") or "").strip()
        name = (row.get("author_display_name") or row.get("main_author_name") or author_id).strip()
        if not name:
            continue
        overrides[upload_id] = {
            "author_id": author_id or name,
            "author_display_name": name,
            "override_date": (row.get("override_date") or "").strip(),
        }
    return overrides


def overrides_csv(overrides) -> str:
    """The CSV text of overrides (same format as the old attribution_overrides.csv)."""
    buffer = io.StringIO()
    buffer.write(OVERRIDES_HEADER)
    writer = csv.DictWriter(buffer, fieldnames=OVERRIDE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for upload_id in sorted(overrides):
        override = overrides[upload_id]
        writer.writerow(
            {
                "upload_id": upload_id,
                "author_id": override.get("author_id", ""),
                "author_display_name": override_name(override),
                "override_date": override.get("override_date", ""),
            }
        )
    return buffer.getvalue()


class OverridesChangedError(RuntimeError):
    """The overrides file changed on disk since it was loaded (another admin saved)."""


@dataclass
class OverridesFile:
    path: Path
    overrides: dict = field(default_factory=dict)
    fingerprint: str | None = None
    """sha256 of the file as loaded; None when there was no file."""


def overrides_path() -> Path:
    """Next to the usage log (in the upload under NORTH, gitignored as *.csv)."""
    return usage_log_dir() / OVERRIDES_FILENAME


def _fingerprint(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def read_overrides(path=None) -> OverridesFile:
    path = Path(path) if path else overrides_path()
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return OverridesFile(path)
    return OverridesFile(path, parse_overrides_csv(text), _fingerprint(path))


def save_overrides(loaded: OverridesFile, overrides) -> OverridesFile:
    """Write overrides to loaded.path, keeping the previous file as <name>.bak. Refuses
    (OverridesChangedError) if the file changed since it was loaded."""
    path = loaded.path
    if _fingerprint(path) != loaded.fingerprint:
        raise OverridesChangedError(
            f"{path.name} was changed since it was loaded (by another admin?). Discard your "
            "changes to load it again, then redo them."
        )
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(overrides_csv(overrides), encoding="utf-8")
    os.replace(temporary, path)
    return OverridesFile(path, dict(overrides), _fingerprint(path))
