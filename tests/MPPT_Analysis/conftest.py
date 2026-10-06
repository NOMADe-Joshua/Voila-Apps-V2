"""Fixtures for MPPT_Analysis's tests."""

import pytest

MODULES = ["fitting_tools", "font_size_ui"]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("MPPT_Analysis", MODULES)
