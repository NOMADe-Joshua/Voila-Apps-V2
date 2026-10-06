"""Fixtures for Process_JV_Overview's tests."""

import pytest

MODULES = ["app", "data_manager", "plot_manager", "resizable_plot_utility", "utils"]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Process_JV_Overview", MODULES)
