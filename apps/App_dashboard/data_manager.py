import logging
import os
from dataclasses import dataclass

from perotf_utils.access_token import log_button_usage
from perotf_utils.config import NORTH_ENDPOINT

logger = logging.getLogger(__name__)


VOILA_PATH_TEMPLATE = f"{NORTH_ENDPOINT}/user/{{user}}/voila/voila/render"
"""Rendered by the "voila" NORTH tool; built from NORTH_ENDPOINT so a deployment that
moves NORTH only changes config."""


@dataclass(frozen=True)
class AppEntry:
    folder: str
    notebook: str
    name: str
    description: str
    icon: str
    experimental: bool = False


CATEGORIES: dict[str, list[AppEntry]] = {
    "Device Characterization": [
        AppEntry(
            "JV-Analysis",
            "jv-analysis.ipynb",
            "JV Analysis",
            "Load the JV measurements of your batches from NOMAD, filter them, compare "
            "device parameters and JV curves, and export plots and data.",
            "fa-chart-bar",
        ),
        AppEntry(
            "Process_JV_Overview",
            "process_jv_overview.ipynb",
            "Process & JV Overview",
            "The processing steps of each batch next to its JV boxplots by variation, "
            "to correlate processes and efficiencies batch by batch.",
            "fa-project-diagram",
        ),
        AppEntry(
            "MPPT_Analysis",
            "mppt_plotting.ipynb",
            "MPPT Analysis",
            "Plot maximum power point tracking data from NOMAD, fit decay models to the "
            "curves and download the results.",
            "fa-chart-line",
        ),
        AppEntry(
            "EQE_Analysis",
            "eqe-analysis_voila.ipynb",
            "EQE Analysis",
            "Plot external quantum efficiency spectra from NOMAD and derive the integrated "
            "Jsc and the bandgap.",
            "fa-chart-area",
        ),
    ],
    "Optical & Structural Analysis": [
        AppEntry(
            "AbsPL_Analysis",
            "abspl_plotter.ipynb",
            "AbsPL Analysis",
            "Plot absolute photoluminescence measurements from NOMAD: spectra, PLQY, QFLS "
            "and intensity sweeps.",
            "fa-sun",
        ),
        AppEntry(
            "UVVis_Analyzer",
            "UVVis_analyzer.ipynb",
            "UV-Vis Analyzer",
            "Plot UV-Vis spectra from NOMAD and estimate bandgaps from derivative and Tauc plots.",
            "fa-rainbow",
        ),
        AppEntry(
            "XRD_PF",
            "peak_analyzer.ipynb",
            "XRD Peak Analyzer",
            "Load XRD diffractograms from NOMAD, overlay patterns, detect peaks and fit "
            "Gaussian profiles.",
            "fa-mountain",
        ),
        AppEntry(
            "SEM_crystal_counter",
            "image_analysis.ipynb",
            "SEM Grain Size Analysis",
            "Estimate the grain size distribution of perovskite films in SEM images via "
            "edge detection and region analysis.",
            "fa-image",
        ),
    ],
    "Data Management": [
        AppEntry(
            "Data_Tools",
            "data_tools.ipynb",
            "Data Tools",
            "Split, rename and merge raw JV, EQE and UV-Vis files into the naming scheme "
            "the ELN expects, plus a ratio calculator.",
            "fa-tools",
        ),
        AppEntry(
            "Excel_creator",
            "excel_creator.ipynb",
            "Excel Creator",
            "Configure the process sequence of an experiment and generate the Excel file "
            "that documents it for upload to NOMAD.",
            "fa-file-excel",
        ),
        AppEntry(
            "smart_databaser",
            "smart_databaser.ipynb",
            "Smart Databaser",
            "Build the experiment Excel for NOMAD with values filled in live from earlier "
            "batches: replicate a whole experiment or adopt single processes.",
            "fa-magic",
            experimental=True,
        ),
    ],
    "Utilities & Calculators": [
        AppEntry(
            "DesignOfExperiments",
            "DoE.ipynb",
            "Design of Experiments",
            "Define process variables and generate experiment plans with space-filling "
            "sampling (Latin hypercube, Sobol, Halton, grids, ...).",
            "fa-flask",
        ),
        AppEntry(
            "UVVis_Simulator",
            "UVVis_Simulation.ipynb",
            "UV-Vis Layer Stack Simulator",
            "Simulate reflectance, transmittance and absorptance of a thin-film layer "
            "stack with the transfer matrix method.",
            "fa-layer-group",
        ),
    ],
}


def get_current_user() -> str:
    """Return the NOMAD username of the person running this notebook, or '' if unknown."""
    return os.environ.get("NOMAD_CLIENT_USER", "")


def log_navigation(action: str) -> None:
    """Log a dashboard click (an app launch card, the What's New link, ...).

    The cards are Buttons rather than plain links precisely so that the click runs in
    this app's Python kernel and can be written to perotf_utils' button usage log.
    """
    log_button_usage(action, user=get_current_user())


UPLOADS_DIR_NAME = "uploads"


def _cwd_parts() -> list[str]:
    """The current working directory as path segments, separator-agnostic."""
    return [part for part in os.getcwd().replace("\\", "/").split("/") if part]


def _uploads_index(parts: list[str]) -> int | None:
    """Index of the NOMAD 'uploads' mount in parts, or None if cwd is not under one.

    The leftmost match wins: the mount lives at a fixed prefix (/home/jovyan/uploads),
    so a later segment of the same name is an upload or folder that happens to be
    called "uploads", not the mount point.
    """
    for index, part in enumerate(parts):
        # Needs at least <upload_id>/<AppFolder> after it to be usable.
        if part == UPLOADS_DIR_NAME and index + 2 < len(parts):
            return index
    return None


def get_upload_id() -> str:
    """Derive this dashboard's own NOMAD upload ID from the current working directory.

    Under a NOMAD north tool the cwd is .../uploads/<upload_id>/.../<AppFolder>, so the
    upload ID is the segment right after 'uploads'. Read from cwd rather than hardcoded
    so this keeps working if the upload is ever re-uploaded under a different ID.

    Anchored on the 'uploads' segment rather than counting directories up from the cwd,
    because how deep the repo sits inside the upload varies with how it was deployed:
    unpacking the repo at the top of an upload gives <upload_id>/apps/<AppFolder>, while
    `git clone` inside the upload adds the repo directory, giving
    <upload_id>/Voila-Apps-V2/apps/<AppFolder>. Fixed-depth walking silently returned
    the repo folder as the upload ID in the latter case, producing links with the upload
    name missing entirely.
    """
    parts = _cwd_parts()
    index = _uploads_index(parts)
    if index is None:
        # Not under an uploads mount (local dev, tests): best-effort, previous behaviour.
        return os.path.basename(os.path.dirname(os.path.dirname(os.getcwd())))
    return parts[index + 1]


def get_uploads_path() -> str:
    """Derive 'uploads/<upload_id>/.../<container>' from the current working directory.

    <container> is the folder holding all app folders ("apps" for this repo). Everything
    between the upload ID and the app folder is preserved, so a repo cloned into a
    subdirectory of the upload keeps that subdirectory in the path. See get_upload_id
    for why this is not a fixed number of levels.
    """
    parts = _cwd_parts()
    index = _uploads_index(parts)
    if index is None:
        container = os.path.basename(os.path.dirname(os.getcwd()))
        return f"{UPLOADS_DIR_NAME}/{get_upload_id()}/{container}"
    # From 'uploads' up to, but not including, this app's own folder.
    return "/".join(parts[index:-1])


def build_voila_url(entry: AppEntry, user: str, uploads_path: str) -> str:
    """Build the absolute Voila render path (without URL_BASE) for an app entry."""
    base_path = VOILA_PATH_TEMPLATE.format(user=user)
    folder = f"{entry.folder}/" if entry.folder else ""
    return f"{base_path}/{uploads_path}/{folder}{entry.notebook}"


def notebook_exists(entry: AppEntry) -> bool:
    """Best-effort local existence check for the entry notebook, relative to this app's folder."""
    local_path = os.path.join("..", entry.folder, entry.notebook)
    try:
        return os.path.exists(local_path)
    except OSError:
        logger.warning("Could not check existence of %s", local_path)
        return True
