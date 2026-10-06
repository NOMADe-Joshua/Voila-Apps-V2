"""Smoke tests for XRD_PF: modules import and the app builds without network or token."""

from perotf_utils.config import API_ENDPOINT, URL_BASE


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(mods):
    assert hasattr(mods["app"], "XRDAnalysisApp")


def test_app_local_config_is_not_perotf_config(mods):
    assert hasattr(mods["config"], "DEBUG_MODE")


def test_app_constructs_offline(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].XRDAnalysisApp()
    assert app is not None
    assert app.auth_manager.url == f"{URL_BASE}{API_ENDPOINT}"
    assert not app.auth_manager.is_authenticated()
    assert app.get_dashboard() is not None
