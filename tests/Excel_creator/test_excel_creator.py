"""Smoke tests for Excel_creator: modules import and the app builds without network or token."""

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
