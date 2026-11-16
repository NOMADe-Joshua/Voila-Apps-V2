"""perotf_utils.access_token: where the usage logs (and records kept next to them) go."""

from pathlib import Path

from perotf_utils import access_token


def test_usage_logs_stay_in_the_package_folder_where_log_view_reads_them():
    assert access_token.usage_log_dir() == Path(access_token.__file__).resolve().parent


def test_both_usage_logs_are_written_to_usage_log_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(access_token, "usage_log_dir", lambda: tmp_path)
    monkeypatch.setenv("NOMAD_CLIENT_USER", "tester")
    access_token.log_notebook_usage()
    access_token.log_button_usage("open_app:SEM_crystal_counter")
    assert (tmp_path / "notebook_usage.log").read_text(encoding="utf-8")
    assert "open_app:SEM_crystal_counter" in (tmp_path / "button_usage.log").read_text(
        encoding="utf-8"
    )
