"""Fixtures for Peak_Explorer's tests."""

import pytest

MODULES = [
    "pl_data_loader",
    "pl_export_utils",
    "pl_fitting_models",
    "pl_peak_detection",
    "pl_visualization",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Peak_Explorer", MODULES)
