"""Repo-wide structure rules that keep the migration from drifting back.

The server address, its URL paths and the NOMAD entry type (schema class) names live in
shared/perotf_utils/config.py and nowhere else. Every app sits in apps/<App>/ with its own
pyproject.toml, every app notebook starts with the bootstrap cell, and nothing in apps/
manipulates sys.path (bootstrap.py puts shared/ on it).
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APPS_DIR = REPO_ROOT / "apps"
SHARED_PKG = REPO_ROOT / "shared" / "perotf_utils"
CONFIG_FILE = SHARED_PKG / "config.py"

APP_DIRS = sorted(p for p in APPS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))
NOTEBOOKS = sorted(p for p in APPS_DIR.rglob("*.ipynb") if ".ipynb_checkpoints" not in p.parts)
PY_FILES = sorted(
    [p for p in APPS_DIR.rglob("*.py") if "__pycache__" not in p.parts]
    + [p for p in SHARED_PKG.glob("*.py") if p != CONFIG_FILE]
)

# Literals that may only appear in config.py: server hosts (ours and HZB's), Oasis URL paths and
# entry type names. A GitHub link to HZB's schema repo (Excel_creator's citation sheet) is not a
# server address and is allowed.
SERVER_LITERALS = re.compile(
    r"elnserver|nomad-hzb-se\.|/nomad-oasis|peroTF_|HySprint_|baseclasses\."
)
SYS_PATH = re.compile(r"\bsys\.path\b")
BOOTSTRAP_LINE = '_ = runpy.run_path("../../bootstrap.py")'


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _code_cells(notebook: Path) -> list[str]:
    data = json.loads(notebook.read_text(encoding="utf-8"))
    cells = []
    for cell in data["cells"]:
        if cell.get("cell_type") != "code":
            continue
        src = cell.get("source", "")
        cells.append("".join(src) if isinstance(src, list) else src)
    return cells


def _offending_lines(text: str, pattern: re.Pattern) -> list[str]:
    return [line.strip() for line in text.splitlines() if pattern.search(line)]


def test_there_are_apps_and_notebooks():
    assert len(APP_DIRS) >= 10
    assert len(NOTEBOOKS) >= len(APP_DIRS)


@pytest.mark.parametrize("app_dir", APP_DIRS, ids=lambda p: p.name)
def test_app_has_pyproject_depending_on_perotf_utils(app_dir):
    pyproject = app_dir / "pyproject.toml"
    assert pyproject.exists(), f"{_rel(app_dir)} has no pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert '"perotf-utils"' in text, f"{_rel(pyproject)} must depend on perotf-utils"
    assert "hysprint" not in text.lower()


@pytest.mark.parametrize("app_dir", APP_DIRS, ids=lambda p: p.name)
def test_app_has_a_notebook(app_dir):
    assert list(app_dir.glob("*.ipynb")), f"{_rel(app_dir)} has no notebook"


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=_rel)
def test_notebook_starts_with_bootstrap_cell(notebook):
    data = json.loads(notebook.read_text(encoding="utf-8"))
    first = data["cells"][0]
    src = first.get("source", "")
    src = "".join(src) if isinstance(src, list) else src
    assert first.get("cell_type") == "code" and BOOTSTRAP_LINE in src, (
        f"{_rel(notebook)}: the first cell must be the bootstrap cell"
    )


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=_rel)
def test_notebook_code_has_no_server_literals_or_sys_path(notebook):
    offending = []
    for src in _code_cells(notebook):
        offending += _offending_lines(src, SERVER_LITERALS)
        offending += _offending_lines(src, SYS_PATH)
    assert not offending, f"{_rel(notebook)} must use perotf_utils.config: {offending}"


LOG_CALL = re.compile(r"^\s*(?:access_token\.)?log_notebook_usage\(")


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=_rel)
def test_notebook_logs_its_usage(notebook):
    """Every app start is written to the usage log (perotf_utils.access_token)."""
    calls = [
        line for src in _code_cells(notebook) for line in src.splitlines() if LOG_CALL.search(line)
    ]
    assert calls, f"{_rel(notebook)} never calls log_notebook_usage()"


@pytest.mark.parametrize("py_file", PY_FILES, ids=_rel)
def test_python_file_has_no_server_literals_or_sys_path(py_file):
    text = py_file.read_text(encoding="utf-8")
    offending = _offending_lines(text, SERVER_LITERALS) + _offending_lines(text, SYS_PATH)
    assert not offending, f"{_rel(py_file)} must use perotf_utils.config: {offending}"


@pytest.mark.parametrize("path", PY_FILES + NOTEBOOKS, ids=_rel)
def test_no_hysprint_utils_imports(path):
    assert "hysprint_utils" not in path.read_text(encoding="utf-8")


def test_no_tests_inside_apps():
    assert not [p for p in APPS_DIR.rglob("tests") if p.is_dir()]
    assert not list(APPS_DIR.rglob("test_*.py"))


def test_config_is_the_one_place_with_server_literals():
    text = CONFIG_FILE.read_text(encoding="utf-8")
    assert "elnserver" in text and "peroTF_" in text
