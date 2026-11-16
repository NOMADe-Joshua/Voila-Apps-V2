"""Entry_Auditor: unit tests (ported from HZB) -- never hits the real API.

The tests of HZB's local backup and log are replaced by tests of the peroTF write path:
backups and correction logs go into the entry's own upload (hidden files NOMAD never
parses), NOMAD refuses a write when the entry changed meanwhile (entry_hash), published
uploads, non-archive files and locked fields are never written, and a correction counts as
verified only when the file and the processed entry hold the new value."""

import json
from pathlib import Path

import pandas as pd
import pytest

from perotf_utils import api_calls, upload_backups
from perotf_utils.config import ENTRY_TYPES

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_batch.json"

# App modules, bound from the app_loader fixture (tests/Entry_Auditor/conftest.py). HZB's
# tests call the GUI module gc.
dm = gc = app_module = None


@pytest.fixture(scope="module", autouse=True)
def _bind_app_modules(mods):
    global dm, gc, app_module
    dm, gc, app_module = mods["data_manager"], mods["gui_components"], mods["app"]


def _patch_post(monkeypatch, fake_post):
    """Replace the requests.post that perotf_utils.api_calls.query_all uses."""
    monkeypatch.setattr(api_calls.requests, "post", fake_post)


# ---------------------------------------------------------------------------
# modify_file_field -- raw-text regex correction mechanism
# ---------------------------------------------------------------------------


def test_modify_file_field_json_replaces_value():
    file_text = '{"name": "Cleaning", "location": "HySpinbox", "other": "HySpinbox"}'
    modified, count = dm.modify_file_field(
        file_text, "entry.archive.json", "location", "HySpinbox", "HySpinBox"
    )
    assert count == 1
    assert '"location": "HySpinBox"' in modified
    assert '"other": "HySpinbox"' in modified  # only the matched key is touched


def test_modify_file_field_json_no_match_returns_zero_count():
    file_text = '{"location": "HySpinBox"}'
    modified, count = dm.modify_file_field(
        file_text, "entry.archive.json", "location", "NotPresent", "New"
    )
    assert count == 0
    assert modified == file_text


def test_modify_file_field_yaml_replaces_value():
    file_text = "name: Cleaning\nlocation: HySpinbox\nother: HySpinbox\n"
    modified, count = dm.modify_file_field(
        file_text, "entry.archive.yaml", "location", "HySpinbox", "HySpinBox"
    )
    assert count == 1
    assert "location: HySpinBox" in modified
    assert "other: HySpinbox" in modified


def test_modify_file_field_has_no_leaf_name_aliases_any_more():
    """The old COLUMN_TO_JSON_KEY mapping edited by leaf name; edits are path-exact now."""
    assert not hasattr(dm, "COLUMN_TO_JSON_KEY")


# ---------------------------------------------------------------------------
# _flatten -- recursive archive-data flattening used by load_generic_data
# ---------------------------------------------------------------------------


def test_flatten_nested_dict_produces_dot_path_keys():
    out: dict = {}
    dm._flatten({"annealing": {"atmosphere": "N2"}}, "", out)
    assert out == {"annealing.atmosphere": "N2"}


def test_flatten_list_of_dicts_keeps_shared_prefix():
    out: dict = {}
    dm._flatten({"layer": [{"layer_type": "ETL"}]}, "", out)
    assert out == {"layer.layer_type": "ETL"}


def test_flatten_skips_blank_none_and_bool_leaves_but_keeps_numbers():
    out: dict = {}
    dm._flatten({"a": "", "b": None, "c": 5, "d": "kept", "e": 1.42, "f": True}, "", out)
    assert out == {"c": "5", "d": "kept", "e": "1.42"}


def test_flatten_keeps_a_varying_solute_concentration():
    out: dict = {}
    data = {"solution": [{"solution_details": {"solute": [{"concentration_mol": 1.42}]}}]}
    dm._flatten(data, "", out)
    assert out == {"solution.solution_details.solute.concentration_mol": "1.42"}


def test_modify_file_field_writes_a_number_back_as_a_number():
    file_text = '{"data": {"solute": [{"concentration_mol": 1.42}, {"concentration_mol": 2}]}}'
    modified, count = dm.modify_file_field(
        file_text, "entry.archive.json", "solute.1.concentration_mol", "1.42", "1.5"
    )
    assert count == 1
    assert '"concentration_mol": 1.5' in modified
    assert '"1.5"' not in modified
    # an integer stays an integer when the new value is one
    modified, count = dm.modify_file_field(
        file_text, "entry.archive.json", "solute.2.concentration_mol", "2", "3"
    )
    assert count == 1
    assert '"concentration_mol": 3}' in modified


def test_modify_file_field_refuses_text_for_a_number():
    file_text = '{"data": {"conc": 1.42}}'
    modified, count = dm.modify_file_field(file_text, "e.archive.json", "conc", "1.42", "abc")
    assert count == 0
    assert modified == file_text


def test_flatten_multi_item_list_numbers_each_item_instead_of_overwriting():
    out: dict = {}
    dm._flatten(
        {
            "solvent": [
                {"name": "DMF 0.01 milliliter"},
                {"name": "DMF 0.02 milliliter"},
            ]
        },
        "",
        out,
    )
    assert out == {
        "solvent.1.name": "DMF 0.01 milliliter",
        "solvent.2.name": "DMF 0.02 milliliter",
    }


def test_flatten_three_item_list_numbers_all_three():
    out: dict = {}
    dm._flatten({"layer": [{"layer_type": "A"}, {"layer_type": "B"}, {"layer_type": "C"}]}, "", out)
    assert out == {
        "layer.1.layer_type": "A",
        "layer.2.layer_type": "B",
        "layer.3.layer_type": "C",
    }


# ---------------------------------------------------------------------------
# get_ids_in_batch_tolerant -- duplicate-tolerant replacement for the shared,
# asserting perotf_utils.api_calls.get_ids_in_batch
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_get_ids_in_batch_tolerant_dedupes_and_warns_on_duplicates(monkeypatch, caplog):
    payload = {
        "data": [
            {
                "archive": {
                    "data": {
                        "lab_id": "Batch1",
                        "entities": [{"lab_id": "S1"}, {"lab_id": "S2"}],
                    }
                }
            },
            {
                "archive": {
                    "data": {
                        "lab_id": "Batch1",
                        "entities": [{"lab_id": "S2"}, {"lab_id": "S3"}],
                    }
                }
            },
        ],
        "pagination": {},
    }
    _patch_post(monkeypatch, lambda *a, **k: _FakeResponse(payload))

    with caplog.at_level("WARNING"):
        result = dm.get_ids_in_batch_tolerant("https://example.test/api/v1", "tok", ["Batch1"])

    assert result == ["S1", "S2", "S3"]
    assert any("duplicate" in message.lower() for message in caplog.messages)


def test_get_ids_in_batch_tolerant_uses_the_configured_batch_type(monkeypatch):
    from perotf_utils.config import ENTRY_TYPES

    sent = []

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.append(json["query"]["entry_type"])
        return _FakeResponse({"data": [], "pagination": {}})

    _patch_post(monkeypatch, fake_post)
    monkeypatch.setitem(ENTRY_TYPES, "batch", "Other_Batch")

    dm.get_ids_in_batch_tolerant("https://example.test/api/v1", "tok", ["B1"])

    assert sent == ["Other_Batch"]


def test_fetch_entry_files_reads_every_page(monkeypatch):
    """Both queries return two pages; entries on the second page used to be dropped (#172)."""

    def fake_post(url, headers=None, json=None, timeout=None):
        after = json["pagination"].get("page_after_value")
        if "results.eln.lab_ids:any" in json["query"]:
            rows = [{"entry_id": "s2"}] if after else [{"entry_id": "s1"}]
        else:
            assert json["query"]["entry_references.target_entry_id:any"] == ["s1", "s2"]
            n = 2 if after else 1
            rows = [{"entry_id": f"e{n}", "upload_id": "U", "mainfile": f"m{n}.json"}]
        pagination = {} if after else {"next_page_after_value": "p2"}
        return _FakeResponse({"data": rows, "pagination": pagination})

    _patch_post(monkeypatch, fake_post)

    files = dm.fetch_entry_files("https://example.test/api/v1", "tok", ["S1"], "HySprint_JV")

    assert files == [("e1", "U", "m1.json"), ("e2", "U", "m2.json")]


def test_get_ids_in_batch_tolerant_returns_empty_for_no_batch_ids():
    assert dm.get_ids_in_batch_tolerant("https://example.test/api/v1", "tok", []) == []


# ---------------------------------------------------------------------------
# discover_present_entry_types -- lightweight, entry_type-agnostic reconnaissance that
# lets EntryAuditSession.load skip load_generic_data entirely for schemas with nothing
# for a given sample set, instead of running its full per-type queries to find that out
# ---------------------------------------------------------------------------


def test_discover_present_entry_types_covers_all_three_match_strategies(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        query = json.get("query", {})
        if url.endswith("/entries/archive/query"):
            # _resolve_reference_ids: full archive fetch for reference-id extraction.
            return _FakeResponse(
                {"data": [{"archive": {"data": {"note": "../uploads/X/archive/REF1#/data"}}}]}
            )
        if "entry_references.target_entry_id:any" in query:
            return _FakeResponse({"data": [{"entry_type": "TypeB"}]})
        if "entry_id:any" in query:
            return _FakeResponse({"data": [{"entry_type": "TypeC"}]})
        if "results.eln.lab_ids:any" in query:
            return _FakeResponse(
                {
                    "data": [
                        {"entry_id": "e1", "entry_type": "HySprint_Sample"},
                        {"entry_id": "e2", "entry_type": "HySprint_Sample"},
                    ]
                }
            )
        raise AssertionError(f"unexpected query: {json}")

    _patch_post(monkeypatch, fake_post)

    sample_entry_ids, ref_ids, entry_types = dm.discover_present_entry_types(
        "https://example.test/api/v1", "tok", ["S1", "S2"]
    )

    assert sample_entry_ids == ["e1", "e2"]
    assert ref_ids == {"REF1"}
    assert entry_types == {"HySprint_Sample", "TypeB", "TypeC"}


# ---------------------------------------------------------------------------
# Correction log persistence
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# EntryAuditSession -- offline/demo mode + inconsistency detection
# ---------------------------------------------------------------------------


def test_load_offline_returns_true_and_populates_datasets(fresh_session):
    assert fresh_session.load_offline(FIXTURE_PATH) is True
    assert fresh_session.is_loaded
    assert set(fresh_session.datasets) == {"Cleaning", "Substrate"}
    assert len(fresh_session.sample_ids) == 3


def test_load_offline_returns_false_for_empty_fixture(tmp_path, fresh_session):
    fixture = tmp_path / "empty.json"
    fixture.write_text(json.dumps({"sample_links": {}, "datasets": {}}))
    assert fresh_session.load_offline(fixture) is False
    assert not fresh_session.is_loaded


def test_auditable_columns_finds_inconsistent_location_field(fresh_session):
    fresh_session.load_offline(FIXTURE_PATH)
    assert "location" in fresh_session.auditable_columns("Cleaning")


def test_field_summary_reports_typo_split(fresh_session):
    fresh_session.load_offline(FIXTURE_PATH)
    summary = fresh_session.field_summary("Cleaning", "location")
    values = {row["value"]: row["count"] for row in summary}
    assert values == {"HySpinBox": 2, "HySpinbox": 1}


def test_consistent_dataset_field_has_single_value(fresh_session):
    fresh_session.load_offline(FIXTURE_PATH)
    assert "substrate" in fresh_session.auditable_columns("Substrate")
    summary = fresh_session.field_summary("Substrate", "substrate")
    assert len(summary) == 1
    assert summary[0]["count"] == 3


def test_field_overview_flags_varied_and_consistent_columns(fresh_session):
    fresh_session.load_offline(FIXTURE_PATH)
    overview = {entry["column"]: entry for entry in fresh_session.field_overview("Cleaning")}
    assert overview["location"]["is_varied"] is True
    assert len(overview["location"]["summary"]) == 2
    assert overview["name"]["is_varied"] is False
    assert len(overview["name"]["summary"]) == 1


def test_field_overview_matches_auditable_columns(fresh_session):
    fresh_session.load_offline(FIXTURE_PATH)
    overview_columns = {entry["column"] for entry in fresh_session.field_overview("Substrate")}
    assert overview_columns == set(fresh_session.auditable_columns("Substrate"))


def _sample_with_jv_plots() -> dict:
    """A Sample's data as recent nomad-baseclasses stores it: Plotly figures and per-scan
    jv_history_* lists, both recomputed from the JV measurements on every processing."""
    return {
        "name": "S1",
        "description": "spin coated",
        "jv_history_efficiency": [14.7, 21.5],
        "jv_history_cell_name": ["a_rev", "b_rev"],
        "figures": [
            {
                "label": "JV History",
                "figure": {"data": [{"x": [1, 2, 3], "y": [14.7, 21.5, 20.1], "name": "rev"}]},
            },
            {"label": "Best Pixel", "figure": {"data": [{"x": [0.1, 0.2], "y": [5, 6]}]}},
        ],
    }


def test_auditable_columns_skip_plot_figures_and_jv_history(fresh_session):
    """Issue #167: every plot point became an auditable field (over 10,000 for one batch),
    which stalled the results view."""
    rows = []
    for name in ("S1", "S2"):
        row: dict = {"sample_id": name}
        data = _sample_with_jv_plots()
        data["name"] = name
        dm._flatten(data, "", row)
        rows.append(row)
    fresh_session.datasets["Sample"] = pd.DataFrame(rows)
    columns = fresh_session.auditable_columns("Sample")
    assert "name" in columns and "description" in columns
    assert not [c for c in columns if c.startswith(("figures", "jv_history_"))]


def test_noise_patterns_match_nested_figures_but_not_similar_names():
    def noise(column):
        return any(pattern.search(column) for pattern in dm._NOISE_COLUMN_PATTERNS)

    assert noise("figures.1.figure.data.x.2")
    assert noise("results.figures.label")
    assert noise("jv_history_efficiency.3")
    assert not noise("figures_note")
    assert not noise("my_jv_history_note")


# ---------------------------------------------------------------------------
# apply_correction -- corrects every occurrence and logs only on success
# ---------------------------------------------------------------------------


def test_mainfile_label_strips_archive_suffix():
    assert gc._mainfile_label("11_0_spin_coating_Perovskite.archive.json") == (
        "11_0_spin_coating_Perovskite"
    )
    assert gc._mainfile_label("cleaning.archive.yaml") == "cleaning"


def test_mainfile_label_leaves_non_matching_names_untouched():
    assert gc._mainfile_label("") == ""
    assert gc._mainfile_label("no_suffix_here") == "no_suffix_here"


def test_correction_result_total_sums_all_outcomes():
    result = dm.CorrectionResult(success=2, failed=1, skipped=3)
    assert result.total == 6


def test_modify_file_field_does_not_partial_match_substrings():
    # "HySpinbox" must not match inside "HySpinboxes" -- guards against the regex
    # accidentally corrupting an unrelated, longer value that merely contains it.
    file_text = '{"location": "HySpinboxes"}'
    _modified, count = dm.modify_file_field(
        file_text, "entry.archive.json", "location", "HySpinbox", "HySpinBox"
    )
    assert count == 0


# ---------------------------------------------------------------------------
# Corrections are enabled, behind a preview + confirm step (issue #56)
# ---------------------------------------------------------------------------


def test_field_audit_panel_offers_preview_then_confirm(fresh_session):
    assert gc.CORRECTIONS_ENABLED is True
    assert fresh_session.load_offline(FIXTURE_PATH)
    label = next(iter(fresh_session.datasets))
    panel = gc.FieldAuditPanel(fresh_session, label, url="https://example.org", token="t")
    assert panel.dropdown is not None
    assert not hasattr(panel, "correct_button")  # no one-click write any more
    assert panel.confirm_button.layout.display == "none"  # nothing to confirm yet
    assert panel.cancel_button.layout.display == "none"


def test_sample_dropdown_follows_the_table_column_order(fresh_session):
    assert fresh_session.load_offline(FIXTURE_PATH)
    label = next(iter(fresh_session.datasets))
    panel = gc.FieldAuditPanel(fresh_session, label, url="https://example.org", token="t")
    df = panel.entries_df
    table_order = [str(df.loc[i].get("_entry_id", "")) for i in panel.entry_indices]
    shown = [value for _label, value in panel.sample_dropdown.options if value is not None]
    assert shown == [e for e in table_order if e in shown]


def test_field_audit_panel_offline_has_no_correction_controls(fresh_session):
    assert fresh_session.load_offline(FIXTURE_PATH)
    label = next(iter(fresh_session.datasets))
    panel = gc.FieldAuditPanel(fresh_session, label, url=None, token=None)
    assert panel.dropdown is None


# ---------------------------------------------------------------------------
# 5.1 safe corrections: path-exact edit (C1), escaping (H1/H2), upload folder (C2),
# verified outcome (C3), backup + preview (H3), HTML escaping (H4), refresh (H5)
# ---------------------------------------------------------------------------

_MULTI = {
    "name": "DMF",
    "solution": [
        {
            "solvent": [
                {"chemical_2": {"name": "DMF"}},
                {"chemical_2": {"name": "DMSO"}},
            ],
            "solute": [{"chemical_2": {"name": "DMF"}}],
        }
    ],
}


def _flat(text, mainfile="e.archive.json"):
    data = dm._parse_archive_text(text, mainfile)
    out: dict[str, str] = {}
    dm._flatten(data, "", out)
    return out


def test_correction_changes_only_the_audited_path_not_every_same_leaf_name():
    """Reproduces C1: three fields share the leaf name 'name' (and two the value DMF)."""
    text = json.dumps(_MULTI)
    column = "solution.solvent.1.chemical_2.name"
    assert _flat(text)[column] == "DMF"

    modified, count = dm.modify_file_field(text, "e.archive.json", column, "DMF", "N,N-DMF")

    assert count == 1
    flat = _flat(modified)
    assert flat[column] == "N,N-DMF"
    assert flat["solution.solvent.2.chemical_2.name"] == "DMSO"
    assert flat["solution.solute.chemical_2.name"] == "DMF"  # same value, other field
    assert flat["name"] == "DMF"  # the entry's own name


def test_correction_follows_single_item_lists_and_numbered_lists():
    text = json.dumps(_MULTI)
    modified, count = dm.modify_file_field(
        text, "e.archive.json", "solution.solute.chemical_2.name", "DMF", "X"
    )
    assert count == 1 and _flat(modified)["solution.solute.chemical_2.name"] == "X"
    modified, count = dm.modify_file_field(
        text, "e.archive.json", "solution.solvent.2.chemical_2.name", "DMSO", "Y"
    )
    assert count == 1 and _flat(modified)["solution.solvent.2.chemical_2.name"] == "Y"


def test_correction_refuses_a_path_that_is_missing_or_holds_another_value():
    text = json.dumps(_MULTI)
    for column, old in (
        ("solution.solvent.3.chemical_2.name", "DMF"),  # no third solvent
        ("solution.solvent.2.chemical_2.name", "DMF"),  # holds DMSO
        ("name.extra", "DMF"),  # beyond a leaf
        ("solution.solvent", "DMF"),  # not a leaf
    ):
        modified, count = dm.modify_file_field(text, "e.archive.json", column, old, "X")
        assert count == 0 and modified == text, column


def test_correction_survives_quotes_backslashes_newlines_and_unicode_in_the_new_value():
    text = '{"location": "HySpinbox", "unit": "\\u00b0C"}'
    for new in ['say "hi"', "back\\1slash", "line1\nline2", "N,N-DMF °C", "a: b # c"]:
        modified, count = dm.modify_file_field(text, "e.archive.json", "location", "HySpinbox", new)
        assert count == 1
        assert json.loads(modified)["location"] == new  # still valid JSON, exact value
        assert json.loads(modified)["unit"] == "°C"


def test_correction_matches_values_stored_json_escaped_or_yaml_quoted():
    escaped = '{"unit": "\\u00b0C"}'  # the file holds the escape, the audit table the character
    modified, count = dm.modify_file_field(escaped, "e.archive.json", "unit", "°C", "degC")
    assert count == 1 and json.loads(modified)["unit"] == "degC"
    quoted = 'location: "HySpinbox"\nother: "HySpinbox"\n'
    modified, count = dm.modify_file_field(quoted, "e.archive.yaml", "location", "HySpinbox", "Box")
    assert count == 1
    assert dm._parse_archive_text(modified, "e.archive.yaml") == {
        "location": "Box",
        "other": "HySpinbox",
    }


def test_correction_refuses_a_file_that_does_not_parse():
    modified, count = dm.modify_file_field("{not json", "e.archive.json", "a", "x", "y")
    assert count == 0 and modified == "{not json"


def test_correction_keeps_key_order_and_json_indentation():
    text = '{\n  "b": "1",\n  "a": "2"\n}\n'
    modified, count = dm.modify_file_field(text, "e.archive.json", "a", "2", "3")
    assert count == 1
    assert modified == '{\n  "b": "1",\n  "a": "3"\n}\n'


def test_field_values_from_nomad_are_html_escaped_in_the_table(fresh_session):
    assert fresh_session.load_offline(FIXTURE_PATH)
    label = next(iter(fresh_session.datasets))
    df = fresh_session.datasets[label]
    column = next(c for c in df.columns if not c.startswith("_") and c != "sample_id")
    df.loc[df.index[0], column] = "<img src=x onerror=alert(1)>"
    panel = gc.FieldAuditPanel(fresh_session, label, url=None, token=None)
    cells = [c.value for cells in panel._value_cells.values() for c in cells]
    assert any("&lt;img src=x onerror=alert(1)&gt;" in v for v in cells)
    assert not any("<img" in v for v in cells)
    assert gc._esc("<a title='x'>") == "&lt;a title=&#x27;x&#x27;&gt;"


def test_changing_the_selection_after_a_preview_withdraws_the_confirmation(monkeypatch):
    session = dm.EntryAuditSession()
    assert session.load_offline(FIXTURE_PATH)
    monkeypatch.setattr(dm, "download_file", lambda *a, **k: json.dumps({"location": "HySpinbox"}))
    monkeypatch.setattr(dm, "get_upload", lambda *a, **k: {"published": False})
    monkeypatch.setattr(gc, "preview_correction", dm.preview_correction)
    panel = gc.FieldAuditPanel(session, "Cleaning", url="https://e.test/api/v1", token="t")
    panel.dropdown.value = "location"
    panel.from_dropdown.value = "HySpinbox"
    panel.to_input.value = "Other"
    panel._on_preview_click(None)
    assert panel.confirm_button.layout.display is None
    panel.to_input.value = "Different"
    assert panel._pending is None and panel.confirm_button.layout.display == "none"


def _wrapped_archive():
    """The shape of a real .archive.json: the entry's fields sit under a top-level "data"."""
    return {
        "data": {
            "m_def": "nomad_hysprint.schema_packages.hysprint_package.HySprint_SpinCoating",
            "name": "spin coating X",
            "description": "Process notes",
            "location": "HZB-HySprintBox",
            "samples": [{"lab_id": "S1", "reference": "../uploads/u/archive/e#data"}],
            "solution": [{"solvent": [{"name": "DMF"}, {"name": "DMSO"}]}],
        }
    }


def test_correction_works_on_a_file_with_the_data_wrapper():
    """Real archive files wrap the audited fields in "data"; a path-exact edit that started at the
    file root found nothing ("0 will change") so no correction could ever be confirmed."""
    text = json.dumps(_wrapped_archive(), indent=2)
    modified, count = dm.modify_file_field(
        text, "e.archive.json", "location", "HZB-HySprintBox", "HySpinBox"
    )
    assert count == 1
    result = json.loads(modified)
    assert result["data"]["location"] == "HySpinBox"
    assert result["data"]["name"] == "spin coating X"  # nothing else touched
    assert set(result) == {"data"}


def test_wrapped_file_numbered_lists_and_read_back():
    text = json.dumps(_wrapped_archive())
    modified, count = dm.modify_file_field(
        text, "e.archive.json", "solution.solvent.2.name", "DMSO", "N,N-DMF"
    )
    assert count == 1
    assert (
        dm.get_value_at_flat_path(modified, "e.archive.json", "solution.solvent.2.name")
        == "N,N-DMF"
    )
    assert dm.get_value_at_flat_path(modified, "e.archive.json", "solution.solvent.1.name") == "DMF"
    assert dm.get_value_at_flat_path(modified, "e.archive.json", "samples.lab_id") == "S1"


def test_wrapped_yaml_file():
    text = "data:\n  location: Box\n  other: Box\n"
    modified, count = dm.modify_file_field(text, "e.archive.yaml", "location", "Box", "New")
    assert count == 1
    assert dm._parse_archive_text(modified, "e.archive.yaml") == {
        "data": {"location": "New", "other": "Box"}
    }


def test_a_wrong_path_still_changes_nothing_in_a_wrapped_file():
    text = json.dumps(_wrapped_archive())
    modified, count = dm.modify_file_field(text, "e.archive.json", "data.location", "x", "y")
    assert count == 0 and modified == text


def test_load_generic_data_keeps_a_field_that_only_some_entries_have(monkeypatch):
    from perotf_utils.consistency import get_string_columns

    def entry(entry_id, solutes):
        return {
            "archive": {
                "metadata": {"entry_id": entry_id, "upload_id": "u", "mainfile": entry_id},
                "data": {
                    "samples": [{"lab_id": "s1"}],
                    "solution": [{"solution_details": {"solute": solutes}}],
                },
            }
        }

    entries = [
        entry("e1", [{"concentration_mol": 0.1}, {"concentration_mol": 0.2}]),
        entry("e2", [{"concentration_mol": 0.1}]),
    ]

    class _Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": entries}

    _patch_post(monkeypatch, lambda *a, **k: _Response())
    monkeypatch.setattr(dm, "_resolve_sample_entry_ids", lambda *a, **k: [])

    df = dm.load_generic_data("http://x/api/v1", "t", ["s1"], "HySprint_SpinCoating")

    column = "solution.solution_details.solute.2.concentration_mol"
    assert column in get_string_columns(df)
    assert df[column].dropna().tolist() == ["0.2"]


# ---------------------------------------------------------------------------
# What is audited on this Oasis
# ---------------------------------------------------------------------------


def _prefixed(name):
    """An entry type name with this Oasis' schema prefix (taken from the sample type)."""
    return ENTRY_TYPES["sample"].split("_", 1)[0] + "_" + name


def test_audit_catalog_is_batch_sample_substrate_and_the_batchs_process_steps():
    present = {ENTRY_TYPES["sample"], ENTRY_TYPES["batch"], _prefixed("JVmeasurement")}
    processes = {_prefixed("CR_SpinBox_SpinCoating"), _prefixed("TFL_PEROvap_Evaporation")}
    catalog = dm.audit_catalog(present | processes, processes)
    assert catalog == {
        "Batch": ENTRY_TYPES["batch"],
        "Sample": ENTRY_TYPES["sample"],
        "CR_SpinBox_SpinCoating": _prefixed("CR_SpinBox_SpinCoating"),
        "TFL_PEROvap_Evaporation": _prefixed("TFL_PEROvap_Evaporation"),
    }  # no substrate in this batch, and measurements are never audited


def test_discover_process_types_asks_nomad_for_baseprocess_entries(monkeypatch):
    seen = []

    def fake_query_all(url, token, endpoint, query):
        seen.append(query["query"])
        return [{"entry_type": _prefixed("Cleaning")}, {"entry_type": _prefixed("Cleaning")}]

    monkeypatch.setattr(dm, "query_all", fake_query_all)
    assert dm.discover_process_types("u", "t", ["e1", "e2"]) == {_prefixed("Cleaning")}
    assert seen == [
        {
            "entry_references.target_entry_id:any": ["e1", "e2"],
            "section_defs.definition_qualified_name": ENTRY_TYPES["base_process"],
        }
    ]
    assert dm.discover_process_types("u", "t", []) == set()


def test_session_load_audits_the_catalog_and_remembers_each_type(monkeypatch):
    spin = _prefixed("CR_SpinBox_SpinCoating")
    monkeypatch.setattr(dm, "get_ids_in_batch_tolerant", lambda *a: ["S1"])
    monkeypatch.setattr(dm, "get_sample_links_chunked", lambda *a: {})
    monkeypatch.setattr(
        dm,
        "discover_present_entry_types",
        lambda *a: (["e1"], set(), {ENTRY_TYPES["sample"], spin, _prefixed("JVmeasurement")}),
    )
    monkeypatch.setattr(dm, "discover_process_types", lambda *a: {spin})
    loaded = []

    def fake_load(url, token, sample_ids, entry_type, cache=None):
        loaded.append(entry_type)
        return pd.DataFrame([{"sample_id": "S1", "_upload_id": "U1", "solvent": "DMF"}])

    monkeypatch.setattr(dm, "load_generic_data", fake_load)
    session = dm.EntryAuditSession()
    session.load("u", "t", ["B1"])
    assert loaded == [ENTRY_TYPES["sample"], spin]
    assert session.entry_types == {"Sample": ENTRY_TYPES["sample"], "CR_SpinBox_SpinCoating": spin}
    assert session.upload_ids == ["U1"]


def test_entry_links_point_at_this_oasis_gui(monkeypatch):
    from perotf_utils.config import GUI_ENDPOINT, URL_BASE

    entry = {
        "archive": {
            "metadata": {"entry_id": "E1", "upload_id": "U1", "mainfile": "a.archive.json"},
            "data": {"samples": [{"lab_id": "S1"}], "solvent": "DMF"},
        }
    }
    monkeypatch.setattr(dm, "query_all", lambda *a, **k: [entry])
    monkeypatch.setattr(dm, "_resolve_sample_entry_ids", lambda *a, **k: [])
    df = dm.load_generic_data("u", "t", ["S1"], "Any_Type")
    assert df.loc[0, "_gui_url"] == (
        f"{URL_BASE}{GUI_ENDPOINT}/user/uploads/upload/id/U1/entry/id/E1"
    )


# ---------------------------------------------------------------------------
# Locked fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "column",
    [
        "lab_id",
        "samples.lab_id",
        "positon_in_experimental_plan",
        "datetime",
        "layer.1.end_time",
    ],
)
def test_locked_fields_are_never_offered_and_never_written(column):
    df = pd.DataFrame(
        {
            "sample_id": ["S1", "S2"],
            column: ["A", "B"],
            "solvent": ["DMF", "dmf"],
            "_entry_id": ["E1", "E2"],
            "_upload_id": ["U1", "U1"],
            "_mainfile": ["a.archive.json", "b.archive.json"],
        }
    )
    session = dm.EntryAuditSession()
    session.datasets["Spin"] = df
    assert session.auditable_columns("Spin") == ["solvent"]
    with pytest.raises(dm.LockedFieldError):
        dm.apply_correction("u", "t", df, column, "A", "C", "T")
    with pytest.raises(dm.LockedFieldError):
        dm.preview_correction("u", "t", df, column, "A", "C", "T")


def test_similar_names_are_not_locked():
    assert not dm.is_locked("lab_id_note")
    assert not dm.is_locked("solvent")
    assert dm.is_locked("entities.3.lab_id")


# ---------------------------------------------------------------------------
# The write path against a simulated NOMAD (at the level of perotf_utils.api_calls)
# ---------------------------------------------------------------------------


class FakeNomad:
    """Uploads with raw files, entries with hashes, processing and publish state."""

    def __init__(self, entries, published=()):
        # entries: {entry_id: (upload_id, mainfile, file text)}
        self.files = {(u, path): text for u, path, text in entries.values()}
        self.entry_files = {eid: (u, path) for eid, (u, path, _) in entries.items()}
        self.hashes = {eid: f"hash-{eid}" for eid in entries}
        self.published = set(published)
        self.changed_meanwhile = set()  # entry ids someone edited after they were read
        self.processed_override = {}  # entry id -> data NOMAD serves after processing
        self.fail_backups = False
        self.status = "SUCCESS"
        self.puts = []

    def install(self, monkeypatch):
        monkeypatch.setattr(dm, "get_upload", self.get_upload)
        monkeypatch.setattr(dm, "download_raw_file", self.download)
        monkeypatch.setattr(dm, "put_raw_file", self.put)
        monkeypatch.setattr(dm, "wait_for_upload", lambda *a, **k: self.status)
        monkeypatch.setattr(
            dm, "get_entry_hashes", lambda url, token, ids: {i: self.hashes[i] for i in ids}
        )
        monkeypatch.setattr(dm, "get_entry_data", self.entry_data)
        monkeypatch.setattr(dm.time, "sleep", lambda *_a: None)
        # backups and logs are written by the shared module (perotf_utils.upload_backups)
        for name, fake in [
            ("put_raw_file", self.put),
            ("download_raw_file", self.download),
            ("list_raw_folder", self.listdir),
            ("wait_for_upload", lambda *a, **k: self.status),
        ]:
            monkeypatch.setattr(upload_backups, name, fake)
        return self

    def get_upload(self, url, token, upload_id):
        published = upload_id in self.published
        return {"published": published, "process_running": False, "process_status": "SUCCESS"}

    def download(self, url, token, upload_id, path):
        return self.files[(upload_id, path)].encode("utf-8")

    def put(self, url, token, upload_id, folder, filename, content, mime_type, **kwargs):
        path = f"{folder}/{filename}" if folder else filename
        self.puts.append({"upload": upload_id, "path": path, **kwargs})
        assert upload_id not in self.published, "wrote into a published upload"
        if kwargs.get("overwrite") is False:
            if self.fail_backups and path.endswith(".bak"):
                raise api_calls.UploadConflictError("backup refused")
            if (upload_id, path) in self.files:
                raise api_calls.UploadConflictError("exists")
        entry = next((e for e, f in self.entry_files.items() if f == (upload_id, path)), None)
        if entry is not None:
            if entry in self.changed_meanwhile or kwargs.get("entry_hash") != self.hashes[entry]:
                raise api_calls.UploadConflictError("The provided hash did not match")
            self.hashes[entry] += "+"
        self.files[(upload_id, path)] = content.decode("utf-8")

    def entry_data(self, url, token, entry_id):
        if entry_id in self.processed_override:
            return self.processed_override[entry_id]
        parsed = json.loads(self.files[self.entry_files[entry_id]])
        return parsed["data"]

    def listdir(self, url, token, upload_id, folder):
        prefix = folder.rstrip("/") + "/"
        return [
            path[len(prefix) :]
            for u, path in self.files
            if u == upload_id and path.startswith(prefix) and "/" not in path[len(prefix) :]
        ]

    def data_paths(self, upload_id):
        return {path for u, path in self.files if u == upload_id}


def _archive(**data):
    return json.dumps({"data": data}, indent=2)


def _frame(entries, column="location"):
    """The audit table rows of these entries (as load_generic_data would build them)."""
    rows = []
    for entry_id, (upload_id, mainfile, text) in entries.items():
        value = json.loads(text)["data"].get(column) if text.startswith("{") else "HySpinbox"
        rows.append(
            {
                "sample_id": f"S-{entry_id}",
                "_entry_id": entry_id,
                "_upload_id": upload_id,
                "_mainfile": mainfile,
                column: value,
            }
        )
    return pd.DataFrame(rows)


ONE = {"E1": ("U1", "sub/clean.archive.json", _archive(location="HySpinbox", lab_id="S-E1"))}


def test_a_correction_backs_up_into_the_entrys_own_upload_then_writes_its_own_folder(
    monkeypatch,
):
    nomad = FakeNomad(ONE).install(monkeypatch)
    original = nomad.files[("U1", "sub/clean.archive.json")]
    result = dm.apply_correction("u", "t", _frame(ONE), "location", "HySpinbox", "HySpinBox", "T")

    assert (result.success, result.failed, result.log_errors) == (1, 0, 0)
    backup, corrected, log = nomad.puts
    # 1. the original, hidden, in the same upload, never overwriting, no reprocessing
    assert backup["upload"] == "U1"
    assert backup["path"].startswith("entry_auditor_backups/sub/.clean.archive.json.")
    assert backup["path"].endswith(".bak")
    assert (backup["overwrite"], backup["trigger_processing"]) == (False, False)
    assert nomad.files[("U1", backup["path"])] == original
    # 2. the corrected file back into its own folder, guarded by the entry's hash
    assert corrected["path"] == "sub/clean.archive.json"
    assert corrected["entry_hash"] == "hash-E1"
    assert json.loads(nomad.files[("U1", "sub/clean.archive.json")])["data"] == {
        "location": "HySpinBox",
        "lab_id": "S-E1",
    }
    # 3. the log of this run, hidden, in the same upload
    assert log["path"].startswith("entry_auditor_backups/.") and log["path"].endswith(
        "_corrections.log"
    )
    assert (log["overwrite"], log["trigger_processing"]) == (False, False)
    record = json.loads(nomad.files[("U1", log["path"])])
    assert (record["field"], record["from"], record["to"]) == ("location", "HySpinbox", "HySpinBox")
    assert record["entries"][0]["backup"] == backup["path"]
    assert record["entries"][0]["outcome"] == "verified"


def test_backups_and_logs_have_names_nomad_never_parses():
    """NOMAD skips every file whose name starts with a dot (nomad.parsing.parsers.
    match_parser), so a backup or log can never become an entry; .bak/.log end the name."""
    for mainfile in ["a.archive.json", "deep/er/b.archive.yaml"]:
        folder, name = dm.backup_location(mainfile, "20261114T120000_000001")
        assert folder == "/".join(
            filter(None, ["entry_auditor_backups", mainfile.rpartition("/")[0]])
        )
        assert name.startswith(".") and name.endswith(".bak")
        assert not name.endswith((".archive.json", ".archive.yaml", ".xlsx"))
    assert dm._LOG_NAME.match(".20261114T120000_000001_corrections.log")


def test_nothing_is_written_when_the_backup_cannot_be_stored(monkeypatch):
    nomad = FakeNomad(ONE).install(monkeypatch)
    nomad.fail_backups = True
    before = dict(nomad.files)
    result = dm.apply_correction("u", "t", _frame(ONE), "location", "HySpinbox", "X", "T")
    assert (result.success, result.failed) == (0, 1)
    assert nomad.files == before  # no correction, no log
    assert [p["path"].endswith(".bak") for p in nomad.puts] == [True]


def test_an_entry_changed_since_it_was_read_is_not_overwritten(monkeypatch):
    nomad = FakeNomad(ONE).install(monkeypatch)
    nomad.changed_meanwhile.add("E1")
    original = nomad.files[("U1", "sub/clean.archive.json")]
    result = dm.apply_correction("u", "t", _frame(ONE), "location", "HySpinbox", "X", "T")
    assert (result.success, result.failed) == (0, 1)
    assert nomad.files[("U1", "sub/clean.archive.json")] == original
    assert "changed since it was read" in result.details[0]["detail"]


def test_a_published_upload_is_never_written_or_backed_up(monkeypatch):
    nomad = FakeNomad(ONE, published={"U1"}).install(monkeypatch)
    result = dm.apply_correction("u", "t", _frame(ONE), "location", "HySpinbox", "X", "T")
    assert (result.success, result.failed) == (0, 1)
    assert nomad.puts == []
    preview = dm.preview_correction("u", "t", _frame(ONE), "location", "HySpinbox", "X", "T")
    assert preview[0]["status"] == "error" and "published" in preview[0]["detail"]


def test_only_archive_files_are_corrected(monkeypatch):
    entries = {"E1": ("U1", "plan.xlsx", "not json")}
    nomad = FakeNomad(entries).install(monkeypatch)
    result = dm.apply_correction("u", "t", _frame(entries), "location", "HySpinbox", "X", "T")
    assert (result.success, result.failed) == (0, 1)
    assert nomad.puts == []


def test_a_value_nomad_recomputes_while_processing_counts_as_failed(monkeypatch):
    nomad = FakeNomad(ONE).install(monkeypatch)
    nomad.processed_override["E1"] = {"location": "HySpinbox"}
    result = dm.apply_correction("u", "t", _frame(ONE), "location", "HySpinbox", "X", "T")
    assert (result.success, result.failed) == (0, 1)
    assert "NOMAD shows 'HySpinbox'" in result.details[0]["detail"]


def test_processing_that_does_not_finish_is_unverified_and_failed_processing_failed(monkeypatch):
    nomad = FakeNomad(ONE).install(monkeypatch)
    nomad.status = None
    result = dm.apply_correction("u", "t", _frame(ONE), "location", "HySpinbox", "X", "T")
    assert (result.success, result.unverified, result.failed) == (0, 0, 1)  # backup wait timed out

    nomad = FakeNomad(ONE).install(monkeypatch)
    statuses = iter(["SUCCESS", None])  # backup settled, correction still processing
    for module in (dm, upload_backups):  # the backup's wait, then the correction's
        monkeypatch.setattr(module, "wait_for_upload", lambda *a, **k: next(statuses))
    result = dm.apply_correction("u", "t", _frame(ONE), "location", "HySpinbox", "X", "T")
    assert (result.success, result.unverified, result.unverified_entry_ids) == (0, 1, ["E1"])

    nomad = FakeNomad(ONE).install(monkeypatch)
    statuses = iter(["SUCCESS", "FAILURE"])
    for module in (dm, upload_backups):  # the backup's wait, then the correction's
        monkeypatch.setattr(module, "wait_for_upload", lambda *a, **k: next(statuses))
    result = dm.apply_correction("u", "t", _frame(ONE), "location", "HySpinbox", "X", "T")
    assert (result.success, result.failed) == (0, 1)


def test_a_value_not_at_the_path_is_skipped_and_nothing_written(monkeypatch):
    nomad = FakeNomad(ONE).install(monkeypatch)
    nomad.files[("U1", "sub/clean.archive.json")] = _archive(location="Other")
    result = dm.apply_correction("u", "t", _frame(ONE), "location", "HySpinbox", "X", "T")
    assert (result.success, result.skipped) == (0, 1)
    assert nomad.puts == []


TWO_UPLOADS = {
    "E1": ("U1", "a.archive.json", _archive(location="HySpinbox")),
    "E2": ("U1", "b.archive.json", _archive(location="HySpinbox")),
    "E3": ("U2", "c.archive.json", _archive(location="HySpinbox")),
}


def test_one_failing_entry_does_not_stop_the_others_and_progress_is_reported(monkeypatch):
    nomad = FakeNomad(TWO_UPLOADS).install(monkeypatch)
    download = nomad.download

    def flaky(url, token, upload_id, path):
        if path == "a.archive.json":
            raise RuntimeError("network error")
        return download(url, token, upload_id, path)

    monkeypatch.setattr(dm, "download_raw_file", flaky)
    progress = []
    result = dm.apply_correction(
        "u",
        "t",
        _frame(TWO_UPLOADS),
        "location",
        "HySpinbox",
        "X",
        "T",
        progress_callback=lambda i, n: progress.append((i, n)),
    )
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert (result.success, result.failed, sorted(result.succeeded_entry_ids)) == (
        2,
        1,
        ["E2", "E3"],
    )


def test_only_entry_id_changes_a_single_entry(monkeypatch):
    nomad = FakeNomad(TWO_UPLOADS).install(monkeypatch)
    result = dm.apply_correction(
        "u", "t", _frame(TWO_UPLOADS), "location", "HySpinbox", "X", "T", only_entry_id="E2"
    )
    assert result.succeeded_entry_ids == ["E2"]
    assert json.loads(nomad.files[("U1", "a.archive.json")])["data"]["location"] == "HySpinbox"


def test_every_upload_gets_its_own_log_and_the_corrections_tab_reads_them_back(monkeypatch):
    nomad = FakeNomad(TWO_UPLOADS).install(monkeypatch)
    monkeypatch.setenv("NOMAD_CLIENT_USER", "tester")
    dm.apply_correction("u", "t", _frame(TWO_UPLOADS), "location", "HySpinbox", "X", "Spin")
    logs = {
        u: [p for p in nomad.data_paths(u) if p.endswith("_corrections.log")] for u in ("U1", "U2")
    }
    assert len(logs["U1"]) == len(logs["U2"]) == 1

    records = dm.read_correction_logs("u", "t", ["U1", "U2"])
    assert {r["upload_id"] for r in records} == {"U1", "U2"}
    assert all(r["user"] == "tester" and r["entry_type"] == "Spin" for r in records)
    table = gc.corrections_dataframe(records).set_index("Upload")
    assert table.loc["U1", "Entries verified"] == 2 and table.loc["U2", "Entries verified"] == 1
    assert table.loc["U1", "Wrong value"] == "HySpinbox" and table.loc["U1", "Corrected to"] == "X"


def test_preview_writes_nothing(monkeypatch):
    entries = {**TWO_UPLOADS, "E4": ("U1", "d.archive.json", _archive(location="Other"))}
    nomad = FakeNomad(entries).install(monkeypatch)
    df = _frame(entries)
    df.loc[df["_entry_id"] == "E4", "location"] = "HySpinbox"  # the table is out of date
    preview = dm.preview_correction("u", "t", df, "location", "HySpinbox", "X", "T")
    assert [item["status"] for item in preview] == ["change", "change", "change", "no_match"]
    assert nomad.puts == []


# ---------------------------------------------------------------------------
# GUI and app
# ---------------------------------------------------------------------------


def test_confirm_flow_changes_the_table_after_a_verified_correction(monkeypatch):
    """Nothing is written until Confirm; afterwards the table shows the new value and the
    result lists every entry."""
    session = dm.EntryAuditSession()
    assert session.load_offline(FIXTURE_PATH)
    label, column, old = "Cleaning", "location", "HySpinbox"
    df = session.datasets[label]
    targets = df[df[column] == old]
    entries = {
        row["_entry_id"]: (row["_upload_id"], row["_mainfile"], _archive(location=old))
        for _, row in targets.iterrows()
    }
    nomad = FakeNomad(entries).install(monkeypatch)

    panel = gc.FieldAuditPanel(session, label, url="https://e.test/api/v1", token="t")
    panel.dropdown.value = column
    panel.from_dropdown.value = old
    panel.to_input.value = "HySpinBox"

    panel._on_preview_click(None)
    assert nomad.puts == []  # a preview writes nothing
    assert panel.confirm_button.layout.display is None
    assert "will change" in panel.correct_out.value
    assert "entry_auditor_backups/" in panel.correct_out.value

    panel._on_confirm_click(None)
    assert nomad.puts, "confirm performs the write"
    assert "updated and verified" in panel.correct_out.value
    assert "verified" in panel.correct_out.value and "<table" in panel.correct_out.value
    assert not (session.datasets[label][column] == old).any()
    assert (session.datasets[label][column] == "HySpinBox").any()
    assert panel.confirm_button.layout.display == "none"


def test_a_rerun_of_initialize_ui_closes_the_previous_widgets(monkeypatch):
    from perotf_utils.widget_cleanup import live_widgets

    monkeypatch.setattr(gc, "create_entry_auditor_ui", lambda *args: gc.widgets.Label("ui"))
    first = app_module.initialize_ui(token="tok")
    first_ids = set(app_module._ui.widget_ids)
    assert first.model_id in first_ids
    second = app_module.initialize_ui(token="tok")
    assert not first_ids & set(live_widgets())
    assert second.model_id in live_widgets()


def test_the_app_starts_without_a_nomad_login_and_offers_the_demo(monkeypatch):
    class NoLogin:
        def __init__(self, url_base, api_endpoint):
            self.api_client = type("C", (), {"get_api_url": lambda self: "https://e.test/api"})()

        def authenticate_with_token(self, token):
            raise ValueError("Token not found")

    def must_not_query(*args, **kwargs):
        raise AssertionError("queried NOMAD without a token")

    monkeypatch.setattr(app_module, "AuthenticationManager", NoLogin)
    monkeypatch.setattr(gc, "create_batch_selection", must_not_query)
    ui = app_module.initialize_ui()
    tabs = ui.children[1]
    audit = tabs.children[0]
    assert any("Not logged in to NOMAD" in str(getattr(w, "value", "")) for w in audit.children)
    corrections = tabs.children[1]
    assert "Load batches in the" in corrections.children[2].value


def test_export_csv_starts_the_download_without_a_link(monkeypatch):
    session = dm.EntryAuditSession()
    session.datasets["Spin"] = pd.DataFrame({"_upload_id": ["U1"], "x": ["y"]})
    records = [{"time": "t", "user": "u", "field": "f", "from": "=a", "to": "A", "entries": []}]
    monkeypatch.setattr(gc, "read_correction_logs", lambda url, token, uploads: records)
    started = []
    monkeypatch.setattr(gc, "start_download", lambda *args: started.append(args))
    tab = gc.create_corrections_tab(session, "https://e.test/api", "tok")
    assert "=a" in tab.children[2].value
    tab.children[1].children[1].click()
    (output, content, filename, mime_type) = started[0]
    assert output is tab.children[-1] and filename == "corrections.csv"
    assert mime_type == "text/csv" and "'=a" in content
    assert "<a " not in tab.children[-2].value


def test_corrections_tab_escapes_values_from_nomad(monkeypatch):
    session = dm.EntryAuditSession()
    session.datasets["Spin"] = pd.DataFrame({"_upload_id": ["U1"]})
    records = [{"from": "<img src=x onerror=alert(1)>", "to": "ok", "entries": []}]
    monkeypatch.setattr(gc, "read_correction_logs", lambda url, token, uploads: records)
    tab = gc.create_corrections_tab(session, "https://e.test/api", "tok")
    assert "<img" not in tab.children[2].value and "&lt;img" in tab.children[2].value
