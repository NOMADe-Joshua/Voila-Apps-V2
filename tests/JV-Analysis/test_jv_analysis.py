"""Smoke tests for JV-Analysis: modules import and the app builds without network or token."""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(mods):
    assert hasattr(mods["app"], "JVAnalysisApp")


def test_auth_manager_uses_central_config(mods):
    from perotf_utils.config import API_ENDPOINT, URL_BASE

    manager = mods["app"].SimpleAuthManager(URL_BASE, API_ENDPOINT)
    assert manager.url == f"{URL_BASE}{API_ENDPOINT}"


def test_app_constructs_offline(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].JVAnalysisApp()
    assert app is not None
    assert app.get_dashboard() is not None
    assert not app.auth_manager.is_authenticated()
