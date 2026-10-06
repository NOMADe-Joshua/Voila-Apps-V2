"""Central NOMAD Oasis configuration for every peroTF app.

This is the only place in the repo where the server address, its URL paths and the NOMAD
entry type (schema class) names are written down. Apps and the other perotf_utils modules
import them from here; tests/structure/test_repo_structure.py fails if a literal shows up
anywhere else.

Every server value can be overridden per deployment with an environment variable of the
same name prefixed with ``PEROTF_`` (for example ``PEROTF_URL_BASE``), set in the container
or in the gitignored ``oasis_local_config.py`` that bootstrap.py reads. See DEPLOYMENT.md.

The keys of ENTRY_TYPES match the ones HZB uses in hysprint_utils.config, so an app
exchanged with HZB only needs its imports switched from hysprint_utils to perotf_utils and
then automatically queries the peroTF schema classes on this Oasis.
"""

import os

# Server root, without a trailing slash.
URL_BASE = os.environ.get("PEROTF_URL_BASE", "http://elnserver.lti.kit.edu")

# REST API, appended to URL_BASE.
API_ENDPOINT = os.environ.get("PEROTF_API_ENDPOINT", "/nomad-oasis/api/v1")

# Web GUI, appended to URL_BASE; used for links to entries and searches.
GUI_ENDPOINT = os.environ.get("PEROTF_GUI_ENDPOINT", "/nomad-oasis/gui")

# NORTH tools (Jupyter/Voila), appended to URL_BASE; used by the App Dashboard links.
NORTH_ENDPOINT = os.environ.get("PEROTF_NORTH_ENDPOINT", "/nomad-oasis/north")

# NOMAD entry types (schema class names) the apps query.
ENTRY_TYPES = {
    "batch": "peroTF_Batch",
    "sample": "peroTF_Sample",
    "jv": "peroTF_JVmeasurement",
    "eqe": "peroTF_EQEmeasurement",
    "eqe_tfl_gammabox": "peroTF_TFL_GammaBox_EQEmeasurement",
    "mppt": "peroTF_MPPTracking",
    "abspl": "peroTF_AbsPLMeasurement",
    "xrd": "peroTF_XRD_XY",
    "uvvis": "peroTF_UVvisMeasurement",
    # Base sections from nomad-baseclasses, matched via section_defs.definition_qualified_name
    "base_measurement": "baseclasses.BaseMeasurement",
    "base_process": "baseclasses.BaseProcess",
    "layer_deposition": "baseclasses.LayerDeposition",
    "jv_baseclass": "baseclasses.solar_energy.jvmeasurement.JVMeasurement",
}
