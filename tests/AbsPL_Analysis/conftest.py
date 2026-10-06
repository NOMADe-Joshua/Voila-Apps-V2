"""Fixtures for AbsPL_Analysis's tests."""

import pytest

MODULES = [
    "app",
    "data_manager",
    "diagnostic_helper",
    "gui_components",
    "plot_manager",
    "resizable_plot_utility",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("AbsPL_Analysis", MODULES)
