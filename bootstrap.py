"""Bootstrap run at the top of every app notebook, before any app import.

Applies this deployment's environment (Oasis URL, outbound proxy, per-app
overrides), then installs perotf_utils from shared/. The ordering is not
cosmetic: perotf_utils.config reads PEROTF_URL_BASE at import time, and
pip reaches PyPI for build dependencies, so both need the environment in
place before they run.

Overrides are opt-in; without them every app talks to the server configured
in shared/perotf_utils/config.py and no proxy is applied. A deployment that
needs overrides creates oasis_local_config.py next to this file (gitignored,
same pattern as secrets.py) assigning plain uppercase strings:

    PEROTF_URL_BASE = "https://nomad.example.org"
    HTTP_PROXY = "http://proxy.example.org:3128"

Every uppercase string it defines is exported as an environment variable of
the same name, so a new override needs no change here. Variables already
set at the container level always win - this file never overwrites them.
See DEPLOYMENT.md for the recognised names and a worked example.

Notebooks invoke this via a fixed 2-line cell 0 (cwd is always the
notebook's own directory under Voila, regardless of the upload session
hash, so the relative path here is invariant):

    import runpy
    _ = runpy.run_path("../../bootstrap.py")
"""

import builtins
import contextlib
import hashlib
import importlib
import importlib.util
import io
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent


PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")


def _load_local_config() -> dict[str, str]:
    """Return the uppercase string assignments in oasis_local_config.py, if any."""
    config_path = REPO_ROOT / "oasis_local_config.py"
    if not config_path.exists():
        return {}

    namespace: dict = {}
    exec(config_path.read_text(encoding="utf-8"), namespace)  # noqa: S102
    config = {
        key: value for key, value in namespace.items() if key.isupper() and isinstance(value, str)
    }
    logger.info("Loaded %d override(s) from %s", len(config), config_path)
    return config


def _apply_config_env(config: dict[str, str]) -> None:
    """Export every non-proxy override that the container has not already set.

    Membership, not truthiness: an override deliberately set to "" has to
    survive as an empty string rather than being skipped as falsy.
    """
    for key, value in config.items():
        if key in PROXY_KEYS or key in os.environ:
            continue
        os.environ[key] = value


def _apply_proxy_env(config: dict[str, str]) -> None:
    """Apply HTTP_PROXY/HTTPS_PROXY/NO_PROXY from oasis_local_config.py, if it sets any."""
    if os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY"):
        return

    http_proxy = config.get("HTTP_PROXY")
    https_proxy = config.get("HTTPS_PROXY")
    if not (http_proxy or https_proxy):
        return

    if http_proxy:
        os.environ["HTTP_PROXY"] = http_proxy
    if https_proxy:
        os.environ["HTTPS_PROXY"] = https_proxy

    no_proxy = config.get("NO_PROXY")
    if no_proxy is None:
        # Loopback only. The Oasis host is deliberately NOT excluded: a
        # container that needs a proxy at all usually has no direct route to
        # anything, in-house hosts included. A deployment whose Oasis really
        # is directly reachable sets NO_PROXY explicitly.
        no_proxy = "localhost,127.0.0.1"
    os.environ["NO_PROXY"] = no_proxy

    logger.info("Applied local proxy configuration: %s", https_proxy or http_proxy)


def _build_isolation_args() -> list[str]:
    """Skip pip's build isolation whenever hatchling is already installed.

    With isolation on, pip downloads the build backend from PyPI into a
    throwaway environment on every install, even when the kernel already has
    it. A container with no route to PyPI then fails to build shared/ at all
    ("Network is unreachable ... No matching distribution found for
    hatchling"). Building against the local hatchling needs no network as
    long as the runtime dependencies are already present.
    """
    if importlib.util.find_spec("hatchling") is not None:
        return ["--no-build-isolation"]
    return []


def _pip_install(target: Path) -> tuple[int, str]:
    """Install target, returning pip's exit code and its combined output.

    Captured, not inherited: this runs as cell 0 of a Voila app, where anything
    pip writes to stdout/stderr is rendered into the app's own UI. Callers
    decide what to surface; a successful install has nothing an app user needs
    to see.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "--disable-pip-version-check",
            *_build_isolation_args(),
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return result.returncode, output


# perotf-utils' own runtime dependencies (shared/pyproject.toml). If pip
# could not install shared/, these must already be in the image for the
# sys.path fallback below to be usable.
SHARED_RUNTIME_MODULES = ("perotf_utils", "requests", "pandas", "plotly")


def _install_shared() -> None:
    shared = REPO_ROOT / "shared"
    returncode, output = _pip_install(shared)

    # A fresh kernel already ran site.py before this install happened, so it
    # won't pick up the newly installed package on its own until restarted.
    # Adding shared/ to sys.path directly makes THIS kernel see perotf_utils
    # immediately, without needing a second run. A deliberate exception to
    # CLAUDE.md rule 8, not a violation to clean up.
    shared_str = str(shared)
    if shared_str not in sys.path:
        sys.path.insert(0, shared_str)

    if returncode == 0:
        if output:
            logger.info("pip install of %s reported:\n%s", shared, output)
        return

    # The sys.path entry above is what this kernel actually imports from, so a
    # failed install (typically no route to PyPI) only matters if something
    # perotf_utils needs is genuinely missing. Fatal only in that case.
    missing = [name for name in SHARED_RUNTIME_MODULES if importlib.util.find_spec(name) is None]
    if not missing:
        logger.warning(
            "pip install of %s failed with exit code %d; continuing with it on sys.path:\n%s",
            shared,
            returncode,
            output,
        )
        return

    # The pip output goes in the exception, not the log line: a traceback
    # always renders in the notebook, whereas a log record only shows if
    # something configured logging. Putting it in both duplicates a very
    # long diagnostic in the one place it is hardest to read.
    logger.error("pip install of %s failed with exit code %d", shared, returncode)
    raise RuntimeError(
        f"bootstrap: pip install of {shared} failed with exit code {returncode}, "
        f"and {', '.join(missing)} cannot be imported without it.\n{output}"
    )


def _silence_import_banners() -> None:
    """Keep what libraries print while being imported out of the app's UI.

    Some third-party packages greet stdout at import time with a multi-line
    banner (version, licence status, plot style, backend). Under Voila that
    lands above the app itself, where it reads as an error to anyone who does
    not recognise it.

    Cell 0 has returned by the time an app's imports run, so this cannot be a
    `with` block: it replaces builtins.__import__ for the rest of the kernel's
    life, redirecting stdout for the duration of each outermost import. The
    text is logged at debug rather than dropped, so nothing is truly lost.

    Deliberately narrow: stderr is untouched (warnings still surface), runtime
    output is untouched, and an import of an already-imported module takes a
    fast path. Set PEROTF_KEEP_IMPORT_OUTPUT=1 to turn the whole thing off
    when debugging an import.
    """
    if os.environ.get("PEROTF_KEEP_IMPORT_OUTPUT"):
        return

    real_import = builtins.__import__
    state = {"depth": 0}

    def quiet_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        # Nested imports are already covered by the outermost redirect, and a
        # cache hit cannot print anything - both skip the bookkeeping.
        if state["depth"] or (level == 0 and name in sys.modules):
            return real_import(name, globals, locals, fromlist, level)

        captured = io.StringIO()
        state["depth"] += 1
        try:
            with contextlib.redirect_stdout(captured):
                return real_import(name, globals, locals, fromlist, level)
        finally:
            state["depth"] -= 1
            banner = captured.getvalue().strip()
            if banner:
                logger.debug("suppressed import-time output of %s:\n%s", name, banner)

    builtins.__import__ = quiet_import


def _app_install_marker(app_dir: Path, pyproject: Path) -> Path:
    """Path of the once-per-container marker for this app's dependency install.

    Keyed on the app's location and the contents of its pyproject.toml, so
    editing the dependency list invalidates the marker and the next launch
    reinstalls, while an unchanged app never pays for pip twice.
    """
    digest = hashlib.sha256(str(app_dir).encode() + pyproject.read_bytes()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"perotf-bootstrap-{digest}.done"


def _install_app() -> None:
    """Install the calling app's own pyproject dependencies, once per container.

    The cwd is the notebook's own directory, so this installs the app the
    notebook belongs to. Without it an app's pyproject.toml is inert at
    runtime: nothing on the Oasis ever installs it, so a dependency missing
    from the NORTH image would fail with ModuleNotFoundError although it sits
    in the app's dependency list.

    Deliberately non-fatal, unlike the shared install. Most apps need nothing
    beyond what the NORTH image already provides, so a pip failure here (no
    network, an unreachable git host) must not take down an app that would
    otherwise have run fine.
    """
    app_dir = Path.cwd()
    pyproject = app_dir / "pyproject.toml"
    if not pyproject.exists():
        return

    marker = _app_install_marker(app_dir, pyproject)
    if marker.exists():
        logger.info("app dependencies already installed for %s", app_dir)
        return

    returncode, output = _pip_install(app_dir)
    if returncode != 0:
        logger.warning(
            "could not install the dependencies of %s (pip exit %d); the app may still "
            "work if they are already present:\n%s",
            app_dir,
            returncode,
            output,
        )
        return

    if output:
        logger.info("pip install of %s reported:\n%s", app_dir, output)
    try:
        marker.write_text(f"{app_dir}\n", encoding="utf-8")
    except OSError:
        # A read-only or missing temp dir only costs a repeat install later.
        logger.info("could not write the install marker %s", marker)


_local_config = _load_local_config()
_apply_config_env(_local_config)
_apply_proxy_env(_local_config)
_install_shared()
_install_app()
_silence_import_banners()
importlib.invalidate_caches()
