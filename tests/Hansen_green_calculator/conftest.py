"""Fixtures for Hansen_green_calculator's tests."""

import pytest

MODULES = ["unifac_model"]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Hansen_green_calculator", MODULES)
