"""Fixtures for DesignOfExperiments's tests."""

import pytest

MODULES = [
    "app",
    "data_manager",
    "plot_manager",
    "gui_components",
    "sampling_algorithms",
    "utils",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("DesignOfExperiments", MODULES)
