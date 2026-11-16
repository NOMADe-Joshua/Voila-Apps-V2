"""perotf_utils.upload_backups: backups and change logs in the entry's own upload."""

import json

import pytest

from perotf_utils import upload_backups


@pytest.fixture
def fake_upload(monkeypatch):
    """One upload's raw files, written and read through the patched api_calls functions."""
    files = {}
    puts = []

    def put(url, token, upload_id, folder, filename, content, mime_type, **kwargs):
        path = f"{folder}/{filename}" if folder else filename
        puts.append({"path": path, **kwargs})
        if kwargs.get("overwrite") is False and (upload_id, path) in files:
            raise RuntimeError("exists")
        files[(upload_id, path)] = content

    def listdir(url, token, upload_id, folder):
        prefix = folder + "/"
        return [p[len(prefix) :] for u, p in files if u == upload_id and p.startswith(prefix)]

    monkeypatch.setattr(upload_backups, "put_raw_file", put)
    monkeypatch.setattr(upload_backups, "list_raw_folder", listdir)
    monkeypatch.setattr(
        upload_backups, "download_raw_file", lambda url, token, u, path: files[(u, path)]
    )
    monkeypatch.setattr(upload_backups, "wait_for_upload", lambda *a, **k: "SUCCESS")
    return files, puts


def test_backup_names_start_with_a_dot_so_nomad_never_parses_them():
    folder, name = upload_backups.backup_location("app_backups", "sub/x.archive.json", "S")
    assert (folder, name) == ("app_backups/sub", ".x.archive.json.S.bak")
    assert upload_backups.backup_location("app_backups", "y.archive.json", "S")[0] == "app_backups"


def test_a_backup_never_overwrites_and_never_reprocesses(fake_upload):
    files, puts = fake_upload
    path = upload_backups.save_backup("u", "t", "U1", "b", "x.archive.json", "{}", "S")
    assert path == "b/.x.archive.json.S.bak" and files[("U1", path)] == b"{}"
    assert (puts[0]["overwrite"], puts[0]["trigger_processing"]) == (False, False)
    with pytest.raises(RuntimeError):  # the same backup again is refused, not overwritten
        upload_backups.save_backup("u", "t", "U1", "b", "x.archive.json", "{}", "S")


def test_a_backup_that_cannot_settle_raises(fake_upload, monkeypatch):
    monkeypatch.setattr(upload_backups, "wait_for_upload", lambda *a, **k: None)
    with pytest.raises(TimeoutError):
        upload_backups.save_backup("u", "t", "U1", "b", "x.archive.json", "{}", "S")


def test_logs_are_read_back_per_kind_newest_first(fake_upload):
    files, _ = fake_upload
    stamp_a, stamp_b = "20261101T100000_000001", "20261102T100000_000001"
    upload_backups.write_change_log("u", "t", "U1", "b", stamp_a, {"time": "1"}, "corrections")
    upload_backups.write_change_log("u", "t", "U1", "b", stamp_b, {"time": "2"}, "corrections")
    upload_backups.write_change_log("u", "t", "U1", "b", stamp_b, {"time": "3"}, "mppt_fits")
    files[("U1", "b/.broken_corrections.log")] = b"x"  # not a log name: ignored
    records = upload_backups.read_change_logs("u", "t", ["U1"], "b", "corrections")
    assert [r["time"] for r in records] == ["2", "1"]
    assert all(r["upload_id"] == "U1" for r in records)
    mppt = upload_backups.read_change_logs("u", "t", ["U1"], "b", "mppt_fits")
    assert [r["time"] for r in mppt] == ["3"]
    assert json.loads(files[("U1", f"b/.{stamp_b}_mppt_fits.log")])["time"] == "3"
