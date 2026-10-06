"""Fixtures for UVVis_Analyzer's tests."""

import pytest

MODULES = [
    "app",
    "data_manager",
    "plot_manager",
    "gui_components",
    "common_widgets",
    "font_size_ui",
    "diagnostic_helper",
    "resizable_plot_utility",
    "utils",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("UVVis_Analyzer", MODULES)
