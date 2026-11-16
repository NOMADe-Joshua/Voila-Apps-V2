"""Excel_creator: modules import, the app builds without network or token, the experiment sheet
writes the column names nomad_perotf's experiment parser reads, the process catalog agrees
with the sheet, templates are validated, and the optional prefill from NOMAD. The template
and prefill tests are ported from HZB's nomad-pv-analysis-apps. No network: the NOMAD calls
are replaced by fixtures."""

import io
import json

import pytest
from openpyxl import Workbook, load_workbook

from perotf_utils.config import API_ENDPOINT, GUI_ENDPOINT, URL_BASE
from perotf_utils.manual import read_manual
from perotf_utils.process_specs import PROCESSES

INFO_ONLY = [{"process": "Experiment Info", "config": {}}]
WITH_CLEANING = [*INFO_ONLY, {"process": "Cleaning O2-Plasma", "config": {"solvents": 1}}]

# What NOMAD holds for a fully described sample (the fields of peroTF_Sample and
# peroTF_Substrate that process_specs' Experiment Info paths read).
FULL_SAMPLE = {"number_of_junctions": 2, "description": "1000 rpm"}
FULL_SUBSTRATE = {
    "substrate": "Soda Lime Glass",
    "substrate_dimension": "2.5 cm x 2.5 cm",
    "solar_cell_area": 0.5,
    "number_of_pixels": 6,
    "pixel_area": 0.16,
    "conducting_material": ["ITO", "Ag"],
    "lab_id": "KIT_Bottom_20260101_1_1_1",
    "description": "fresh ITO",
}
FULL_EXPECTED = {
    "Variation": "1000 rpm",
    "Sample dimension": "2.5 cm x 2.5 cm",
    "Sample area [cm^2]": 0.5,
    "Number of pixels": 6,
    "Pixel area": 0.16,
    "Number of junctions": 2,
    "Substrate material": "Soda Lime Glass",
    "Substrate conductive layer": "ITO",
    "Bottom Cell Name": "KIT_Bottom_20260101_1_1_1",
    "Notes": "fresh ITO",
}


@pytest.fixture(autouse=True)
def _no_container_login(monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)


@pytest.fixture
def app_module(mods):
    return mods["voila_experiment_app"]


@pytest.fixture
def prefill(mods):
    return mods["nomad_prefill"]


def _sample(prefill, lab_id, fields=None):
    return prefill.PrefillSample(lab_id, dict(fields or {}))


def _source(lab_id="KIT_A_1", sample=None, substrate=None):
    return {"sample": {"lab_id": lab_id, **(sample or {})}, "substrate": substrate or {}}


def _sheet(mods, sequence, is_testing, samples):
    rows = None if samples is None else [s.as_row() for s in samples]
    builder = mods["experiment_excel_builder"].ExperimentExcelBuilder(
        sequence, is_testing=is_testing, samples=rows
    )
    builder.build_excel()
    return builder.workbook["Experiment Data"]


def _column(ws, header):
    return next(c.column for c in ws[2] if c.value == header)


def header_labels(mods, processes):
    wb = Workbook()
    mods["sheet_experiment"].add_experiment_sheet(
        wb, [{"process": process} for process in processes], is_testing=False
    )
    ws = wb.active
    return [ws.cell(row=2, column=col).value for col in range(1, ws.max_column + 1)]


# =============================================================================
# Modules, app, guide
# =============================================================================


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(app_module):
    assert hasattr(app_module, "MinimalistExperimentBuilder")
    assert app_module.EXCEL_BUILDER_AVAILABLE


def test_app_constructs_offline(app_module):
    app = app_module.MinimalistExperimentBuilder()
    # templates/process_templates.json is resolved next to the module, independent of the cwd
    assert app.templates
    assert app.current_sequence == [{"process": "Experiment Info"}]


def test_guide_sheet_links_to_configured_oasis(mods):
    wb = Workbook()
    mods["sheet_data_entry_guide"].add_guide_sheet(wb)
    links = [
        cell.hyperlink.target
        for row in wb["Data Entry Guide"].iter_rows()
        for cell in row
        if cell.hyperlink is not None
    ]
    assert f"{URL_BASE}{GUI_ENDPOINT}/search/voila" in links


def test_the_app_shows_its_manual_and_no_linter_comment(app_module, monkeypatch):
    """'# noqa: E501' sat inside HTML strings at HZB and was printed in the page."""
    app = app_module.MinimalistExperimentBuilder()
    shown = []
    monkeypatch.setattr(app_module, "display", shown.append)
    app.display()

    def widgets_in(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from widgets_in(child)

    texts = [w.value for w in widgets_in(shown[0]) if isinstance(getattr(w, "value", None), str)]
    assert texts and not [t for t in texts if "noqa" in t]
    assert "📖 Manual" in [getattr(w, "description", None) for w in widgets_in(shown[0])]
    assert "Prefill from NOMAD" in read_manual(app_module.__file__)


# =============================================================================
# The sheet's columns
# =============================================================================


def test_sheet_uses_the_corrected_column_names(mods):
    labels = header_labels(mods, ["Spin Coating", "Lamination", "Annealing"])
    assert labels.count("Annealing atmosphere") == 2
    assert "Annealing athmosphere" not in labels
    assert "Humidity [%rel]" in labels
    assert "Humidity [%%rel]" not in labels


def test_sheet_leaves_out_columns_nomad_does_not_store(mods):
    labels = header_labels(mods, ["Evaporation", "Close Space Sublimation"])
    assert "Power [%]" not in labels
    # Evaporation keeps "Organic": it decides where the source is stored
    assert labels.count("Organic") == 1


def test_laser_scribing_is_not_offered(app_module):
    app = app_module.MinimalistExperimentBuilder()
    assert "Laser Scribing" not in app.available_processes


def _catalog_labels(process, config):
    spec = PROCESSES[process]
    labels = list(spec.get("fields", {}))
    for key, group in spec.get("indexed", {}).items():
        for n in range(1, config.get(key, 0) + 1):
            labels += [entry["excel_key"].format(n=n) for entry in group]
    for key, block in spec.get("optional", {}).items():
        if config.get(key):
            labels += list(block)
    return labels


def _configs(meta):
    """The defaults, then every count at 1, 2 and 3 with every optional block on, then each
    choice option."""
    configs = [dict(meta.get("config_defaults", {}))]
    for count in (1, 2, 3):
        config = dict(meta.get("config_defaults", {}))
        for key, _label, low, high in meta.get("numeric_config", []):
            config[key] = max(low, min(high, count))
        config.update({key: True for key, _label in meta.get("boolean_config", [])})
        configs.append(config)
    for key, _label, options in meta.get("choice_config", []):
        configs += [{**configs[-1], key: option} for option in options]
    return configs


def _known_difference(process, config, only_in_sheet, only_in_catalog):
    """The three places where the sheet does more than the catalog can describe."""
    if process == "Spin Coating":
        # One spin step gets unnumbered columns, several get numbered ones; the catalog
        # lists both spellings.
        steps = config.get("spinsteps", 1)
        unnumbered = {"Rotation speed [rpm]", "Rotation time [s]", "Acceleration [rpm/s]"}
        numbered = {"Rotation speed 1 [rpm]", "Rotation time 1 [s]", "Acceleration 1 [rpm/s]"}
        return not only_in_sheet and set(only_in_catalog) == (unnumbered if steps > 1 else numbered)
    if process == "Inkjet Printing":
        # The waveform columns depend on the printer type and the pulse count.
        return not only_in_catalog and all(label.startswith("Wf ") for label in only_in_sheet)
    if process == "Close Space Sublimation":
        # The ratio columns only exist with more than one source material.
        return not only_in_sheet and only_in_catalog == ["Source material ratio 1"]
    return False


@pytest.mark.parametrize("process", list(PROCESSES))
def test_the_catalog_lists_the_columns_the_sheet_writes(mods, process):
    """perotf_utils.process_specs drives the app's process list, its controls and the
    prefill; sheet_experiment writes the columns inline. The two must agree."""
    for config in _configs(PROCESSES[process]["meta"]):
        wb = Workbook()
        mods["sheet_experiment"].add_experiment_sheet(
            wb, [{"process": process, "config": dict(config)}], is_testing=False
        )
        ws = wb.active
        sheet = [cell.value for cell in ws[2] if cell.value is not None]
        catalog = _catalog_labels(process, config)
        only_in_sheet = [label for label in sheet if label not in catalog]
        only_in_catalog = [label for label in catalog if label not in sheet]
        if only_in_sheet or only_in_catalog:
            assert _known_difference(process, config, only_in_sheet, only_in_catalog), (
                process,
                config,
                only_in_sheet,
                only_in_catalog,
            )


def test_the_nomad_id_formula_is_written_to_every_data_row(mods):
    ws = _sheet(mods, INFO_ONLY, False, None)
    sheet_experiment = mods["sheet_experiment"]
    assert ws["F3"].value == ('=IF(B3="","",CONCATENATE("KIT_",B3,"_",A3,"_",C3,"_",D3,"_",E3))')
    last = sheet_experiment.NOMAD_ID_LAST_ROW
    assert ws[f"F{last}"].value == sheet_experiment.nomad_id_formula(last)
    assert ws[f"F{last + 1}"].value is None


def test_generated_excel_has_example_row_and_nomad_id_formula(app_module):
    """Row 3 carries example values and the Nomad ID formula (no checkbox)."""
    app = app_module.MinimalistExperimentBuilder()
    ws = load_workbook(io.BytesIO(app._generate_excel_data()))["Experiment Data"]
    assert ws["A2"].value == "Date"
    assert ws["A3"].value == "YYYYMMDD"
    assert ws["F3"].value.startswith('=IF(B3="","",CONCATENATE("KIT_"')


# =============================================================================
# Process rows: controls and configs from the catalog
# =============================================================================


def test_inkjet_printing_offers_type_and_pulses(app_module):
    app = app_module.MinimalistExperimentBuilder()
    app.current_sequence.append({"process": "Inkjet Printing", "config": {}})
    numeric, checkboxes = app._create_inline_config_controls(
        1, "Inkjet Printing", {"pixORnotion": "Notion", "Wf Number of Pulses": 2}
    )
    by_label = {w.description: w for w in numeric}
    assert by_label["Pulses:"].value == 2 and by_label["Pulses:"].max == 3
    assert list(by_label["Type:"].options) == ["Pixdro", "Notion"]
    assert by_label["Type:"].value == "Notion"
    by_label["Type:"].value = "Pixdro"
    assert app.current_sequence[1]["config"]["pixORnotion"] == "Pixdro"
    assert {c.description for c in checkboxes} == {"Gas Quenching", "Vacuum Quenching"}


def test_no_atmospheric_checkbox_without_a_catalog_block(app_module):
    _numeric, checkboxes = app_module.MinimalistExperimentBuilder()._create_inline_config_controls(
        1, "Spin Coating", {}
    )
    assert "Add Atmospheric Values" not in {c.description for c in checkboxes}


def test_changing_to_co_evaporation_gets_its_default_config(app_module):
    app = app_module.MinimalistExperimentBuilder()
    app.current_sequence.append({"process": "Generic Process"})
    app._update_process_type(1, "Co-Evaporation")
    assert app.current_sequence[1]["config"] == {"materials": 2}


def test_changing_to_a_process_without_config_drops_it(app_module):
    app = app_module.MinimalistExperimentBuilder()
    app.current_sequence.append({"process": "Spin Coating", "config": {"solvents": 2}})
    app._update_process_type(1, "Annealing")
    assert "config" not in app.current_sequence[1]


def test_a_shown_default_is_also_generated(app_module):
    """A template step without "spinsteps" showed "Steps: 1" and generated no rotation
    columns at HZB; the shown value is now written into the config."""
    app = app_module.MinimalistExperimentBuilder()
    app.current_sequence = [
        {"process": "Experiment Info"},
        {"process": "Spin Coating", "config": {"solvents": 1}},
        {"process": "Inkjet Printing", "config": {}},
    ]
    app._update_process_display()
    assert app.current_sequence[1]["config"]["spinsteps"] == 1
    assert app.current_sequence[2]["config"]["pixORnotion"] == "Pixdro"
    assert app.current_sequence[2]["config"]["Wf Number of Pulses"] == 1


@pytest.mark.parametrize("process", sorted(app for app in PROCESSES if app != "Experiment Info"))
def test_a_step_without_settings_generates_what_the_sheet_did_before(mods, app_module, process):
    """A template step without a config gets the catalog defaults, which are the fallbacks
    sheet_experiment itself uses (one solvent, two co-evaporation materials, ...), not the
    minimum of each control (HZB's sheet falls back to 0, ours does not)."""
    app = app_module.MinimalistExperimentBuilder()
    app.current_sequence = [{"process": "Experiment Info"}, {"process": process}]
    app._update_process_display()
    ws = load_workbook(io.BytesIO(app._generate_excel_data()))["Experiment Data"]
    generated = [cell.value for cell in ws[2] if cell.value is not None]
    assert generated == header_labels(mods, ["Experiment Info", process])


# =============================================================================
# Templates
# =============================================================================


def _shipped_templates(app_module):
    with open(app_module.DEFAULT_TEMPLATES_FILE, encoding="utf-8") as f:
        return json.load(f)["templates"]


def test_every_shipped_template_is_valid_and_uses_known_settings(app_module):
    for key, template in _shipped_templates(app_module).items():
        assert app_module.validate_template(template) == [], key
        for step in template["process_sequence"]:
            unknown = set(step.get("config", {})) - app_module._known_config_keys(step["process"])
            assert not unknown, (key, step["process"], unknown)


def test_every_shipped_template_applies_and_generates(app_module):
    app = app_module.MinimalistExperimentBuilder()
    assert len(app.templates) == len(_shipped_templates(app_module))
    for template in app.templates.values():
        app.template_dropdown.value = template["name"]
        app._on_apply_template(None)
        assert len(app.current_sequence) == len(template["process_sequence"])
        assert app._generate_excel_data().startswith(b"PK")


def test_validate_template_names_the_problem(app_module):
    validate = app_module.validate_template
    assert validate("x") == ["it is not a template entry"]
    assert "it has no name" in validate({"process_sequence": [{"process": "Experiment Info"}]})
    assert validate({"name": "n"}) == ["it has no process_sequence"]
    assert validate({"name": "n", "process_sequence": [{"process": "Laser Scribing"}]}) == [
        "step 1 uses the unknown process 'Laser Scribing'"
    ]


def test_an_unreadable_templates_file_is_not_overwritten(app_module, tmp_path):
    broken = tmp_path / "process_templates.json"
    broken.write_text("{not json", encoding="utf-8")
    app = app_module.MinimalistExperimentBuilder(broken)
    assert broken.read_text(encoding="utf-8") == "{not json"
    assert set(app.templates) == set(app_module.default_templates())


def test_a_missing_templates_file_is_not_created(app_module, tmp_path):
    missing = tmp_path / "templates.json"
    app = app_module.MinimalistExperimentBuilder(missing)
    assert not missing.exists()
    assert app.templates


def test_an_invalid_template_is_left_out_and_the_others_survive(app_module, tmp_path):
    path = tmp_path / "process_templates.json"
    templates = {
        "good": {"name": "Good", "process_sequence": [{"process": "Experiment Info"}]},
        "bad": {"name": "Bad", "process_sequence": [{"process": "Teleportation"}]},
    }
    path.write_text(json.dumps({"templates": templates}), encoding="utf-8")
    app = app_module.MinimalistExperimentBuilder(path)
    assert list(app.templates) == ["good"]
    assert "Bad" not in app.template_dropdown.options


def test_applying_a_template_drops_settings_the_process_does_not_have(app_module, tmp_path):
    path = tmp_path / "process_templates.json"
    sequence = [
        {"process": "Experiment Info"},
        {"process": "Close Space Sublimation", "config": {"materials": 2, "mixing_ratio": True}},
    ]
    path.write_text(json.dumps({"templates": {"t": {"name": "T", "process_sequence": sequence}}}))
    app = app_module.MinimalistExperimentBuilder(path)
    app.template_dropdown.value = "T"
    app._on_apply_template(None)
    assert app.current_sequence[1]["config"] == {"materials": 2}


def test_a_failed_generation_shows_the_error_and_offers_no_download(
    app_module, monkeypatch, capsys
):
    app = app_module.MinimalistExperimentBuilder()

    def broken(samples=None):
        raise RuntimeError("disk full")

    monkeypatch.setattr(app, "_generate_excel_data", broken)
    downloads = []
    monkeypatch.setattr(app_module, "start_download", lambda *a, **k: downloads.append(a))
    app._on_generate_excel(None)
    assert downloads == []
    # outside a kernel the Output widget passes its prints through to stdout
    assert "could not be generated: disk full" in capsys.readouterr().out


def test_generate_starts_the_download(app_module, monkeypatch):
    app = app_module.MinimalistExperimentBuilder()
    downloads = []
    monkeypatch.setattr(
        app_module, "start_download", lambda *args, **kwargs: downloads.append((args, kwargs))
    )
    app._on_generate_excel(None)
    [(args, kwargs)] = downloads
    output, content, filename, mime = args
    assert output is app.download_output
    assert content.startswith(b"PK") and filename.endswith(".xlsx")
    assert mime == app_module.XLSX_MIME
    assert filename in kwargs["note"]


# =============================================================================
# nomad_prefill: what is taken from NOMAD
# =============================================================================


def test_every_mapped_experiment_info_column_is_taken(prefill):
    source = _source(sample=FULL_SAMPLE, substrate=FULL_SUBSTRATE)
    assert prefill.info_fields(source) == FULL_EXPECTED


def test_the_field_list_comes_from_process_specs(prefill):
    """Columns without an archive path are never filled from NOMAD."""
    assert set(FULL_EXPECTED) == set(prefill.INFO_FIELD_PATHS)
    for key in ("Date", "Project_Name", "Batch", "Subbatch", "Sample", "Nomad ID"):
        assert key not in prefill.INFO_FIELD_PATHS


@pytest.mark.parametrize(
    "substrate",
    [
        {"conducting_material": []},
        {"conducting_material": "ITO"},  # not a list: index 0 is not taken from a string
        {"substrate": ""},
        {"substrate": "   "},
        {"number_of_pixels": True},
        {"substrate_dimension": {"value": 1}},
    ],
)
def test_missing_empty_or_odd_values_are_left_out(prefill, substrate):
    assert prefill.info_fields(_source(substrate=substrate)) == {}


def test_zero_is_a_value(prefill):
    fields = prefill.info_fields(_source(sample={"number_of_junctions": 0}))
    assert fields == {"Number of junctions": 0}


def test_a_confirmed_unit_factor_is_applied(prefill, monkeypatch):
    monkeypatch.setattr(prefill, "INFO_MULTIPLIERS", {"Sample area [cm^2]": 100})
    fields = prefill.info_fields(_source(substrate={"solar_cell_area": 0.5}))
    assert fields["Sample area [cm^2]"] == 50


def test_samples_are_sorted_and_sources_without_lab_id_skipped(prefill):
    sources = [
        _source("KIT_B_1", substrate={"substrate": "FTO glass"}),
        {"sample": {}, "substrate": {"substrate": "ignored"}},
        {"sample": None, "substrate": {}},
        _source("KIT_A_1"),
    ]
    assert prefill.samples_from_sources(sources) == [
        _sample(prefill, "KIT_A_1"),
        _sample(prefill, "KIT_B_1", {"Substrate material": "FTO glass"}),
    ]


@pytest.mark.parametrize(
    "lab_id, parts",
    [
        ("KIT_JoDa_20261103_1_1_1", ("20261103", "JoDa", "1", "1", "1")),
        ("KIT_AnAl_26-02-2025_1_2_1", ("26-02-2025", "AnAl", "1", "2", "1")),
        ("KIT_Green Ink_20260101_6_2_14", ("20260101", "Green Ink", "6", "2", "14")),
        ("KIT_IJP_Green_Ink_20260101_6_A_3", ("20260101", "IJP_Green_Ink", "6", "A", "3")),
    ],
)
def test_a_formula_lab_id_is_read_back_into_its_columns(prefill, lab_id, parts):
    parsed = prefill.parse_lab_id(lab_id)
    assert tuple(parsed[key] for key in prefill.LAB_ID_COLUMNS) == parts
    # the parts rebuild exactly the same ID, as the sheet's Nomad ID formula would
    date, project, batch, subbatch, sample = parts
    assert f"KIT_{project}_{date}_{batch}_{subbatch}_{sample}" == lab_id


@pytest.mark.parametrize(
    "lab_id",
    [
        "KIT_A_1",  # too few parts
        "HZB_JoDa_20261103_1_1_1",  # another prefix
        "KIT_JoDa_20261103_1_1",  # no sample
        "KIT__20261103_1_1_1",  # empty project
        "KIT_JoDa_20261103_1_1_",  # empty sample
        "sample 12",
    ],
)
def test_a_lab_id_not_made_by_the_formula_fills_no_columns(prefill, lab_id):
    assert prefill.parse_lab_id(lab_id) == {}


def test_samples_get_the_columns_of_their_lab_id(prefill):
    [sample] = prefill.samples_from_sources(
        [_source("KIT_JoDa_20261103_3_2_7", substrate={"substrate": "Glass"})]
    )
    assert sample.fields == {
        "Date": "20261103",
        "Project_Name": "JoDa",
        "Batch": "3",
        "Subbatch": "2",
        "Sample": "7",
        "Substrate material": "Glass",
    }
    assert prefill.filled_columns([sample]) == [
        "Date",
        "Project_Name",
        "Batch",
        "Subbatch",
        "Sample",
        "Nomad ID",
        "Substrate material",
    ]


def test_parsed_lab_id_columns_land_in_the_sheet(mods, prefill):
    [sample] = prefill.samples_from_sources([_source("KIT_JoDa_20261103_3_2_7")])
    ws = _sheet(mods, INFO_ONLY, False, [sample])
    row = {header: ws.cell(3, _column(ws, header)).value for header in prefill.LAB_ID_COLUMNS}
    assert row == {
        "Date": "20261103",
        "Project_Name": "JoDa",
        "Batch": "3",
        "Subbatch": "2",
        "Sample": "7",
    }
    assert ws.cell(3, _column(ws, "Nomad ID")).value == "KIT_JoDa_20261103_3_2_7"


def test_filled_columns_lists_what_any_sample_has_in_sheet_order(prefill):
    samples = [
        _sample(prefill, "a", {"Number of junctions": 1}),
        _sample(prefill, "b", {"Substrate material": "Glass"}),
    ]
    assert prefill.filled_columns(samples) == [
        "Nomad ID",
        "Number of junctions",
        "Substrate material",
    ]


def test_upload_choices_tell_duplicate_names_apart_and_fall_back_to_the_id(prefill):
    uploads = [
        {"upload_id": "id1", "upload_name": "Batch 7"},
        {"upload_id": "id2", "upload_name": "Batch 7"},
        {"upload_id": "id3"},
        {"upload_id": "id4", "upload_name": "Other"},
    ]
    assert prefill.upload_choices(uploads) == [
        ("Batch 7 (id1)", "id1"),
        ("Batch 7 (id2)", "id2"),
        ("id3", "id3"),
        ("Other", "id4"),
    ]


def test_fetch_samples_uses_the_shared_query(prefill, monkeypatch):
    calls = []

    def fake(url, token, upload_id):
        calls.append((url, token, upload_id))
        return [_source("KIT_A_1", substrate={"substrate": "ITO glass"})]

    monkeypatch.setattr(prefill, "get_samples_with_substrates", fake)
    samples = prefill.fetch_samples_in_upload("https://oasis/api", "tok", "up1")
    assert calls == [("https://oasis/api", "tok", "up1")]
    assert samples == [_sample(prefill, "KIT_A_1", {"Substrate material": "ITO glass"})]


def test_connect_uses_the_container_token(prefill, monkeypatch):
    monkeypatch.setenv("NOMAD_CLIENT_ACCESS_TOKEN", "abc")
    url, token = prefill.connect()
    assert token == "abc"
    assert url == URL_BASE + API_ENDPOINT


def test_connect_without_a_token_raises(prefill, monkeypatch):
    def no_login(*args, **kwargs):
        raise RuntimeError("no token file and no terminal to ask for a password")

    monkeypatch.setattr("perotf_utils.access_token.get_token", no_login)
    with pytest.raises(ValueError, match="Token not found"):
        prefill.connect()


# =============================================================================
# nomad_prefill: the sheet
# =============================================================================


@pytest.fixture
def two_samples(prefill):
    return [
        _sample(prefill, "KIT_A_20261103_1_1_1", FULL_EXPECTED),
        _sample(prefill, "KIT_A_20261103_1_1_2"),
    ]


@pytest.mark.parametrize("is_testing, first_row", [(False, 3), (True, 4)])
def test_samples_fill_their_columns_below_the_example_row(mods, two_samples, is_testing, first_row):
    ws = _sheet(mods, WITH_CLEANING, is_testing, two_samples)
    nomad_col = _column(ws, "Nomad ID")
    assert ws.cell(first_row, nomad_col).value == "KIT_A_20261103_1_1_1"
    for header, value in FULL_EXPECTED.items():
        assert ws.cell(first_row, _column(ws, header)).value == value, header
    assert ws.cell(first_row + 1, nomad_col).value == "KIT_A_20261103_1_1_2"
    # a sample NOMAD knows nothing more about leaves the other columns empty
    assert ws.cell(first_row + 1, _column(ws, "Substrate material")).value is None
    # the row after the samples keeps its formula
    assert str(ws.cell(first_row + 2, nomad_col).value).startswith("=IF(")


def test_samples_write_nothing_into_the_process_columns(mods, two_samples):
    ws = _sheet(mods, WITH_CLEANING, False, two_samples)
    first_process_column = _column(ws, "Notes") + 1  # Experiment Info ends with Notes
    for row in ws.iter_rows(min_row=3, min_col=first_process_column):
        assert all(cell.value is None for cell in row)


def test_samples_are_written_beyond_the_formula_rows(mods, prefill):
    many = [_sample(prefill, f"S{i:04d}") for i in range(600)]
    ws = _sheet(mods, INFO_ONLY, False, many)
    assert ws.cell(602, _column(ws, "Nomad ID")).value == "S0599"


def test_an_unknown_header_in_a_row_is_ignored(mods):
    builder = mods["experiment_excel_builder"].ExperimentExcelBuilder(
        INFO_ONLY, is_testing=False, samples=[{"Nomad ID": "X", "Not a column": "?"}]
    )
    builder.build_excel()
    ws = builder.workbook["Experiment Data"]
    assert ws.cell(3, _column(ws, "Nomad ID")).value == "X"
    assert "?" not in [c.value for row in ws.iter_rows() for c in row]


@pytest.mark.parametrize("samples", [None, []])
def test_without_samples_the_sheet_is_unchanged(mods, samples):
    plain = mods["experiment_excel_builder"].ExperimentExcelBuilder(WITH_CLEANING, is_testing=True)
    plain.build_excel()
    ws = _sheet(mods, WITH_CLEANING, True, samples)
    expected = plain.workbook["Experiment Data"]
    assert [[c.value for c in row] for row in ws.iter_rows()] == [
        [c.value for c in row] for row in expected.iter_rows()
    ]


def test_samples_without_an_experiment_info_step_raise(mods, two_samples):
    with pytest.raises(ValueError, match="Nomad ID"):
        _sheet(mods, [{"process": "Annealing", "config": {}}], False, two_samples)


# =============================================================================
# nomad_prefill: the app's hidden panel
# =============================================================================

UPLOADS = [{"upload_id": "up1", "upload_name": "Batch 7"}, {"upload_id": "up2"}]


@pytest.fixture
def fake_nomad(prefill, two_samples, monkeypatch):
    """Replaces every NOMAD call of nomad_prefill; records what was called."""
    calls = []

    def connect():
        calls.append("connect")
        return "https://oasis/api", "tok"

    def fetch_uploads(url, token):
        calls.append("uploads")
        return UPLOADS

    def fetch_samples(url, token, upload_id):
        calls.append(("samples", upload_id))
        return list(two_samples)

    monkeypatch.setattr(prefill, "connect", connect)
    monkeypatch.setattr(prefill, "fetch_uploads", fetch_uploads)
    monkeypatch.setattr(prefill, "fetch_samples_in_upload", fetch_samples)
    return calls


def _generated_sheet(app_module, app, monkeypatch):
    built = []
    real = app_module.ExperimentExcelBuilder

    def recording(*args, **kwargs):
        builder = real(*args, **kwargs)
        built.append(builder)
        return builder

    monkeypatch.setattr(app_module, "ExperimentExcelBuilder", recording)
    monkeypatch.setattr(app_module, "start_download", lambda *a, **k: None)
    app._on_generate_excel(None)
    [builder] = built
    return builder.workbook["Experiment Data"]


def test_the_app_uses_the_same_prefill_module(app_module, prefill):
    assert app_module.nomad_prefill is prefill


def test_the_prefill_panel_is_hidden_and_nothing_is_fetched_at_start(app_module, fake_nomad):
    app = app_module.MinimalistExperimentBuilder()
    assert app.prefill_panel.layout.display == "none"
    assert fake_nomad == []


def test_the_panel_says_where_to_upload_and_what_is_kept(app_module):
    app = app_module.MinimalistExperimentBuilder()
    assert app.prefill_note in app.prefill_panel.children
    assert "same upload" in app.prefill_note.value
    assert "kept as they are" in app.prefill_note.value


def test_opening_the_panel_loads_the_uploads_once(app_module, fake_nomad):
    app = app_module.MinimalistExperimentBuilder()
    app.prefill_toggle.value = True
    assert app.prefill_panel.layout.display != "none"
    assert list(app.prefill_upload_dropdown.options) == [
        (app.PREFILL_PLACEHOLDER, None),
        ("Batch 7", "up1"),
        ("up2", "up2"),
    ]
    assert app.prefill_upload_dropdown.value is None
    app.prefill_toggle.value = False
    app.prefill_toggle.value = True
    assert fake_nomad == ["connect", "uploads"]


def test_choosing_an_upload_loads_its_samples_and_names_the_columns(
    app_module, fake_nomad, two_samples
):
    app = app_module.MinimalistExperimentBuilder()
    app.prefill_toggle.value = True
    app.prefill_upload_dropdown.value = "up1"
    assert fake_nomad[-1] == ("samples", "up1")
    assert app.prefill_samples == two_samples
    assert "2 samples" in app.prefill_info.value
    assert "Substrate conductive layer" in app.prefill_info.value


def test_generate_prefills_without_an_example_row_while_the_panel_is_open(
    app_module, fake_nomad, monkeypatch
):
    """A prefilled file is meant to be uploaded, and an example row left in it would become
    a sample."""
    app = app_module.MinimalistExperimentBuilder()
    app.prefill_toggle.value = True
    app.prefill_upload_dropdown.value = "up1"
    ws = _generated_sheet(app_module, app, monkeypatch)
    assert ws.cell(3, _column(ws, "Nomad ID")).value == "KIT_A_20261103_1_1_1"
    assert ws.cell(3, _column(ws, "Number of pixels")).value == 6
    assert ws.cell(4, _column(ws, "Nomad ID")).value == "KIT_A_20261103_1_1_2"


def test_closing_the_panel_turns_the_prefill_off(app_module, fake_nomad, monkeypatch):
    app = app_module.MinimalistExperimentBuilder()
    app.prefill_toggle.value = True
    app.prefill_upload_dropdown.value = "up1"
    app.prefill_toggle.value = False
    ws = _generated_sheet(app_module, app, monkeypatch)
    assert str(ws.cell(3, _column(ws, "Nomad ID")).value).startswith("=IF(")
    assert ws.cell(3, _column(ws, "Date")).value == "YYYYMMDD"  # the example row is back


def test_a_failed_upload_list_is_shown_and_retried_on_the_next_opening(
    app_module, prefill, fake_nomad, monkeypatch
):
    def no_token():
        raise ValueError("Token not found")

    working_connect = prefill.connect  # the fake_nomad one
    monkeypatch.setattr(prefill, "connect", no_token)
    app = app_module.MinimalistExperimentBuilder()
    app.prefill_toggle.value = True
    assert "Token not found" in app.prefill_info.value
    assert list(app.prefill_upload_dropdown.options) == [(app.PREFILL_PLACEHOLDER, None)]
    monkeypatch.setattr(prefill, "connect", working_connect)
    app.prefill_toggle.value = False
    app.prefill_toggle.value = True
    assert len(app.prefill_upload_dropdown.options) == 3


def test_a_failed_sample_query_is_shown_and_nothing_is_prefilled(
    app_module, prefill, fake_nomad, monkeypatch
):
    def broken(url, token, upload_id):
        raise RuntimeError("HTTP 500")

    app = app_module.MinimalistExperimentBuilder()
    app.prefill_toggle.value = True
    monkeypatch.setattr(prefill, "fetch_samples_in_upload", broken)
    app.prefill_upload_dropdown.value = "up1"
    assert "HTTP 500" in app.prefill_info.value
    assert app.prefill_samples == []


def test_going_back_to_the_placeholder_clears_the_samples(app_module, fake_nomad):
    app = app_module.MinimalistExperimentBuilder()
    app.prefill_toggle.value = True
    app.prefill_upload_dropdown.value = "up1"
    app.prefill_upload_dropdown.value = None
    assert app.prefill_samples == []
    assert app._samples_to_prefill() == []


def test_sample_names_are_escaped_in_the_info_line(app_module, prefill, fake_nomad, monkeypatch):
    monkeypatch.setattr(
        prefill,
        "fetch_samples_in_upload",
        lambda url, token, upload_id: [_sample(prefill, "<b>x</b>")],
    )
    app = app_module.MinimalistExperimentBuilder()
    app.prefill_toggle.value = True
    app.prefill_upload_dropdown.value = "up1"
    assert "<b>x</b>" not in app.prefill_info.value
    assert "&lt;b&gt;x&lt;/b&gt;" in app.prefill_info.value
