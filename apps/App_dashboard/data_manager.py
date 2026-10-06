import logging
import os
from dataclasses import dataclass

from perotf_utils.access_token import log_button_usage
from perotf_utils.config import NORTH_ENDPOINT

logger = logging.getLogger(__name__)


VOILA_PATH_TEMPLATE = f"{NORTH_ENDPOINT}/user/{{user}}/voila/voila/render"
JUPYTER_PATH_TEMPLATE = f"{NORTH_ENDPOINT}/user/{{user}}/voila/lab/tree"
"""Deliberately the "voila" NORTH tool, not a separate "jupyter2" tool: the latter is not
provisioned on every Oasis, while the voila tool's container also serves a full JupyterLab
tree view at /voila/lab/tree, in addition to /voila/voila/render for rendered Voila apps.
Both are built from NORTH_ENDPOINT so a deployment that moves NORTH only changes config."""


@dataclass(frozen=True)
class AppEntry:
    folder: str
    notebook: str
    name: str
    description: str
    icon: str
    experimental: bool = False
    external_url: str | None = None
    """When set, the card links straight here instead of rendering folder/notebook via Voila."""


@dataclass(frozen=True)
class LearningEntry:
    name: str
    description: str
    icon: str
    path: str
    """Path to the notebook within this dashboard's own upload, e.g.
    'Learning/01_Python_logic_intro.ipynb'. Always resolved against get_upload_id()."""
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
        AppEntry(
            "Diode_Analyzer",
            "diode-gui.ipynb",
            "Diode Analyzer",
            "Fit LED current-voltage curves from a CSV file with a single-diode model to "
            "extract shunt and series resistance.",
            "fa-lightbulb",
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
            "Peak_Explorer",
            "main_notebook.ipynb",
            "Peak Explorer",
            "Fit peaks in time-resolved photoluminescence spectra and follow their "
            "position, height and width over time.",
            "fa-search",
        ),
        AppEntry(
            "SEM_crystal_counter",
            "SEM_Analyzer.ipynb",
            "SEM Crystal Counter",
            "Detect and count crystals in SEM images with configurable thresholding and "
            "segmentation, then export their size distribution.",
            "fa-microscope",
        ),
        AppEntry(
            "SEM_crystal_counter",
            "image_analysis.ipynb",
            "SEM Grain Size Analysis",
            "Estimate the grain size distribution of perovskite films in SEM images via "
            "edge detection and region analysis.",
            "fa-image",
        ),
        AppEntry(
            "XPS-Automated",
            "xps_automated.ipynb",
            "XPS Automated",
            "Align, normalize and Gaussian-fit XPS core-level spectra. A raw working "
            "notebook, not yet a finished app.",
            "fa-atom",
            experimental=True,
        ),
    ],
    "Data Management": [
        AppEntry(
            "Data_Overview_Machines",
            "get_data_from_last_week.ipynb",
            "Data Overview",
            "Best JV efficiency of every sample in a date range, plotted over time per "
            "person and filterable by the deposition machines used.",
            "fa-calendar-alt",
        ),
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
            "Hansen_green_calculator",
            "Hansen_UNIFAC_calculator.ipynb",
            "Hansen Blend Calculator",
            "Find the solvent blend that best matches target Hansen solubility parameters, "
            "with UNIFAC activity coefficients at a chosen temperature.",
            "fa-tint",
        ),
        AppEntry(
            "Hansen_green_calculator",
            "Mixture_calculator.ipynb",
            "Hansen Mixture Calculator",
            "Weighted average Hansen parameters and properties of a solvent mixture from "
            "the percentages you enter.",
            "fa-blender",
        ),
        AppEntry(
            "Hansen_green_calculator",
            "3D_visualizer.ipynb",
            "Hansen 3D Visualizer",
            "Search the solvent database and highlight compounds in 3D Hansen space, "
            "colored by any property.",
            "fa-cube",
        ),
        AppEntry(
            "Hansen_green_calculator",
            "data_visualizer.ipynb",
            "Solvent Data Visualizer",
            "Scatter any two properties of the solvent database against each other, "
            "colored by a third, or show all pairwise plots.",
            "fa-th",
        ),
        AppEntry(
            "Hansen_green_calculator",
            "perovskite_viz.ipynb",
            "Perovskite Ink Visualizer",
            "Plot perovskite inks in 3D Hansen space, filtered by solute and colored by "
            "any column of the ink table.",
            "fa-gem",
        ),
        AppEntry(
            "Hansen_green_calculator",
            "Hansen_Group_Plotting_Device.ipynb",
            "Hansen Ink Plotter",
            "Plot inks by solvent system in 3D Hansen space, with the volume spanned by "
            "each solute shown as a sphere.",
            "fa-cubes",
            experimental=True,
        ),
        AppEntry(
            "Perovskite_calculator",
            "perovskite_calculator.ipynb",
            "Perovskite Solution Calculator",
            "Calculate precursor masses and volumes for a perovskite solution from its "
            "target composition.",
            "fa-calculator",
        ),
        AppEntry(
            "UVVis_Simulator",
            "UVVis_Simulation.ipynb",
            "UV-Vis Layer Stack Simulator",
            "Simulate reflectance, transmittance and absorptance of a thin-film layer "
            "stack with the transfer matrix method.",
            "fa-layer-group",
        ),
        AppEntry(
            "Wetting_envelope",
            "wetting_envelope_app.ipynb",
            "Wetting Envelope",
            "Plot wetting envelopes of materials from their surface energy components "
            "(Owens-Wendt) and see which solvents wet them.",
            "fa-water",
        ),
    ],
    "Build Your Own": [
        AppEntry(
            "",
            "",
            "Make Your Own App With This Prompt",
            "Paste this into an LLM chatbot (Claude, ChatGPT, ...) so it can query your NOMAD "
            "data directly and write a custom analysis script, no new app required.",
            "fa-robot",
            external_url=(
                "https://raw.githubusercontent.com/NOMADe-Joshua/Voila-Apps-V2/main/"
                "NOMAD_DATA_ACCESS_PROMPT.md"
            ),
        ),
    ],
}


LEARNING_FOLDER = LearningEntry(
    "Learning",
    "Learn to build your own NOMAD solutions: guided Python & NOMAD tutorial notebooks. "
    "Opens the first lesson in JupyterLab, with the whole Learning folder in the sidebar "
    "so you can browse and pick whichever one you want.",
    "fa-graduation-cap",
    path="Learning/01_Python_logic_intro.ipynb",
)


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


def build_jupyter_url(entry: LearningEntry, user: str, upload_id: str) -> str:
    """Build the absolute JupyterLab 'tree' path that opens a learning notebook directly.

    Unlike build_voila_url, this points at the JupyterLab tree view of the voila NORTH
    tool, so the notebook opens already loaded in a JupyterLab tab instead of being
    rendered as a Voila app. Takes upload_id explicitly (from get_upload_id()), since a
    LearningEntry always lives in this dashboard's own upload.
    """
    base_path = JUPYTER_PATH_TEMPLATE.format(user=user)
    return f"{base_path}/uploads/{upload_id}/{entry.path}"


def notebook_exists(entry: AppEntry) -> bool:
    """Best-effort local existence check for the entry notebook, relative to this app's folder."""
    local_path = os.path.join("..", entry.folder, entry.notebook)
    try:
        return os.path.exists(local_path)
    except OSError:
        logger.warning("Could not check existence of %s", local_path)
        return True
