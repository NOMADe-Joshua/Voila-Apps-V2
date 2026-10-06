"""Fixtures for smart_databaser's tests -- never hits the real API.

smart_databaser imports Excel_creator's sheet_experiment / experiment_excel_builder by bare
name ([tool.perotf] uses-apps in its pyproject.toml); the root app_loader makes
apps/Excel_creator importable while importing, so those two are loaded here as well and
are the very module objects data_manager uses.
"""

import pytest

MODULES = [
    "alias_config",
    "data_manager",
    "gui_components",
    "app",
    "sheet_experiment",
    "experiment_excel_builder",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("smart_databaser", MODULES)


@pytest.fixture
def fresh_state(mods):
    """A clean ExperimentState instance for each test."""
    return mods["data_manager"].ExperimentState()
