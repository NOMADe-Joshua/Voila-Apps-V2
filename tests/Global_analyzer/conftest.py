"""Fixtures for Global_analyzer's tests."""

import pytest

# Every module, loaded in one go so they share their module objects (the mixins of app.py
# import data_manager & co. by bare name while loading).
MODULES = [
    "config",
    "utils",
    "data_loader",
    "data_manager",
    "plot_manager",
    "ml_analysis",
    "experimental_analysis",
    "gui_components",
    "analysis_data_handlers",
    "analysis_handlers",
    "app",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Global_analyzer", MODULES)
