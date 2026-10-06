"""Fixtures for Data_Tools's tests."""

import pytest

MODULES = [
    "dragdrop_widget",
    "eln_renamer_module",
    "eqe_split_module",
    "iv_converter_module",
    "jv_organizer_module",
    "uvvis_merger_module",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Data_Tools", MODULES)
