# app.py
# Thin orchestrator: wires data_manager state + gui_components widgets together. No
# business logic lives here.

import logging
from pathlib import Path

import gui_components
import ipywidgets as widgets

from perotf_utils.auth_manager import AuthenticationManager
from perotf_utils.config import API_ENDPOINT, URL_BASE
from perotf_utils.manual import manual_panel
from perotf_utils.widget_cleanup import UiRebuild

logger = logging.getLogger(__name__)

_TESTS_ROOT = Path(__file__).parent.parent.parent / "tests"
DEMO_FIXTURE_PATH = _TESTS_ROOT / "Entry_Auditor" / "fixtures" / "sample_batch.json"

# A re-run of the cell first closes the widgets of the previous run (see UiRebuild).
_ui = UiRebuild()


def _login(url_base: str, api_endpoint: str, token: str | None) -> tuple[str, str | None]:
    """(API url, token). On the Oasis the token is NOMAD_CLIENT_ACCESS_TOKEN; without one
    (outside NORTH under Voila) the app still starts, with the demo data only."""
    auth = AuthenticationManager(url_base, api_endpoint)
    url = auth.api_client.get_api_url()
    try:
        return url, auth.authenticate_with_token(token)
    except Exception as exc:  # noqa: BLE001
        # info, not warning: a warning would also land on stderr, which Voila shows
        logger.info("No NOMAD login: %s", exc)
        return url, None


def initialize_ui(
    url_base: str = URL_BASE, api_endpoint: str = API_ENDPOINT, token: str | None = None
) -> widgets.Widget:
    url, token = _login(url_base, api_endpoint, token)
    with _ui.build():
        ui = widgets.VBox(
            [
                manual_panel(__file__),
                gui_components.create_entry_auditor_ui(url, token, DEMO_FIXTURE_PATH),
            ]
        )
    return ui
