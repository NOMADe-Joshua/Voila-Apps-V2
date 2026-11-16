"""Smoke tests for EQE_Analysis: modules import and the app builds without network or token."""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_main_class_present(mods):
    assert hasattr(mods["app"], "EQEAnalysisApp")


def test_batch_selection_is_the_shared_one(mods):
    from perotf_utils.batch_selection import create_batch_selection

    assert mods["app"].create_batch_selection is create_batch_selection


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


def test_dashboard_shows_the_manual(mods, monkeypatch):
    from perotf_utils.manual import read_manual

    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    dashboard = mods["app"].EQEAnalysisApp().get_dashboard()

    def widgets_in(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from widgets_in(child)

    assert "📖 Manual" in [getattr(w, "description", None) for w in widgets_in(dashboard)]
    assert read_manual(mods["app"].__file__) is not None


def test_plot_titles_escape_sample_names(mods, monkeypatch):
    import plotly.graph_objects as go

    rpu = mods["resizable_plot_utility"]
    shown = []
    monkeypatch.setattr(rpu, "display", lambda obj: shown.append(obj.data))
    rpu.ResizablePlotWidget(go.Figure(), title="Batch <b>1</b>", subtitle="a & b").display()
    assert "Batch &lt;b&gt;1&lt;/b&gt;" in shown[0] and "a &amp; b" in shown[0]


def test_j0rad_is_shown_in_the_unit_nomad_stores_it(mods, monkeypatch):
    """NOMAD stores integrated_j0rad in mA/cm² like integrated_jsc (the schema's unit); an extra
    factor 0.1 showed it ten times too small."""
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].EQEAnalysisApp()
    factors = {key: factor for key, _, _, factor in app.LEGEND_ANNOTATIONS}
    assert factors["integrated_j0rad"] == factors["integrated_jsc"] == 1.0


def test_the_json_download_output_is_in_the_displayed_tree(mods, monkeypatch):
    """start_download runs its script from this Output; outside the tree it never runs."""
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    app = mods["app"].EQEAnalysisApp()
    dashboard = app.get_dashboard()

    def widgets_in(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from widgets_in(child)

    assert any(w is app.save_ui.download_output for w in widgets_in(dashboard))


def test_plots_use_axis_settings_every_plotly_version_accepts(mods):
    """titlefont is rejected from plotly 6 on."""
    from pathlib import Path

    assert "titlefont" not in Path(mods["plot_manager"].__file__).read_text(encoding="utf-8")
