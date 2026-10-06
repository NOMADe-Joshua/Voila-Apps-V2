"""Smoke tests for DesignOfExperiments: modules import, the app builds offline."""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(mods):
    assert hasattr(mods["app"], "DoEApplication")


def test_app_constructs_offline(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].DoEApplication()
    assert app is not None
    assert app.main_interface is not None
    assert app.sampling_engine.get_available_algorithms()
    assert isinstance(app.get_status(), dict)
