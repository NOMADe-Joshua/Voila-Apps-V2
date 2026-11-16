"""Backups and change logs kept in the upload of the entry an app changes.

An app that writes to NOMAD (Entry_Auditor's corrections, MPPT_Analysis's fit results) first
stores the entry's original file, and afterwards one record of what it changed, in a folder of
the entry's OWN upload, so they have exactly the access rights of the data they hold (never
next to the app, where every user of the apps could read other people's private entries).

Every file name there starts with a dot: NOMAD never parses such a file
(nomad.parsing.parsers.match_parser skips names starting with "." or "~"), so a backup can
never become a second entry; the .bak/.log endings are a second guard. Backups and logs are
written without overwriting anything and without reprocessing the upload.
"""

import json
import logging
import posixpath
import re
from datetime import datetime

from perotf_utils.api_calls import (
    download_raw_file,
    list_raw_folder,
    put_raw_file,
    wait_for_upload,
)

logger = logging.getLogger(__name__)

ARCHIVE_SUFFIXES = (".archive.json", ".archive.yaml", ".archive.yml")
"""Only an entry whose own file is a NOMAD archive file can be changed by an app; for any
other mainfile (an Excel sheet, a measured data file) NOMAD derives the values while parsing."""


def is_archive_file(mainfile: str) -> bool:
    return mainfile.endswith(ARCHIVE_SUFFIXES)


LOG_NAME = re.compile(r"^\.(?P<stamp>\d{8}T\d{6}_\d{6})_(?P<kind>[a-z_]+)\.log$")


def change_stamp() -> str:
    """Time stamp of one write run, shared by its backups and its logs."""
    return datetime.now().strftime("%Y%m%dT%H%M%S_%f")


def backup_location(folder: str, mainfile: str, stamp: str) -> tuple[str, str]:
    """(folder, file name) of the backup of `mainfile` inside `folder` of the entry's upload:
    <folder>/<folder of mainfile>/.<file name>.<stamp>.bak"""
    target = posixpath.join(folder, posixpath.dirname(mainfile)).rstrip("/")
    return target, f".{posixpath.basename(mainfile)}.{stamp}.bak"


def save_backup(
    url: str, token: str, upload_id: str, folder: str, mainfile: str, original_text: str, stamp
) -> str:
    """Store the original file text in the entry's own upload and return its path there.
    Never overwrites a file and does not reprocess the upload. Raises when the backup cannot
    be stored, in which case the caller must not change the entry."""
    target, name = backup_location(folder, mainfile, stamp)
    put_raw_file(
        url,
        token,
        upload_id,
        target,
        name,
        original_text.encode("utf-8"),
        "text/plain",
        overwrite=False,
        trigger_processing=False,
    )
    # A NOMAD version without trigger_processing reprocesses anyway: let it finish, so the
    # change itself does not run into a busy upload.
    if wait_for_upload(url, token, upload_id) is None:
        raise TimeoutError(f"upload {upload_id} still processing after the backup")
    return f"{target}/{name}"


def write_change_log(
    url: str, token: str, upload_id: str, folder: str, stamp: str, record: dict, kind: str
) -> str:
    """Store one run's record for this upload (JSON) as <folder>/.<stamp>_<kind>.log."""
    name = f".{stamp}_{kind}.log"
    put_raw_file(
        url,
        token,
        upload_id,
        folder,
        name,
        json.dumps(record, indent=1, ensure_ascii=False).encode("utf-8"),
        "text/plain",
        overwrite=False,
        trigger_processing=False,
    )
    return f"{folder}/{name}"


def read_change_logs(
    url: str, token: str, upload_ids: list[str], folder: str, kind: str
) -> list[dict]:
    """Every record of this kind stored in these uploads (one per upload and run), newest
    first, each with its upload_id. An upload or log that cannot be read is skipped."""
    records = []
    for upload_id in upload_ids:
        try:
            names = list_raw_folder(url, token, upload_id, folder)
        except Exception:  # noqa: BLE001
            logger.warning("Could not list %s of %s", folder, upload_id, exc_info=True)
            continue
        for name in names:
            match = LOG_NAME.match(name)
            if not match or match.group("kind") != kind:
                continue
            try:
                content = download_raw_file(url, token, upload_id, f"{folder}/{name}")
                record = json.loads(content.decode("utf-8"))
            except Exception:  # noqa: BLE001
                logger.warning("Could not read %s of %s", name, upload_id, exc_info=True)
                continue
            if isinstance(record, dict):
                records.append({**record, "upload_id": upload_id})
    return sorted(records, key=lambda r: str(r.get("time", "")), reverse=True)
