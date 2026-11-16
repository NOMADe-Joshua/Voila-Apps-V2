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
    "substrate": "peroTF_Substrate",
    # Process classes whose archive steps carry no 'method' value; code that sorts steps
    # by type recognises them by their m_def suffix instead (nomad_perotf perotf_package.py).
    "process": "peroTF_Process",
    # Entries nomad_perotf's experiment parser writes from the experiment Excel; the
    # experiment entry lists the process entries it created in data.processed_archive.
    "experiment": "RawHySprintExperiment",
    "evaporation": "peroTF_Evaporation",
    "spin_coating": "peroTF_SpinCoating",
    "inkjet_printing": "peroTF_InkjetPrinting",
    "thermal_annealing": "peroTF_ThermalAnnealing",
    "lamination": "peroTF_Lamination",
    "jv": "peroTF_JVmeasurement",
    "eqe": "peroTF_EQEmeasurement",
    "eqe_tfl_gammabox": "peroTF_TFL_GammaBox_EQEmeasurement",
    "mppt": "peroTF_MPPTracking",
    "abspl": "peroTF_AbsPLMeasurement",
    "xrd": "peroTF_XRD_XY",
    "uvvis": "peroTF_UVvisMeasurement",
    # SEM images (Zeiss TIFFs); data.detector_data lists the image files of the entry.
    "sem": "peroTF_SEM",
    # Base sections from nomad-baseclasses, matched via section_defs.definition_qualified_name
    "base_measurement": "baseclasses.BaseMeasurement",
    "base_process": "baseclasses.BaseProcess",
    "layer_deposition": "baseclasses.LayerDeposition",
    "jv_baseclass": "baseclasses.solar_energy.jvmeasurement.JVMeasurement",
}

# Every schema class of one kind of process step or measurement. nomad_perotf has a
# device-specific subclass per tool (CR_SpinBox_SpinCoating, TFL_PEROvap_Evaporation, ...),
# each its own entry type, so "every spin coating" is a list (classes as in nomad_perotf's
# perotf_package.py on 2026-11-14; add a new tool class here). api_calls queries a list with
# entry_type:any. Read by Global_analyzer.
ENTRY_TYPE_FAMILIES = {
    "cleaning": ["peroTF_Cleaning", "peroTF_CR_Wetbench_Cleaning", "peroTF_CR_Plasma_Cleaning"],
    "substrate": ["peroTF_Substrate"],
    "evaporation": [
        "peroTF_Evaporation",
        "peroTF_TFL_Ebeam_Evaporation",
        "peroTF_CR_Angstrom_Evaporation",
        "peroTF_TFL_BellJar_Evaporation",
        "peroTF_UP_PEROvap_Evaporation",
        "peroTF_TFL_PEROvap_Evaporation",
        "peroTF_UP_OPTIvap_Evaporation",
    ],
    "slot_die_coating": ["peroTF_SlotDieCoating", "peroTF_UP_SlotDieBox_SlotDieCoating"],
    "spin_coating": [
        "peroTF_SpinCoating",
        "peroTF_CR_SpinBox_SpinCoating",
        "peroTF_CR_ChemistryBox_SpinCoating",
        "peroTF_CR_MixBox_SpinCoating",
        "peroTF_CR_OmegaBox_SpinCoating",
        "peroTF_TFL_AlphaBox_SpinCoating",
        "peroTF_CR_BetaBox_SpinCoating",
    ],
    "inkjet_printing": ["peroTF_InkjetPrinting"],
    "ald": ["peroTF_ALD"],
    "blade_coating": ["peroTF_BladeCoating"],
    "dip_coating": ["peroTF_DipCoating"],
    "laser_scribing": [],  # no such step in nomad_perotf
    "annealing": [
        "peroTF_ThermalAnnealing",
        "peroTF_CR_ThermalAnnealing",
        "peroTF_TFL_ThermalAnnealing",
    ],
    "sputtering": ["peroTF_Sputtering", "peroTF_TFL_SputterSystem_Sputtering"],
    "close_space_sublimation": ["peroTF_CloseSpaceSublimation"],
    "lamination": ["peroTF_Lamination"],
    "jv": [
        "peroTF_JVmeasurement",
        "peroTF_CR_SolSimBox_JVmeasurement",
        "peroTF_TFL_GammaBox_JVmeasurement",
    ],
    # peroTF_EQEmeasurement is ENTRY_TYPES["eqe"]: no longer a class, but older entries have it
    "eqe": ["peroTF_EQEmeasurement", "peroTF_TFL_GammaBox_EQEmeasurement"],
    "mppt": ["peroTF_MPPTracking", "peroTF_CR_SolSimBox_MPPTracking"],
    "sem": ["peroTF_SEM"],
    "abspl": ["peroTF_AbsPLMeasurement"],
    "xrd": ["peroTF_XRD_XY"],
    "uvvis": ["peroTF_UVvisMeasurement"],
    "pl_imaging": ["peroTF_PLImaging"],
}

# NOMAD usernames (NOMAD_CLIENT_USER) that see admin-only apps such as the Usage Log.
# Comma-separated override, e.g. PEROTF_ADMIN_USERS="nomade,someone.else".
ADMIN_USERS = tuple(
    name.strip()
    for name in os.environ.get("PEROTF_ADMIN_USERS", "nomade").split(",")
    if name.strip()
)

# First segment of every sample lab id (Nomad ID) this lab writes, e.g.
# KIT_<Project_Name>_<Date>_<Batch>_<Subbatch>_<Sample>; the same prefix Excel_creator's
# example Nomad ID formula uses.
LAB_ID_PREFIX = "KIT"
