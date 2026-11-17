"""Fixtures for Samples_Dashboard's tests."""

import pytest

MODULES = ["app", "data_manager", "plot_manager"]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Samples_Dashboard", MODULES)
