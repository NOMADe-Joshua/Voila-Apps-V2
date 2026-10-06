"""Fixtures for App_dashboard's tests."""

import pytest

MODULES = ["app", "data_manager", "gui_components"]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("App_dashboard", MODULES)


@pytest.fixture(scope="module")
def dm(mods):
    return mods["data_manager"]
