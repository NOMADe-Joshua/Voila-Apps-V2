"""Smoke tests for EQE_Analysis: modules import and the app builds without network or token."""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(mods):
    assert hasattr(mods["app"], "EQEAnalysisApp")


def test_batch_selection_uses_shared_api_calls(mods):
    from perotf_utils.api_calls import get_batch_ids

    assert mods["batch_selection"].get_batch_ids is get_batch_ids


def test_am15g_spectrum_loads_from_app_folder(mods):
    energy, flux = mods["plot_manager"]._get_am15g()
    assert len(energy) > 0
    assert len(energy) == len(flux)


def test_app_constructs_offline(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].EQEAnalysisApp()
    assert app is not None
    assert app.get_dashboard() is not None
    assert app.auth_manager.url.endswith(app.auth_manager.api_endpoint)
