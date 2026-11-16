import logging
import os
from dataclasses import dataclass

from perotf_utils.access_token import log_button_usage
from perotf_utils.config import ADMIN_USERS, NORTH_ENDPOINT
from perotf_utils.north import (  # noqa: F401 (used through this module by app.py)
    get_current_user,
    get_upload_id,
    get_uploads_path,
)

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
    admin_only: bool = False
    """Only shown to users listed in perotf_utils.config.ADMIN_USERS."""


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
            "Global_analyzer",
            "global_analyzer.ipynb",
            "Global Analyzer",
            "Plot any result against any process parameter across many batches; correlations, "
            "Random Forest and suggestions for the next experiments.",
            "fa-globe",
        ),
        AppEntry(
            "MPPT_Analysis",
            "MPPT_analyzer.ipynb",
            "MPPT Analysis",
            "Fit degradation models to every MPPT measurement, get T80/T95 and lifetime "
            "energy yield, and write the fits back to NOMAD.",
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
            "SEM_Analyzer.ipynb",
            "SEM Crystal Counter",
            "Grain size and film thickness of perovskite films from SEM images, with manual "
            "correction.",
            "fa-microscope",
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
            "Entry_Auditor",
            "entry_auditor.ipynb",
            "Entry Auditor",
            "Find values spelled differently across the entries of a batch and correct them "
            "in NOMAD, with a preview and a backup of every changed entry.",
            "fa-clipboard-check",
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
    "Administration": [
        AppEntry(
            "log_view",
            "log_view.ipynb",
            "Usage Log",
            "Who started which app when: launches per day or week, filterable by date, "
            "user and app, read from the usage log every app writes on start.",
            "fa-chart-pie",
            admin_only=True,
        ),
        AppEntry(
            "Reprocess_Uploads",
            "reprocess_uploads.ipynb",
            "Reprocess Uploads",
            "Let the current experiment parser write the process entries of unpublished "
            "uploads again, e.g. evaporation steps that were stored without sources.",
            "fa-redo",
            admin_only=True,
        ),
    ],
}


def is_admin(user: str) -> bool:
    """Whether this NOMAD user may see admin-only apps (perotf_utils.config.ADMIN_USERS)."""
    return bool(user) and user in ADMIN_USERS


HIDE_APPS_ENV = "PEROTF_DASHBOARD_HIDE_APPS"
SHOW_APPS_ENV = "PEROTF_DASHBOARD_SHOW_APPS"
GROUP_ORDER_ENV = "PEROTF_DASHBOARD_GROUP_ORDER"
"""Per-deployment app selection (ported from HZB), set like every other per-Oasis override
(usually in oasis_local_config.py): comma-separated app folder names or card names to hide,
or, if SHOW is set, the only ones to show; GROUP_ORDER names the groups to list first. Names
ignore case and spaces; an unknown name logs a warning and is otherwise ignored. Hidden apps
stay in the upload and can still be opened directly."""


def _normalize_name(name: str) -> str:
    return "".join(name.split()).lower()


def parse_name_list(value: str | None) -> set[str]:
    """Normalized names from a comma-separated environment value ('' or None gives an empty set)."""
    return {_normalize_name(part) for part in (value or "").split(",") if part.strip()}


def parse_name_order(value: str | None) -> list[str]:
    """The normalized names of a comma-separated list, in the order given."""
    return [_normalize_name(part) for part in (value or "").split(",") if part.strip()]


def _entry_keys(entry: AppEntry) -> set[str]:
    return {key for key in (_normalize_name(entry.folder), _normalize_name(entry.name)) if key}


def order_categories(
    categories: dict[str, list[AppEntry]], order: list[str] | None
) -> dict[str, list[AppEntry]]:
    """The categories in the order named by `order` (normalized names); categories it does not
    name follow in their default order. An unknown name logs a warning and is ignored."""
    if not order:
        return categories
    by_key = {_normalize_name(name): name for name in categories}
    first = []
    for key in order:
        if key not in by_key:
            logger.warning("Dashboard group order: unknown group %r is ignored", key)
        elif by_key[key] not in first:
            first.append(by_key[key])
    rest = [name for name in categories if name not in first]
    return {name: categories[name] for name in [*first, *rest]}


def select_categories(
    categories: dict[str, list[AppEntry]],
    hide: set[str] | None = None,
    show: set[str] | None = None,
    order: list[str] | None = None,
) -> dict[str, list[AppEntry]]:
    """Apply a hide list, an optional allow-list (both normalized names) and a group order.
    With none of them set the result is exactly `categories`."""
    hide, show = hide or set(), show or set()
    known = set()
    for entries in CATEGORIES.values():
        for entry in entries:
            known |= _entry_keys(entry)
    for unknown in sorted((hide | show) - known):
        logger.warning("Dashboard app selection: unknown name %r is ignored", unknown)

    def visible(entry: AppEntry) -> bool:
        keys = _entry_keys(entry)
        if keys & hide:
            return False
        return not show or bool(keys & show)

    return order_categories(
        {
            category: [entry for entry in entries if visible(entry)]
            for category, entries in categories.items()
        },
        order,
    )


def visible_categories(user: str) -> dict[str, list[AppEntry]]:
    """CATEGORIES as this user should see them on this deployment: admin-only cards are
    dropped for everyone else, the PEROTF_DASHBOARD_* selection is applied, and a category
    left without cards disappears entirely.

    This only hides the card; the app itself checks the user again, since anyone who
    knows the notebook URL could still open it."""
    admin = is_admin(user)
    selected = select_categories(
        {
            category: [entry for entry in entries if admin or not entry.admin_only]
            for category, entries in CATEGORIES.items()
        },
        hide=parse_name_list(os.environ.get(HIDE_APPS_ENV)),
        show=parse_name_list(os.environ.get(SHOW_APPS_ENV)),
        order=parse_name_order(os.environ.get(GROUP_ORDER_ENV)),
    )
    return {category: entries for category, entries in selected.items() if entries}


def log_navigation(action: str) -> None:
    """Log a dashboard click (an app launch card, the What's New link, ...).

    The cards are Buttons rather than plain links precisely so that the click runs in
    this app's Python kernel and can be written to perotf_utils' button usage log.
    """
    log_button_usage(action, user=get_current_user())


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
