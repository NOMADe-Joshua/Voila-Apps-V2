"""Smoke tests for Process_JV_Overview: modules import, the app builds offline."""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(mods):
    assert hasattr(mods["app"], "ProcessJVOverviewApp")


def test_entry_type_comes_from_central_config(mods):
    from perotf_utils.config import ENTRY_TYPES

    assert mods["app"].JV_ENTRY_TYPE == ENTRY_TYPES["jv"]


def test_app_constructs_offline(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].ProcessJVOverviewApp()
    assert app is not None
    assert app.get_dashboard() is not None
