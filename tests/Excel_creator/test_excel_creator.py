"""Excel_creator: modules import, the app builds without network or token, and the experiment
sheet writes the column names nomad_perotf's experiment parser reads."""

from openpyxl import Workbook

from perotf_utils.config import GUI_ENDPOINT, URL_BASE


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(mods):
    assert hasattr(mods["voila_experiment_app"], "MinimalistExperimentBuilder")
    assert mods["voila_experiment_app"].EXCEL_BUILDER_AVAILABLE


def test_app_constructs_offline(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["voila_experiment_app"].MinimalistExperimentBuilder()
    assert app is not None
    # process_templates.json is resolved next to the module, independent of the cwd
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


def header_labels(mods, processes):
    wb = Workbook()
    mods["sheet_experiment"].add_experiment_sheet(
        wb, [{"process": process} for process in processes], is_testing=False
    )
    ws = wb.active
    return [ws.cell(row=2, column=col).value for col in range(1, ws.max_column + 1)]


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


def test_laser_scribing_is_not_offered(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["voila_experiment_app"].MinimalistExperimentBuilder()
    assert "Laser Scribing" not in app.available_processes
    assert "Laser Scribing" not in app.process_config_function()
