"""Smoke tests for UVVis_Analyzer: modules import and the app builds without network or token."""

from perotf_utils.config import API_ENDPOINT, URL_BASE


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(mods):
    assert hasattr(mods["app"], "UVVisAnalysisApp")


def test_gui_components_reuse_common_widgets(mods):
    gui = mods["gui_components"]
    assert issubclass(gui.UVVisAuthenticationUI, mods["common_widgets"].AuthenticationUI)


def test_app_constructs_offline(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].UVVisAnalysisApp()
    assert app is not None
    assert app.auth_manager.url == f"{URL_BASE}{API_ENDPOINT}"
    assert not app.auth_manager.is_authenticated()
    assert app.get_dashboard() is not None


def test_settings_show_configured_api_url(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    app = mods["app"].UVVisAnalysisApp()
    shown = [w.value for w in app.auth_ui.settings_content.children if hasattr(w, "value")]
    assert any(f"{URL_BASE}{API_ENDPOINT}" in str(v) for v in shown)
