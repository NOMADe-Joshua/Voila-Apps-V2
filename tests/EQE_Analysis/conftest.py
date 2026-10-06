"""Fixtures for EQE_Analysis's tests."""

import pytest

MODULES = [
    "app",
    "batch_selection",
    "data_manager",
    "diagnostic_helper",
    "font_size_ui",
    "gui_components",
    "plot_manager",
    "resizable_plot_utility",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("EQE_Analysis", MODULES)
