"""Fixtures for JV-Analysis's tests."""

import pytest

MODULES = [
    "app",
    "data_manager",
    "diagnostic_helper",
    "font_size_ui",
    "gui_components",
    "jv_curve_analysis_ui_NEW",
    "plot_manager",
    "pptx_generator",
    "resizable_plot_utility",
    "utils",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("JV-Analysis", MODULES)
