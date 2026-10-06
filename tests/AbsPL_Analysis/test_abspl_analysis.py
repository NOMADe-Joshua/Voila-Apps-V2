"""Smoke tests for AbsPL_Analysis: modules import and the app builds without network or token."""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(mods):
    assert hasattr(mods["app"], "AbsPLAppController")
    assert hasattr(mods["app"], "launch_abspl_app")


def test_app_constructs_offline(mods, monkeypatch):
    from perotf_utils.config import API_ENDPOINT, URL_BASE

    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].AbsPLAppController()
    assert app is not None
    assert app.main_layout is not None
    assert app.auth_manager.url == f"{URL_BASE}{API_ENDPOINT}"
