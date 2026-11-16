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


def test_dashboard_shows_the_manual_toggle(mods, monkeypatch):
    import ipywidgets as widgets

    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    dashboard = mods["app"].JVAnalysisApp().get_dashboard()

    def walk(widget):
        yield widget
        for child in getattr(widget, "children", ()):
            yield from walk(child)

    toggles = [w for w in walk(dashboard) if isinstance(w, widgets.ToggleButton)]
    assert [t.description for t in toggles] == ["📖 Manual"]


# --- NOMAD text in HTML is escaped (rule 12, ported from HZB) ------------------------------


def test_measurement_links_escape_and_quote_what_comes_from_nomad(mods):
    link = mods["app"].measurement_link_html(
        "https://oasis/gui", "id/with space", "X_<img src=x onerror=alert(1)>"
    )
    assert "<img" not in link and "&lt;img" in link
    assert 'href="https://oasis/gui/entry/id/id%2Fwith%20space/data/data"' in link
    sem = mods["app"].measurement_link_html("https://oasis/gui", "E1", "X_SEM")
    assert "/images:0/image_preview/preview" in sem and ">SEM</a>" in sem


def test_plot_legend_and_titles_escape_sample_names(mods, monkeypatch):
    import plotly.graph_objects as go

    rpu = mods["resizable_plot_utility"]
    fig = go.Figure(go.Scatter(x=[0, 1], y=[0, 1], name="KIT_<script>x</script>", showlegend=True))
    legend = rpu.ResizablePlotManager._build_jv_legend_table(fig)
    assert "<script>" not in legend and "&lt;script&gt;" in legend

    shown = []
    monkeypatch.setattr(rpu, "display", lambda obj: shown.append(obj.data))
    rpu.ResizablePlotWidget(fig, title="Batch <b>1</b>", subtitle="a & b").display()
    assert "Batch &lt;b&gt;1&lt;/b&gt;" in shown[0] and "a &amp; b" in shown[0]


def test_diagnostic_messages_are_escaped(mods):
    logger = mods["diagnostic_helper"].DebugLogger()
    logger.add("ERROR", "KeyError: '<img src=x>'")
    assert "<img" not in logger.get_html() and "&lt;img" in logger.get_html()


def test_filter_rows_offer_only_columns_the_jv_table_has(mods):
    """V_MPP(V)/J_MPP(mA/cm2) were offered but the columns are V_mpp(V)/J_mpp(mA/cm2), so those
    filters were silently ignored (fixed at HZB as well)."""
    import inspect

    from perotf_utils.plotting_utils import WidgetFactory

    gui = mods["gui_components"]
    factory = next(
        cls
        for _, cls in inspect.getmembers(gui, inspect.isclass)
        if hasattr(cls, "create_filter_row") and cls.__module__ == gui.__name__
    )
    source = inspect.getsource(mods["data_manager"])
    for make_row in (factory.create_filter_row, WidgetFactory.create_filter_row):
        options = make_row().children[0].options
        assert all(f'"{option}"' in source for option in options), options


def test_plots_use_axis_settings_every_plotly_version_accepts(mods):
    """titlefont is rejected from plotly 6 on, so every JV plot failed there."""
    from pathlib import Path

    assert "titlefont" not in Path(mods["plot_manager"].__file__).read_text(encoding="utf-8")
