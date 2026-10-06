"""Fixtures for XRD_PF's tests.

gui_components.py and gui_layouts.py belong to the dormant photoluminescence app in the same
folder and import ipyvuetify at module level, which the XRD app never imports and does not
declare as a dependency, so they are not loaded here.
"""

import pytest

MODULES = [
    "app",
    "fitting_engine",
    "config",
    "utils",
    "data_manager",
    "plot_manager",
    "exporters",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    # data_manager.py logs notebook usage at import time; keep that log out of shared/.
    from perotf_utils import access_token

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(access_token, "log_notebook_usage", lambda *args, **kwargs: None)
        return app_loader("XRD_PF", MODULES)
