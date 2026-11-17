"""Fixtures for Group_Management's tests."""

import pytest

MODULES = ["app", "data_manager"]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Group_Management", MODULES)
