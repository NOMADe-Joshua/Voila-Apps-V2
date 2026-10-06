"""Monorepo-wide pytest configuration.

Three things every app's tests rely on:

1. The repo root has its own ``secrets.py`` (gitignored, holds a local NOMAD token).
   When pytest is invoked from the repo root, Python's default sys.path[0] (the
   empty string, meaning "current directory") lets that file shadow the stdlib
   ``secrets`` module for every test. Recent numpy/plotly versions import
   ``secrets.randbits``/``secrets.token_hex`` internally, so without this guard
   almost any test that touches pandas, numpy, or plotly fails with
   ``ImportError: cannot import name 'randbits'/'token_hex' from 'secrets'``.
   The repo-root entry is stripped before any test module gets imported.

2. ``shared/`` goes on sys.path so ``perotf_utils`` imports the same way it does
   after bootstrap.py ran in a notebook.

3. ``load_app_modules`` imports an app's own modules (which import each other by
   bare name, e.g. ``import data_manager``) and then removes those bare names from
   sys.modules again. Every app has a data_manager/gui_components/utils, so leaving
   them registered would hand one app's module to the next app's tests. Tests get
   the loaded modules from a fixture instead of importing them by name.

No test may reach the network: the autouse ``_no_network`` fixture makes every
``requests`` call fail loudly, except in tests marked ``live``.
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SHARED_DIR = _REPO_ROOT / "shared"
APPS_DIR = _REPO_ROOT / "apps"

for _entry in ("", str(_REPO_ROOT)):
    while _entry in sys.path:
        sys.path.remove(_entry)

if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

os.environ.setdefault("MPLBACKEND", "Agg")

_LOADED: dict[tuple[str, tuple[str, ...]], dict] = {}


def load_app_modules(app_folder: str, module_names: list[str]) -> dict:
    """Import ``module_names`` from ``apps/<app_folder>`` and return them by name.

    The app directory is on sys.path only while importing, and every bare name of a
    module in that directory is put back the way it was afterwards (removed, or the
    other app's module restored). Results are cached per app and module list.
    """
    key = (app_folder, tuple(module_names))
    if key in _LOADED:
        return _LOADED[key]

    app_dir = APPS_DIR / app_folder
    local_names = [p.stem for p in app_dir.glob("*.py")]
    displaced = {name: sys.modules.pop(name) for name in local_names if name in sys.modules}
    sys.path.insert(0, str(app_dir))
    try:
        modules = {name: importlib.import_module(name) for name in module_names}
    finally:
        sys.path.remove(str(app_dir))
        for name in local_names:
            sys.modules.pop(name, None)
        sys.modules.update(displaced)
        importlib.invalidate_caches()

    _LOADED[key] = modules
    return modules


@pytest.fixture(scope="session")
def app_loader():
    """``load_app_modules`` as a fixture, for per-app conftests:

    @pytest.fixture(scope="module")
    def jv(app_loader):
        return app_loader("JV-Analysis", ["app", "data_manager", "plot_manager"])
    """
    return load_app_modules


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Fail any HTTP request made through requests, unless the test is marked live."""
    if request.node.get_closest_marker("live"):
        return
    import requests

    def _blocked(self, method, url, *args, **kwargs):
        raise RuntimeError(f"Test tried to reach the network: {method} {url}")

    monkeypatch.setattr(requests.sessions.Session, "request", _blocked)
