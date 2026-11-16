"""Fixtures for MPPT_Analysis's tests (ported from HZB) -- never hits the real API."""

from pathlib import Path

import pandas as pd
import pytest

# Loaded in one go so they share their module objects (gui_components imports data_manager &
# co. by bare name while loading).
MODULES = [
    "utils",
    "fitting_tools",
    "app_state",
    "data_manager",
    "plot_manager",
    "gui_components",
    "app_controller",
]

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "api_responses.json"

FIXTURE_ROWS = [
    {"time": 0.0, "power_density": -15.2, "voltage": 0.92, "current_density": -16.5},
    {"time": 0.5, "power_density": -14.8, "voltage": 0.91, "current_density": -16.3},
    {"time": 1.0, "power_density": -14.4, "voltage": 0.90, "current_density": -16.0},
    {"time": 1.5, "power_density": -14.1, "voltage": 0.89, "current_density": -15.8},
    {"time": 2.0, "power_density": -13.9, "voltage": 0.88, "current_density": -15.7},
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("MPPT_Analysis", MODULES)


@pytest.fixture
def loaded_manager(mods):
    dm = mods["data_manager"].DataManager(url="http://mock", token="mock-token")
    dm.load_offline(FIXTURE_PATH)
    return dm


@pytest.fixture
def mppt_dataframe():
    """Multi-index DataFrame matching the structure DataManager produces."""
    df = pd.DataFrame(FIXTURE_ROWS)
    sample_id = "batch1&sample1"
    curve_df = pd.concat([df], keys=[0], names=["curve_id", "point"])
    return curve_df, sample_id


@pytest.fixture
def loaded_app_state(mods, mppt_dataframe):
    """AppState pre-loaded with fixture curve data and a selected sample."""
    curves_df, sample_id = mppt_dataframe
    full_curves = pd.concat([curves_df], keys=[sample_id])
    sample_ids = pd.Series([sample_id])
    state = mods["app_state"].AppState()
    state.set_api_config("https://test-oasis.example.org", "test-token")
    state.load_curves_data(full_curves, sample_ids, pd.DataFrame(), pd.DataFrame())
    state.set_selected_samples([sample_id])
    return state


@pytest.fixture
def mock_data_manager(mods):
    """DataManager instance with no live API connectivity."""
    DataManager = mods["data_manager"].DataManager
    dm = DataManager.__new__(DataManager)
    dm.url = "https://test-oasis.example.org/nomad-oasis/api/v1"
    dm.token = "test-token"
    return dm


@pytest.fixture
def plot_manager(mods, loaded_app_state, mock_data_manager):
    """PlotManager wired to loaded_app_state and mock_data_manager."""
    return mods["plot_manager"].PlotManager(loaded_app_state, mock_data_manager)
