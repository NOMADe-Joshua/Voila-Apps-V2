"""Reprocess_Uploads against a simulated NOMAD API (no network)."""

import copy

import pytest

from perotf_utils.config import ENTRY_TYPES

URL = "https://oasis.test/api/v1"
EVAPORATION = ENTRY_TYPES["evaporation"]
LAMINATION = ENTRY_TYPES["lamination"]


def archive(entry_id, upload_id, entry_type, mainfile, data, published=False):
    return {
        "entry_id": entry_id,
        "upload_id": upload_id,
        "archive": {
            "metadata": {
                "entry_type": entry_type,
                "mainfile": mainfile,
                "upload_name": f"Upload {upload_id}",
                "published": published,
            },
            "data": data,
        },
    }


def experiment(upload_id, created_ids):
    refs = [f"../uploads/{upload_id}/archive/{entry_id}#data" for entry_id in created_ids]
    return archive(
        f"exp-{upload_id}",
        upload_id,
        ENTRY_TYPES["experiment"],
        "batch.xlsx",
        {"processed_archive": refs},
    )


def evaporation(entry_id, upload_id, mainfile, sources):
    data = {"name": f"evaporation {entry_id}", "co_evaporation": False}
    if sources:
        data["perovskite_evaporation"] = [{"thickness": 100.0}]
    return archive(entry_id, upload_id, EVAPORATION, mainfile, data)


class FakeResponse:
    def __init__(self, body=None, status=200):
        self._body = body if body is not None else {}
        self.status_code = status
        self.ok = status < 400
        self.text = str(self._body)

    def json(self):
        return self._body


class FakeNomad:
    """Archive query, upload state, raw file delete and reprocess, like NOMAD's v1 API."""

    def __init__(self, archives, recreate=True, running_polls=1):
        self.archives = archives
        self.deleted_archives = []
        self.recreate = recreate  # whether reprocessing writes deleted files again (with sources)
        self.running_polls = running_polls  # polls reporting process_running after each action
        self._running = 0
        self.calls = []
        self.fail_delete = False

    def _matches(self, item, query):
        metadata = item["archive"]["metadata"]
        if "entry_type" in query and metadata["entry_type"] != query["entry_type"]:
            return False
        if "entry_type:any" in query and metadata["entry_type"] not in query["entry_type:any"]:
            return False
        if "published" in query and metadata["published"] != query["published"]:
            return False
        return "upload_id" not in query or item["upload_id"] == query["upload_id"]

    def post(self, url, headers=None, json=None, timeout=None):
        if url.endswith("/entries/archive/query"):
            self.calls.append(("query", json["query"]))
            data = [item for item in self.archives if self._matches(item, json["query"])]
            return FakeResponse({"data": copy.deepcopy(data), "pagination": {}})
        if url.endswith("/action/process"):
            self.calls.append(("process", url.split("/uploads/")[1].split("/")[0]))
            if self.recreate:
                for item in self.deleted_archives:
                    item["archive"]["data"]["perovskite_evaporation"] = [{"thickness": 1.0}]
                    self.archives.append(item)
            self.deleted_archives = []
            self._running = self.running_polls
            return FakeResponse({"data": {}})
        raise AssertionError(url)

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("state", url.rsplit("/", 1)[1]))
        running = self._running > 0
        self._running = max(0, self._running - 1)
        return FakeResponse(
            {
                "data": {
                    "process_running": running,
                    "process_status": "RUNNING" if running else "SUCCESS",
                    "last_status_message": "Process done" if not running else "",
                }
            }
        )

    def delete(self, url, headers=None, params=None, timeout=None):
        path = url.split("/raw/", 1)[1]
        self.calls.append(("delete", path, params))
        if self.fail_delete:
            return FakeResponse({"detail": "The upload is currently blocked"}, status=400)
        for item in list(self.archives):
            if item["archive"]["metadata"]["mainfile"] == path:
                self.archives.remove(item)
                self.deleted_archives.append(item)
        self._running = self.running_polls
        return FakeResponse({"data": {}})


@pytest.fixture
def nomad(mods, monkeypatch):
    archives = [
        experiment("U1", ["e1", "e2", "lam1"]),
        evaporation("e1", "U1", "2_0_evaporation_MAPbI3.archive.json", sources=False),
        evaporation("e2", "U1", "3_0_evaporation_C60.archive.json", sources=True),
        # made by hand in the ELN: not in processed_archive, must never be touched
        evaporation("manual", "U1", "my_evaporation.archive.json", sources=False),
        archive("lam1", "U1", LAMINATION, "5_0_lamination.archive.json", {"name": "Lamination"}),
        experiment("U2", ["e3"]),
        evaporation("e3", "U2", "1_0_evaporation_PbI2.archive.json", sources=False),
    ]
    fake = FakeNomad(archives)
    monkeypatch.setattr(mods["data_manager"], "requests", fake)
    return fake


def no_sleep(_seconds):
    pass


def test_search_finds_only_parser_created_evaporations_without_sources(mods, nomad):
    result = mods["data_manager"].find_plans(URL, "token", [EVAPORATION], "admin")
    files = {plan.upload_id: plan.files for plan in result.plans}
    assert files == {
        "U1": ["2_0_evaporation_MAPbI3.archive.json"],
        "U2": ["1_0_evaporation_PbI2.archive.json"],
    }
    assert result.skipped_not_from_parser == 1
    assert result.skipped_with_sources == 1


def test_search_can_include_entries_with_sources_and_other_types(mods, nomad):
    result = mods["data_manager"].find_plans(
        URL, "token", [EVAPORATION, LAMINATION], "admin", only_without_sources=False
    )
    (u1,) = [plan for plan in result.plans if plan.upload_id == "U1"]
    assert u1.files == [
        "2_0_evaporation_MAPbI3.archive.json",
        "3_0_evaporation_C60.archive.json",
        "5_0_lamination.archive.json",
    ]
    assert all(query.get("published") is False for kind, query in nomad.calls if kind == "query")


def test_repair_deletes_without_processing_then_reprocesses_once(mods, nomad):
    dm = mods["data_manager"]
    (plan,) = [
        p for p in dm.find_plans(URL, "token", [EVAPORATION], "admin").plans if p.upload_id == "U2"
    ]
    nomad.calls.clear()

    result = dm.repair_upload(URL, "token", plan, "admin", sleep=no_sleep)

    actions = [call for call in nomad.calls if call[0] in ("delete", "process")]
    assert actions == [
        ("delete", "1_0_evaporation_PbI2.archive.json", {"trigger_processing": "false"}),
        ("process", "U2"),
    ]
    assert result.ok
    assert result.deleted == ["1_0_evaporation_PbI2.archive.json"]
    assert result.missing == [] and result.without_sources == []


def test_repair_reports_files_the_parser_did_not_write_again(mods, nomad):
    dm = mods["data_manager"]
    nomad.recreate = False
    (plan,) = [
        p for p in dm.find_plans(URL, "token", [EVAPORATION], "admin").plans if p.upload_id == "U2"
    ]

    result = dm.repair_upload(URL, "token", plan, "admin", sleep=no_sleep)

    assert not result.ok
    assert result.missing == ["1_0_evaporation_PbI2.archive.json"]


def test_a_failed_delete_is_reported_and_nothing_is_reprocessed(mods, nomad):
    dm = mods["data_manager"]
    nomad.fail_delete = True
    (plan,) = [
        p for p in dm.find_plans(URL, "token", [EVAPORATION], "admin").plans if p.upload_id == "U2"
    ]

    result = dm.repair_upload(URL, "token", plan, "admin", sleep=no_sleep)

    assert "currently blocked" in result.error
    assert not any(call[0] == "process" for call in nomad.calls)


def test_waiting_gives_up_after_the_timeout(mods, nomad):
    dm = mods["data_manager"]
    nomad.running_polls = 10**6
    nomad._running = 10**6
    now = [0.0]

    def clock():
        return now[0]

    def sleep(seconds):
        now[0] += seconds

    with pytest.raises(TimeoutError):
        dm.wait_until_idle(URL, "token", "U1", timeout_s=10, poll_s=3, sleep=sleep, clock=clock)


def test_app_constructs_offline(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].ReprocessUploadsApp()
    assert app.get_dashboard() is not None
    assert app.search_button.disabled  # no search before signing in
    assert [label for label, check in app.type_checks.items() if check.value] == [
        mods["app"].DEFAULT_TYPE
    ]
