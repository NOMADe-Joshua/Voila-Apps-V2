"""Fixtures for Excel_creator's tests."""

import pytest

MODULES = [
    "voila_experiment_app",
    "experiment_excel_builder",
    "sheet_data_entry_guide",
    "sheet_experiment",
    "sheet_how_to_cite",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Excel_creator", MODULES)
