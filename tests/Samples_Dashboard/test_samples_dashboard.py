"""Samples_Dashboard with a simulated NOMAD query (no network)."""

from datetime import date, datetime

import pandas as pd
import pytest
import requests

from perotf_utils.config import ENTRY_TYPES

URL = "https://oasis.test/api/v1"
TOKEN = "tok"


def entry(entry_id, upload_id, author, created, upload_name=None, lab_id=None):
    main_author = author if isinstance(author, str) else {"user_id": author[0], "name": author[1]}
    return {
        "entry_id": entry_id,
        "entry_name": f"sample {entry_id}",
        "upload_id": upload_id,
        "upload_name": upload_name or f"Upload {upload_id}",
        "upload_create_time": created,
        "main_author": main_author,
        "results": {"eln": {"lab_ids": [lab_id or f"KIT_{entry_id}"]}},
    }


ENTRIES = [
    entry("e1", "up1", ("u-a", "Alice A"), "2025-01-10T10:00:00+00:00"),
    entry("e2", "up1", ("u-a", "Alice A"), "2025-01-10T10:00:00+00:00"),
    entry("e3", "up2", ("u-b", "Bob B"), "2025-02-03T09:00:00.123456+00:00"),
    entry("e4", "up3", "u-c", "2025-02-20T12:00:00+00:00"),  # bare id, name looked up
    entry("e5", "up4", ("u-shared", "MMB account"), "2025-03-01T08:00:00+00:00"),
]


class FakeQuery:
    def __init__(self, entries, admin_allowed=True):
        self.entries = entries
        self.admin_allowed = admin_allowed
        self.queries = []

    def __call__(self, url, token, endpoint, query):
        assert (url, token, endpoint) == (URL, TOKEN, "entries/query")
        self.queries.append(query)
        if query["owner"] == "admin" and not self.admin_allowed:
            response = requests.Response()
            response.status_code = 401
            raise requests.HTTPError("401", response=response)
        return [dict(e) for e in self.entries]


@pytest.fixture
def dm(mods):
    return mods["data_manager"]


@pytest.fixture
def pm(mods):
    return mods["plot_manager"]


@pytest.fixture
def nomad(dm, monkeypatch):
    fake = FakeQuery(ENTRIES)
    monkeypatch.setattr(dm, "query_all", fake)
    monkeypatch.setattr(
        dm, "_resolve_user_names", lambda url, token, ids: {i: "Carol C" for i in ids}
    )
    return fake


@pytest.fixture
def samples(dm, nomad):
    return dm.load_samples(URL, TOKEN).samples


# ── Loading ──────────────────────────────────────────────────────────────────


def test_one_query_reads_every_sample_with_its_upload_and_author(dm, nomad):
    result = dm.load_samples(URL, TOKEN)
    assert result.scope == dm.SCOPE_ADMIN
    [query] = nomad.queries
    assert query["owner"] == "admin"
    assert query["query"] == {"entry_type": ENTRY_TYPES["sample"]}
    assert "main_author" in query["required"]["include"]
    samples = result.samples
    assert list(samples["entry_id"]) == ["e1", "e2", "e3", "e4", "e5"]
    assert list(samples["author_name"]) == ["Alice A", "Alice A", "Bob B", "Carol C", "MMB account"]
    assert samples.loc[2, "upload_date"] == pd.Timestamp("2025-02-03 09:00:00.123456")
    assert samples.loc[0, "lab_id"] == "KIT_e1"


def test_without_admin_rights_the_visible_samples_are_loaded(dm, nomad):
    nomad.admin_allowed = False
    result = dm.load_samples(URL, TOKEN)
    assert result.scope == dm.SCOPE_VISIBLE
    assert [q["owner"] for q in nomad.queries] == ["admin", "visible"]
    assert len(result.samples) == 5


def test_a_server_error_is_not_mistaken_for_missing_rights(dm, monkeypatch):
    def failing(*_args):
        response = requests.Response()
        response.status_code = 502
        raise requests.HTTPError("502", response=response)

    monkeypatch.setattr(dm, "query_all", failing)
    with pytest.raises(requests.HTTPError):
        dm.load_samples(URL, TOKEN)


def test_no_samples_give_an_empty_frame(dm):
    samples = dm.samples_frame([])
    assert samples.empty
    assert list(samples.columns) == dm.SAMPLE_COLUMNS
    assert dm.uploads_table(samples, {}).empty
    assert dm.filter_uploads(dm.uploads_table(samples, {}), author="x").empty


# ── Overrides ────────────────────────────────────────────────────────────────

OLD_FILE = """# NOMAD Sample Attribution Overrides
# This file contains manual corrections to sample attributions.
upload_id,author_id,author_display_name,override_date
up4,IJP,IJP,2025-04-16
up2,,Pramila Patil,2025-04-17
,MMB,MMB,2025-04-16
"""


def test_the_old_overrides_file_is_read(dm):
    overrides = dm.parse_overrides_csv(OLD_FILE)
    assert set(overrides) == {"up4", "up2"}
    assert dm.override_name(overrides["up4"]) == "IJP"
    assert overrides["up2"]["author_id"] == "Pramila Patil"
    legacy = dm.parse_overrides_csv("upload_id,main_author,main_author_name\nup1,id1,Name One\n")
    assert dm.override_name(legacy["up1"]) == "Name One"


def test_overrides_round_trip_through_the_csv(dm):
    overrides = dm.parse_overrides_csv(OLD_FILE)
    text = dm.overrides_csv(overrides)
    assert text.startswith("# NOMAD Sample Attribution Overrides\n")
    assert dm.parse_overrides_csv(text) == overrides


def test_effective_authors_use_the_overrides(dm, samples):
    overrides = dm.parse_overrides_csv(OLD_FILE)
    assert list(dm.effective_authors(samples, overrides)) == [
        "Alice A",
        "Alice A",
        "Pramila Patil",
        "Carol C",
        "IJP",
    ]


def test_set_override_credits_and_removes(dm):
    today = date(2026, 11, 16)
    overrides = dm.set_override({}, ["up1", "up2"], "  Dana ", today)
    assert overrides["up1"] == {
        "author_id": "Dana",
        "author_display_name": "Dana",
        "override_date": "2026-11-16",
    }
    removed = dm.set_override(overrides, ["up1"], "")
    assert set(removed) == {"up2"}
    assert set(overrides) == {"up1", "up2"}  # the input is not changed
    assert dm.changed_uploads(overrides, removed) == ["up1"]


def test_uploads_table_and_filters(dm, samples):
    overrides = dm.set_override({}, ["up4"], "IJP")
    table = dm.uploads_table(samples, overrides)
    assert list(table["upload_id"]) == ["up4", "up3", "up2", "up1"]  # newest first
    assert table.set_index("upload_id").loc["up1", "samples"] == 2
    assert list(dm.filter_uploads(table, author="ijp")["upload_id"]) == ["up4"]
    assert list(dm.filter_uploads(table, author="alice")["upload_id"]) == ["up1"]
    assert list(dm.filter_uploads(table, upload_name="UPLOAD UP2")["upload_id"]) == ["up2"]
    in_february = dm.filter_uploads(table, date_from=date(2025, 2, 3), date_to=date(2025, 2, 20))
    assert list(in_february["upload_id"]) == ["up3", "up2"]
    assert dm.known_authors(samples, overrides)[0] == "IJP"


def test_save_keeps_a_backup_and_refuses_a_file_changed_meanwhile(dm, tmp_path):
    path = tmp_path / "overrides.csv"
    path.write_text(OLD_FILE, encoding="utf-8")
    loaded = dm.read_overrides(path)
    changed = dm.set_override(loaded.overrides, ["up9"], "Dana")
    saved = dm.save_overrides(loaded, changed)
    assert dm.read_overrides(path).overrides == changed
    assert (tmp_path / "overrides.csv.bak").read_text(encoding="utf-8") == OLD_FILE

    path.write_text(OLD_FILE, encoding="utf-8")  # another admin saves in between
    with pytest.raises(dm.OverridesChangedError):
        dm.save_overrides(saved, dm.set_override(changed, ["up8"], "Eve"))
    assert path.read_text(encoding="utf-8") == OLD_FILE


def test_a_missing_file_means_no_overrides_and_can_be_created(dm, tmp_path):
    path = tmp_path / "new.csv"
    loaded = dm.read_overrides(path)
    assert loaded.overrides == {} and loaded.fingerprint is None
    dm.save_overrides(loaded, {"up1": {"author_id": "A", "author_display_name": "A"}})
    assert set(dm.read_overrides(path).overrides) == {"up1"}
    assert not (tmp_path / "new.csv.bak").exists()


# ── Plots ────────────────────────────────────────────────────────────────────


def test_counts_per_author_and_period(pm, samples):
    authors = samples["author_name"]
    counts = pm.author_counts(authors)
    assert counts.iloc[0].tolist() == ["Alice A", 2]
    table = pm.time_counts(samples["upload_date"], authors, "Monthly")
    assert list(table.index) == ["2025-01", "2025-02", "2025-03"]
    assert table.loc["2025-02"].sum() == 2
    assert table.index.name == "Month"
    weekly = pm.time_counts(samples["upload_date"], authors, "Weekly")
    assert weekly.index[0] == "2025-01-06"  # the Monday of 2025-01-10
    assert list(pm.time_counts(samples["upload_date"], authors, "Yearly").index) == ["2025"]


def test_date_filter_includes_both_days(pm, samples):
    kept = pm.filter_by_date(samples, date(2025, 2, 3), date(2025, 2, 20))
    assert list(kept["entry_id"]) == ["e3", "e4"]


def test_figures_build_and_escape_names(pm):
    counts = pd.DataFrame({"Author": ["<b>x</b>"], "Samples": [3]})
    fig = pm.author_figure(counts)
    assert fig.data[0].x[0] == "&lt;b&gt;x&lt;/b&gt;"
    table = pd.DataFrame({"<i>y</i>": [1, 2]}, index=pd.Index(["2025-01", "2025-02"], name="Month"))
    time_fig = pm.time_figure(table, stacked=False)
    assert time_fig.layout.barmode == "group"
    assert time_fig.data[0].name == "&lt;i&gt;y&lt;/i&gt;"


# ── The app ──────────────────────────────────────────────────────────────────


@pytest.fixture
def app(mods, nomad, monkeypatch, tmp_path):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    path = tmp_path / "overrides.csv"
    path.write_text(OLD_FILE, encoding="utf-8")
    monkeypatch.setattr(mods["data_manager"], "overrides_path", lambda: path)
    monkeypatch.setattr(
        mods["app"], "read_overrides", lambda p=None: mods["data_manager"].read_overrides(p or path)
    )
    application = mods["app"].SamplesDashboardApp()
    application.auth_manager.url = URL
    application.auth_manager.current_token = TOKEN
    return application


def test_app_constructs_offline(mods, monkeypatch, tmp_path):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(
        mods["app"],
        "read_overrides",
        lambda p=None: mods["data_manager"].read_overrides(tmp_path / "x.csv"),
    )
    application = mods["app"].SamplesDashboardApp()
    assert application.get_dashboard() is not None
    assert application.load_button.disabled


def test_app_loads_plots_and_credits_uploads(app, tmp_path):
    app._load()
    assert "<b>5</b> samples" in app.summary_html.value
    assert "all uploads" in app.summary_html.value
    assert app.current["counts"].set_index("Author").loc["IJP", "Samples"] == 1
    assert len(app.uploads_select.options) == 4

    app.f_author.value = "alice"
    assert [uid for _label, uid in app.uploads_select.options] == ["up1"]
    app._select(all_shown=True)
    app.new_author.value = "Dana"
    app._assign(True)
    assert "1 unsaved changes" in app.pending_html.value
    assert app.current["counts"].set_index("Author").loc["Dana", "Samples"] == 2

    app._save()
    assert "Saved" in app.attr_status.value
    saved = (tmp_path / "overrides.csv").read_text(encoding="utf-8")
    assert "up1,Dana,Dana," in saved
    assert "unsaved" not in app.pending_html.value


def test_app_without_overrides_counts_nomad_authors(app):
    app._load()
    app.use_overrides.value = False
    assert "IJP" not in set(app.current["counts"]["Author"])


def test_app_import_adds_overrides_without_saving(app, tmp_path):
    app._load()
    content = b"upload_id,author_id,author_display_name,override_date\nup3,Eve,Eve,2025-05-01\n"
    upload = {
        "name": "old.csv",
        "type": "text/csv",
        "size": len(content),
        "last_modified": datetime(2026, 11, 16),
    }
    app.import_upload.value = ({**upload, "content": memoryview(content)},)
    assert app.overrides["up3"]["author_display_name"] == "Eve"
    assert "not saved yet" in app.attr_status.value
    assert "up3" not in (tmp_path / "overrides.csv").read_text(encoding="utf-8")
    app._discard()
    assert "up3" not in app.overrides


def test_app_shows_errors_instead_of_raising(app):
    app._guarded(lambda: app._assign(True))
    assert "Select at least one upload" in app.status_html.value


def test_exports_are_csv_safe(app, mods, monkeypatch):
    sent = []
    monkeypatch.setattr(
        mods["app"],
        "start_download",
        lambda out, content, name, mime: sent.append((content, name, mime)),
    )
    app._load()
    app.overrides = mods["data_manager"].set_override(app.overrides, ["up1"], "=HYPERLINK(1)")
    app._update_plots()
    app._export("authors_csv")
    content, name, mime = sent[-1]
    assert name.startswith("samples_per_author_") and mime == "text/csv"
    assert "'=HYPERLINK(1)" in content
    app._export("time_html")
    assert sent[-1][1].endswith(".html") and "<html>" in sent[-1][0]
