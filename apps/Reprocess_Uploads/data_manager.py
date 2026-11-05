"""NOMAD side of Reprocess_Uploads, without widgets.

nomad_perotf's experiment parser writes one process entry per Excel column group and never
overwrites an entry it already created. To let a fixed parser write such entries again, this
module deletes their files from the upload and reprocesses the upload, which reparses the
experiment Excel and recreates every missing file under its old name (and so its old entry id).

Only entries the experiment entry lists in data.processed_archive are touched: those are
the ones the parser will write again. An entry created by hand in the ELN would be gone for good.

Every function takes the API url (URL_BASE + API_ENDPOINT) and a token.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import requests

from perotf_utils.config import ENTRY_TYPES

logger = logging.getLogger(__name__)

# Label -> entry type of the process entries this app can recreate
PROCESS_TYPES = {
    "Evaporation (incl. Co- and Seq-Evaporation)": ENTRY_TYPES["evaporation"],
    "Lamination": ENTRY_TYPES["lamination"],
    "Spin Coating": ENTRY_TYPES["spin_coating"],
    "Inkjet Printing": ENTRY_TYPES["inkjet_printing"],
}
SOURCE_KEYS = ("organic_evaporation", "inorganic_evaporation", "perovskite_evaporation")
REQUEST_TIMEOUT = 60  # seconds per HTTP request
PAGE_SIZE = 100
_REFERENCED_ENTRY_ID = re.compile(r"/archive/([^/#]+)")


@dataclass
class ProcessEntry:
    entry_id: str
    upload_id: str
    upload_name: str
    mainfile: str
    entry_type: str
    name: str
    has_sources: bool | None  # None for entry types without evaporation sources


@dataclass
class UploadPlan:
    upload_id: str
    upload_name: str
    entries: list[ProcessEntry] = field(default_factory=list)

    @property
    def files(self) -> list[str]:
        return sorted({entry.mainfile for entry in self.entries})


@dataclass
class SearchResult:
    plans: list[UploadPlan]
    skipped_not_from_parser: int  # entries of the chosen types the parser did not create
    skipped_with_sources: int  # evaporation entries left out because they have sources


@dataclass
class RepairResult:
    upload_id: str
    upload_name: str
    deleted: list[str] = field(default_factory=list)
    process_status: str = ""
    status_message: str = ""
    missing: list[str] = field(default_factory=list)  # files the reprocess did not write again
    without_sources: list[str] = field(default_factory=list)  # evaporation still without
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and not self.missing and self.process_status == "SUCCESS"


def _log_info(message):
    logger.info("%s", message)


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _check(response, action):
    if response.ok:
        return
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    raise RuntimeError(f"{action}: HTTP {response.status_code} {detail}")


def has_sources(data: dict) -> bool:
    return any(isinstance(data.get(key), list) and data[key] for key in SOURCE_KEYS)


def query_archives(url, token, query, owner):
    """All entries matching query, as {"entry_id", "upload_id", "archive"} dicts."""
    results, page_after = [], None
    while True:
        pagination = {"page_size": PAGE_SIZE}
        if page_after is not None:
            pagination["page_after_value"] = page_after
        response = requests.post(
            f"{url}/entries/archive/query",
            headers=_headers(token),
            json={
                "owner": owner,
                "query": query,
                "required": {"metadata": "*", "data": "*"},
                "pagination": pagination,
            },
            timeout=REQUEST_TIMEOUT,
        )
        _check(response, "Archive query")
        body = response.json()
        results += body.get("data", [])
        page_after = body.get("pagination", {}).get("next_page_after_value")
        if not page_after or not body.get("data"):
            return results


def parser_entry_ids(url, token, owner, upload_id=None) -> dict[str, set[str]]:
    """upload_id -> ids of the entries the experiment parser created in that upload."""
    query = {"entry_type": ENTRY_TYPES["experiment"], "published": False}
    if upload_id:
        query["upload_id"] = upload_id
    created: dict[str, set[str]] = {}
    for result in query_archives(url, token, query, owner):
        references = result.get("archive", {}).get("data", {}).get("processed_archive") or []
        ids = created.setdefault(result["upload_id"], set())
        for reference in references:
            match = _REFERENCED_ENTRY_ID.search(str(reference))
            if match:
                ids.add(match.group(1))
    return created


def process_entries(url, token, entry_types, owner, upload_id=None) -> list[ProcessEntry]:
    query = {"entry_type:any": list(entry_types), "published": False}
    if upload_id:
        query["upload_id"] = upload_id
    entries = []
    for result in query_archives(url, token, query, owner):
        archive = result.get("archive", {})
        metadata, data = archive.get("metadata", {}), archive.get("data", {})
        entry_type = metadata.get("entry_type", "")
        entries.append(
            ProcessEntry(
                entry_id=result["entry_id"],
                upload_id=result["upload_id"],
                upload_name=metadata.get("upload_name") or result["upload_id"],
                mainfile=metadata.get("mainfile", ""),
                entry_type=entry_type,
                name=data.get("name") or metadata.get("entry_name", ""),
                has_sources=(
                    has_sources(data) if entry_type == ENTRY_TYPES["evaporation"] else None
                ),
            )
        )
    return entries


def find_plans(url, token, entry_types, owner, only_without_sources=True) -> SearchResult:
    """Group the parser-created entries of entry_types by upload. With only_without_sources,
    evaporation entries are only included when they have no source stored."""
    created = parser_entry_ids(url, token, owner)
    plans: dict[str, UploadPlan] = {}
    not_from_parser = with_sources = 0
    for entry in process_entries(url, token, entry_types, owner):
        if entry.entry_id not in created.get(entry.upload_id, set()):
            not_from_parser += 1
            continue
        if only_without_sources and entry.has_sources:
            with_sources += 1
            continue
        plan = plans.setdefault(entry.upload_id, UploadPlan(entry.upload_id, entry.upload_name))
        plan.entries.append(entry)
    ordered = sorted(plans.values(), key=lambda plan: plan.upload_name.lower())
    return SearchResult(ordered, not_from_parser, with_sources)


def upload_state(url, token, upload_id) -> dict:
    response = requests.get(
        f"{url}/uploads/{upload_id}", headers=_headers(token), timeout=REQUEST_TIMEOUT
    )
    _check(response, f"Upload {upload_id}")
    return response.json()["data"]


def wait_until_idle(
    url, token, upload_id, timeout_s, poll_s=3.0, sleep=time.sleep, clock=time.monotonic
) -> dict:
    """Upload data once no process runs on the upload any more."""
    deadline = clock() + timeout_s
    while True:
        state = upload_state(url, token, upload_id)
        if not state.get("process_running"):
            return state
        if clock() >= deadline:
            raise TimeoutError(
                f"Upload {upload_id} still processing after {timeout_s:.0f} s "
                f"({state.get('last_status_message', '')})"
            )
        sleep(poll_s)


def delete_file(url, token, upload_id, path):
    """Delete one raw file without reprocessing the upload (that happens once at the end)."""
    response = requests.delete(
        f"{url}/uploads/{upload_id}/raw/{quote(path)}",
        headers=_headers(token),
        params={"trigger_processing": "false"},
        timeout=REQUEST_TIMEOUT,
    )
    _check(response, f"Delete {path}")


def start_processing(url, token, upload_id):
    response = requests.post(
        f"{url}/uploads/{upload_id}/action/process",
        headers=_headers(token),
        timeout=REQUEST_TIMEOUT,
    )
    _check(response, f"Reprocess {upload_id}")


def repair_upload(
    url,
    token,
    plan: UploadPlan,
    owner,
    timeout_s=900,
    log=_log_info,
    sleep=time.sleep,
    clock=time.monotonic,
) -> RepairResult:
    """Delete the plan's files, reprocess the upload and check what came back."""
    result = RepairResult(plan.upload_id, plan.upload_name)
    try:
        wait_until_idle(url, token, plan.upload_id, timeout_s, sleep=sleep, clock=clock)
        for path in plan.files:
            delete_file(url, token, plan.upload_id, path)
            result.deleted.append(path)
            log(f"deleted {path}")
            # the deletion runs as a short process of its own and blocks the upload meanwhile
            wait_until_idle(url, token, plan.upload_id, timeout_s, sleep=sleep, clock=clock)
        start_processing(url, token, plan.upload_id)
        log("reprocessing ...")
        state = wait_until_idle(url, token, plan.upload_id, timeout_s, sleep=sleep, clock=clock)
        result.process_status = state.get("process_status", "")
        result.status_message = state.get("last_status_message", "")

        types = {entry.entry_type for entry in plan.entries}
        back = {
            entry.mainfile: entry
            for entry in process_entries(url, token, types, owner, upload_id=plan.upload_id)
        }
        result.missing = [path for path in plan.files if path not in back]
        result.without_sources = [
            path for path in plan.files if path in back and back[path].has_sources is False
        ]
    except Exception as exc:  # reported per upload, the next upload still runs
        logger.exception("Repair of upload %s failed", plan.upload_id)
        result.error = str(exc)
    return result
