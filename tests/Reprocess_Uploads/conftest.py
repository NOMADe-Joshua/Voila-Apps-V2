"""Fixtures for Reprocess_Uploads' tests."""

import pytest

MODULES = ["app", "data_manager"]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Reprocess_Uploads", MODULES)
