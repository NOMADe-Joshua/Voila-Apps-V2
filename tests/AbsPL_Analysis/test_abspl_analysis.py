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


def _entry(n_results, notes="", flux=True):
    results = [
        {
            "wavelength": [700.0 + k for k in range(10)],
            "luminescence_flux_density": [1.0] * 10 if flux else None,
            "raw_spectrum_counts": [2.0] * 10,
            "laser_intensity_suns": 0.1 * (i + 1),
        }
        for i in range(n_results)
    ]
    return {"name": "e", "results": results}, {"description_notes": notes, "upload_name": "up"}


def _loaded_manager(mods, monkeypatch, entries):
    dm_mod = mods["data_manager"]

    class _Auth:
        url = "http://x"
        current_token = "t"

        def is_authenticated(self):
            return True

    monkeypatch.setattr(dm_mod, "get_ids_in_batch", lambda *a, **k: ["S1"])
    monkeypatch.setattr(dm_mod, "get_sample_description", lambda *a, **k: {"S1": "desc"})
    monkeypatch.setattr(dm_mod, "get_all_eqe", lambda *a, **k: {"S1": entries})
    dm = dm_mod.AbsPLDataManager(_Auth())
    assert dm.load_batch_data(["b"])
    return dm


def test_cycle_and_sweep_step_are_separate(mods, monkeypatch):
    entries = [
        _entry(1, "Cycle_1"),
        _entry(3, "Cycle_2", flux=False),
        _entry(3, "Cycle_3", flux=False),
    ]
    summary = _loaded_manager(mods, monkeypatch, entries).get_data()["summary"]

    pl = summary[summary["measurement_type"] == "pl"]
    assert pl["cycle_number"].tolist() == [1]
    assert pl["sweep_step"].isna().all()

    sweep = summary[summary["measurement_type"] == "sweep"]
    assert sweep["cycle_number"].tolist() == [2, 2, 2, 3, 3, 3]
    assert sweep["sweep_step"].tolist() == [1, 2, 3, 1, 2, 3]


def test_missing_cycle_defaults_to_zero_and_stays_filterable(mods, monkeypatch):
    dm = _loaded_manager(mods, monkeypatch, [_entry(1, "")])
    assert dm.get_data()["summary"]["cycle_number"].tolist() == [0]
    options = dm.get_filter_options()
    assert options["cycles"] == [0]
    assert len(options["filter_rows"]) == 1


def test_sweep_heatmap_uses_sweep_steps(mods, monkeypatch):
    entries = [_entry(3, "Cycle_1", flux=False), _entry(3, "Cycle_2", flux=False)]
    spectra = _loaded_manager(mods, monkeypatch, entries).get_data()["spectra"]
    fig = mods["plot_manager"].AbsPLPlotManager().sweep_heatmap(spectra, cycle=2)
    assert list(fig.data[0].y) == [1, 2, 3]
    assert fig.layout.yaxis.title.text == "Sweep step"


def test_search_for_abspl_filters_batches(mods, monkeypatch):
    app_mod = mods["app"]
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = app_mod.AbsPLAppController()
    app._batch_selector = app_mod.widgets.SelectMultiple(options=["a", "b", "c"])
    app._all_batch_options = ["a", "b", "c"]
    monkeypatch.setattr(app_mod, "get_ids_in_batch", lambda url, tok, ids: list(ids))
    monkeypatch.setattr(
        app_mod, "get_all_eqe", lambda url, tok, ids, eqe_type: {"S": [1]} if ids == ["b"] else {}
    )
    app._on_search_for_abspl()
    assert list(app._batch_selector.options) == ["b"]


def test_trace_order_sorts_traces_and_legend(mods, monkeypatch):
    import pandas as pd

    def row(sample):
        return {
            "sample_id": sample,
            "measurement_type": "pl",
            "wavelength": [700.0 + k for k in range(10)],
            "luminescence_flux_density": [1.0] * 10,
            "raw_spectrum_counts": [1.0] * 10,
            "intensity": [1.0] * 10,
            "laser_intensity_suns": 1.0,
        }

    df = pd.DataFrame([row("A"), row("B"), row("C")])
    pm = mods["plot_manager"].AbsPLPlotManager()
    fig = pm.pl_plot(df, color_by="sample_id", include_nearest_sweep=False, trace_order=["C", "A"])
    assert [t.name for t in fig.data] == ["C", "A", "B"]


def test_trace_order_state_roundtrip_and_exclusion(mods):
    gui = mods["gui_components"].AbsPLGUIComponents()
    gui._update_trace_order_widget(["A", "B", "C"])
    assert gui.get_trace_order() == ["A", "B", "C"]
    assert gui.get_excluded_samples() == []
    # what the browser JS writes into the hidden widgets
    gui.trace_order_state.value = '["C", "A", "B"]'
    gui.trace_excluded_state.value = '["B"]'
    assert gui.get_trace_order() == ["C", "A", "B"]
    assert gui.get_excluded_samples() == ["B"]
    assert gui.trace_js_output in gui.trace_order_section.children


def test_extract_cycle_ignores_px_prefix(mods):
    extract = mods["data_manager"].extract_cycle_info
    assert extract("Cycle_3") == 3
    assert extract("px2Cycle_4") == 4
    assert extract("px12Cycle_5") == 5
    assert extract("pxACycle_6") == 6
    assert extract("sample, px1Cycle_7, laser on") == 7
    assert extract("no cycle here") is None
