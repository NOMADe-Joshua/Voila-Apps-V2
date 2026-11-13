"""bootstrap.py: the shared-install marker, pip time limits and the proxy environment.

The module runs its install steps at import time, so the functions are loaded from the
source up to that tail instead of importing it (scaffold ported from HZB).
"""

import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

BOOTSTRAP = Path(__file__).resolve().parents[2] / "bootstrap.py"


class _Namespace:
    """The module's globals as plain attributes, so monkeypatch reaches them (the globals
    dict itself is the instance __dict__)."""

    def __init__(self, namespace):
        self.__dict__ = namespace


@pytest.fixture
def bs(tmp_path, monkeypatch):
    source = BOOTSTRAP.read_text(encoding="utf-8").split("_local_config = _load_local_config()")[0]
    namespace = {"__file__": str(BOOTSTRAP), "__name__": "bootstrap_under_test"}
    exec(compile(source, str(BOOTSTRAP), "exec"), namespace)  # noqa: S102
    monkeypatch.setattr(namespace["tempfile"], "gettempdir", lambda: str(tmp_path))
    namespace["REPO_ROOT"] = tmp_path
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "shared" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    return _Namespace(namespace)


def test_shared_install_runs_once_then_is_skipped(bs, monkeypatch):
    calls = []
    monkeypatch.setattr(bs, "_pip_install", lambda target: calls.append(target) or (0, ""))
    bs._install_shared()
    bs._install_shared()
    assert len(calls) == 1


def test_shared_install_reruns_when_shared_changes(bs, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(bs, "_pip_install", lambda target: calls.append(target) or (0, ""))
    bs._install_shared()
    (tmp_path / "shared" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    bs._install_shared()
    assert len(calls) == 2


def test_failed_shared_install_writes_no_marker(bs, monkeypatch):
    calls = []
    monkeypatch.setattr(bs, "_pip_install", lambda target: calls.append(target) or (1, "boom"))
    monkeypatch.setattr(bs.importlib.util, "find_spec", lambda name: object())
    bs._install_shared()
    bs._install_shared()
    assert len(calls) == 2


def test_marker_hit_still_puts_shared_on_sys_path(bs, monkeypatch, tmp_path):
    monkeypatch.setattr(bs, "_pip_install", lambda target: (0, ""))
    bs._install_shared()
    monkeypatch.setattr(bs.sys, "path", [p for p in bs.sys.path if p != str(tmp_path / "shared")])
    bs._install_shared()
    assert bs.sys.path[0] == str(tmp_path / "shared")


def test_pip_gets_network_limits_and_an_overall_timeout(bs, monkeypatch):
    seen = {}

    def run(args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(bs.subprocess, "run", run)
    assert bs._pip_install(Path("x")) == (0, "")
    assert seen["args"][seen["args"].index("--timeout") + 1] == str(bs.PIP_NETWORK_TIMEOUT_S)
    assert seen["args"][seen["args"].index("--retries") + 1] == str(bs.PIP_RETRIES)
    assert seen["kwargs"]["timeout"] == bs.PIP_INSTALL_TIMEOUT_S


def test_a_hanging_pip_install_counts_as_failed(bs, monkeypatch):
    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(bs.subprocess, "run", run)
    returncode, output = bs._pip_install(Path("x"))
    assert returncode == 1
    assert "stopped after" in output


@pytest.fixture
def no_proxy_env(monkeypatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        monkeypatch.delenv(key, raising=False)


def test_http_proxy_only_is_applied_and_logged(bs, no_proxy_env, caplog):
    with caplog.at_level(logging.INFO):
        bs._apply_proxy_env({"HTTP_PROXY": "http://proxy.example.org:3128"})
    assert bs.os.environ["HTTP_PROXY"] == "http://proxy.example.org:3128"
    assert bs.os.environ["NO_PROXY"] == "localhost,127.0.0.1"
    assert "http://proxy.example.org:3128" in caplog.text


def test_container_no_proxy_wins(bs, no_proxy_env, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,.kit.edu")
    bs._apply_proxy_env({"HTTPS_PROXY": "http://proxy.example.org:3128", "NO_PROXY": "other"})
    assert bs.os.environ["NO_PROXY"] == "localhost,.kit.edu"


def test_no_proxy_without_configuration(bs, no_proxy_env):
    bs._apply_proxy_env({})
    assert "HTTP_PROXY" not in bs.os.environ and "HTTPS_PROXY" not in bs.os.environ
