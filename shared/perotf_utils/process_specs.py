"""Per-process-type Excel columns and their NOMAD archive field mappings for peroTF.

smart_databaser (apps/smart_databaser) reads this catalog to know, for every process type
peroTF's Excel_creator can write, which Excel column autofills from which path of an
already-uploaded NOMAD process step. The module keeps the API of HZB's equivalent module
(PROCESSES, AVAILABLE_PROCESSES, ATMOSPHERIC_CONFIG_KEY, field_args and the build_*
functions), so smart_databaser runs against it unchanged.

Two sources define what belongs in here, and the catalog must match both:

1. The column labels peroTF's apps/Excel_creator/sheet_experiment.py writes
   (generate_steps_for_process). smart_databaser builds its columns by running that
   function and reading back the header row, so a label in this catalog that the sheet
   never writes can never be filled, and a label spelled differently than in the sheet
   never autofills. peroTF's sheet_experiment.py does NOT read this module; it keeps its
   own inline labels, which is why every label below is copied from it verbatim,
   including its spelling quirks ("Annealing athmosphere", "Solution volume [um]",
   "Drying gas temperature [°]").
2. The archive paths nomad_perotf's experiment parser (perotf_batch_parser.py) stores
   through the nomad-baseclasses map_<type> functions (helper/solar_cell_batch_mapping.py).
   Only add a path after reading the map_<type> function that writes it; never guess.

AVAILABLE_PROCESSES mirrors the process list of peroTF's Excel_creator
(voila_experiment_app.py, MinimalistExperimentBuilder) in the same order, so smart_databaser
offers exactly the process types Excel_creator can write. Types the parser never turns into
an archive step (Multijunction Info; Laser Scribing while the parser has it commented out)
or turns into a step of another type (Seq-Evaporation becomes a plain Evaporation) are
still listed so they can be part of a new experiment; they simply never autofill.

Shape of one field entry (a dict): {"test": <test value>, "path": [...]} for a single
archive path, or {"test": <test value>, "paths": [[...], [...]]} for alternative paths tried
in order (first non-None wins). Optional keys: "unit_verified" (default True; False means
the value is copied from the archive with NO unit conversion applied and has NOT been
confirmed to match the Excel column's stated unit - check against the NOMAD web GUI before
flipping to True), "multiply" (a confirmed numeric unit-conversion factor applied before the
value is written/previewed - only add once verified against the actual NOMAD quantity
definition, never guessed), "dropdown" (inline Excel data-validation choices). A field with
no "path"/"paths" is a deliberately unmapped column (Notes on every process type, Experiment
Info's Date/Project_Name/Batch/Subbatch/Nomad ID/Sample/Variation - see
EXPERIMENT_INFO_NEVER_AUTOFILLED and EXPERIMENT_INFO_COMPUTED_KEYS in smart_databaser's
data_manager.py - and every column the parser does not store).

Indexed (repeated) fields - e.g. "Solvent {n} name" - are grouped by the config key that
drives their repeat count (PROCESSES[type]["indexed"][key]), since every field in that group
loops together off the same counter. Each entry's "path" carries a "{i}" placeholder
resolved to the 0-based index. "test" may be a plain value or a callable taking the 1-based
n. "mapping_range" (default (1, 5)) is how far smart_databaser pre-generates archive-path
lookups for autofill; a source archive with more items than that simply does not autofill
the extras. Exactly one entry per group carries a `config_key` matching its group key;
smart_databaser's infer_config_from_source_step uses it to size a new process's config to
the source step.

Optional blocks (e.g. Spin Coating's Gas Quenching) are grouped by their boolean config key
(PROCESSES[type]["optional"][key]) - present only when that config flag is True, same shape
as a plain "fields" entry otherwise.

"meta" holds the per-process GUI metadata: "material_gated" (the parser skips the step when
"Material name" is empty, so smart_databaser only counts its progress once it is filled),
"numeric_config" (list of (config_key, label, min, max) - numeric controls such as the
solvent count), "boolean_config" (list of (config_key, label) - checkboxes such as Gas
Quenching), "config_defaults" (starting config dict for a newly added process). These mirror
the controls and defaults of Excel_creator's voila_experiment_app.py. Two Inkjet Printing
controls there cannot be expressed here and are left unsupported in smart_databaser: the
"pixORnotion" printer-type dropdown (a string, not a count or flag) and the
"Wf Number of Pulses" count (it repeats waveform columns the parser only stores for some
printers, computed rather than copied). Their defaults are still listed in config_defaults,
so the generated sheet gets Excel_creator's default waveform columns.
"""

# ---------------------------------------------------------------------------
# Shared coating-family blocks - Spin Coating / Dip Coating / Slot Die Coating /
# Inkjet Printing share the same prefix (material/layer/tool), solvent and solute loops
# and annealing suffix around their own process-specific fields, mirroring
# sheet_experiment.py's `if process_name in [...]` grouping.
# ---------------------------------------------------------------------------

_LAYER_FIELDS = {
    "Material name": {
        "test": "Cs0.05(MA0.17FA0.83)0.95Pb(I0.83Br0.17)3",
        "path": ["layer", 0, "layer_material_name"],
    },
    "Layer type": {"test": "Absorber", "path": ["layer", 0, "layer_type"]},
    "Tool/GB name": {"test": "Glovebox 1", "path": ["location"]},
}

# map_annealing() (called by every coating map_<type>) reads "Annealing athmosphere".
_COATING_SUFFIX_FIELDS = {
    "Annealing time [min]": {"test": 30, "path": ["annealing", "time"], "unit_verified": False},
    "Annealing temperature [°C]": {
        "test": 120,
        "path": ["annealing", "temperature"],
        "unit_verified": False,
    },
    "Annealing athmosphere": {"test": "Nitrogen", "path": ["annealing", "atmosphere"]},
    "Notes": {"test": "Process notes"},
}

# map_solutions(): solvent names land in chemical_2.name. SolutionChemical.chemical_volume
# is declared in ml while the column says uL, so the volume stays unit_verified False until
# checked in the NOMAD GUI.
_COATING_SOLVENT_INDEXED = [
    {
        "excel_key": "Solvent {n} name",
        "test": lambda n: "DMF",
        "path": ["solution", 0, "solution_details", "solvent", "{i}", "chemical_2", "name"],
        "config_key": "solvents",
    },
    {
        "excel_key": "Solvent {n} volume [uL]",
        "test": lambda n: 10 * n,
        "path": ["solution", 0, "solution_details", "solvent", "{i}", "chemical_volume"],
        "unit_verified": False,
    },
]

# map_solutions() reads "Solute {n} type" (falling back to "... name") into chemical_2.name;
# SolutionChemical.normalize copies it to "name" as well.
_COATING_SOLUTE_INDEXED = [
    {
        "excel_key": "Solute {n} type",
        "test": lambda n: "PbI2",
        "paths": [
            ["solution", 0, "solution_details", "solute", "{i}", "chemical_2", "name"],
            ["solution", 0, "solution_details", "solute", "{i}", "name"],
        ],
        "config_key": "solutes",
    },
    {
        "excel_key": "Solute {n} Concentration [mM]",
        "test": lambda n: 1.42,
        "path": ["solution", 0, "solution_details", "solute", "{i}", "concentration_mol"],
        "unit_verified": False,
    },
]

# map_gas_quenching_with_nozzle()
_GAS_QUENCHING_FIELDS = {
    "Gas": {"test": "Nitrogen", "path": ["quenching", "gas"]},
    "Gas quenching start time [s]": {
        "test": 5,
        "path": ["quenching", "starting_delay"],
        "unit_verified": False,
    },
    "Gas quenching duration [s]": {
        "test": 15,
        "path": ["quenching", "duration"],
        "unit_verified": False,
    },
    "Gas quenching flow rate [ml/s]": {
        "test": 20,
        "path": ["quenching", "flow_rate"],
        "unit_verified": False,
    },
    "Gas quenching pressure [bar]": {
        "test": 1.2,
        "path": ["quenching", "pressure"],
        "unit_verified": False,
    },
    "Gas quenching velocity [m/s]": {
        "test": 2.5,
        "path": ["quenching", "velocity"],
        "unit_verified": False,
    },
    "Gas quenching height [mm]": {
        "test": 10,
        "path": ["quenching", "height"],
        "unit_verified": False,
    },
    "Nozzle shape": {"test": "Round", "path": ["quenching", "nozzle_shape"]},
    "Nozzle size [mm²]": {"test": 3, "path": ["quenching", "nozzle_size"], "unit_verified": False},
}

# map_vacuum_quenching()
_VACUUM_QUENCHING_FIELDS = {
    "Vacuum quenching start time [s]": {
        "test": 8,
        "path": ["quenching", "start_time"],
        "unit_verified": False,
    },
    "Vacuum quenching duration [s]": {
        "test": 20,
        "path": ["quenching", "duration"],
        "unit_verified": False,
    },
    "Vacuum quenching pressure [bar]": {
        "test": 0.01,
        "path": ["quenching", "pressure"],
        "unit_verified": False,
    },
}


def _without_paths(fields: dict) -> dict:
    """Same labels and test values, no archive paths - for columns the sheet writes but
    the parser never stores."""
    return {key: {"test": spec["test"]} for key, spec in fields.items()}


_ATMOSPHERIC_FIELDS: dict = {}
"""The upstream (HZB) sheet_experiment.py can append a block of atmosphere columns to every
process (the "add_atmospheric" flag). peroTF's sheet_experiment.py has no such block, so the
catalog has none either and ATMOSPHERIC_CONFIG_KEY is None: smart_databaser then does not
offer the checkbox. Kept as an (empty) name so atmospheric_args() keeps the upstream API."""

ATMOSPHERIC_CONFIG_KEY = None

_MATERIALS_CONFIG = ("materials", "Materials", 1, 5)

# ---------------------------------------------------------------------------
# Per-process-type specs, in the order of Excel_creator's process list
# ---------------------------------------------------------------------------

PROCESSES = {
    "Experiment Info": {
        "meta": {"material_gated": False, "numeric_config": [], "boolean_config": []},
        # map_basic_sample() / map_substrate(); smart_databaser reads these from the first
        # sample and its substrate entry ({"sample": ..., "substrate": ...}).
        "fields": {
            "Date": {"test": "20260526"},
            "Project_Name": {"test": "JoDa"},
            "Batch": {"test": "1"},
            "Subbatch": {"test": "1"},
            "Sample": {"test": "1"},
            "Nomad ID": {"test": ""},
            "Variation": {"test": "1000 rpm"},
            "Sample dimension": {"test": "16x16", "path": ["substrate", "substrate_dimension"]},
            "Sample area [cm^2]": {"test": 0.105, "path": ["substrate", "solar_cell_area"]},
            "Number of pixels": {"test": 4, "path": ["substrate", "number_of_pixels"]},
            "Pixel area": {"test": 0.105, "path": ["substrate", "pixel_area"]},
            "Number of junctions": {"test": 1, "path": ["sample", "number_of_junctions"]},
            "Substrate material": {"test": "Glass", "path": ["substrate", "substrate"]},
            "Substrate conductive layer": {
                "test": "ITO",
                "path": ["substrate", "conducting_material", 0],
            },
            "Bottom Cell Name": {"test": "", "path": ["substrate", "lab_id"]},
            "Notes": {"test": "Test excel"},
        },
    },
    "Spin Coating": {
        "meta": {
            "material_gated": True,
            "numeric_config": [
                ("solvents", "Solvents", 0, 20),
                ("solutes", "Solutes", 0, 20),
                ("spinsteps", "Steps", 1, 5),
            ],
            "boolean_config": [
                ("antisolvent", "Antisolvent"),
                ("gasquenching", "Gas Quenching"),
                ("vacuumquenching", "Vacuum Quenching"),
            ],
            "config_defaults": {
                "solvents": 1,
                "solutes": 1,
                "spinsteps": 1,
                "antisolvent": False,
                "gasquenching": False,
                "vacuumquenching": False,
            },
        },
        # map_spin_coating()
        "fields": {
            **_LAYER_FIELDS,
            "Solution volume [uL]": {
                "test": 100,
                "path": ["solution", 0, "solution_volume"],
                "unit_verified": False,
            },
            "Spin Delay [s]": {"test": 0.5},
            "Rotation speed [rpm]": {
                "test": 1500,
                "path": ["recipe_steps", 0, "speed"],
                "unit_verified": False,
            },
            "Rotation time [s]": {
                "test": 30,
                "path": ["recipe_steps", 0, "time"],
                "unit_verified": False,
            },
            "Acceleration [rpm/s]": {
                "test": 500,
                "path": ["recipe_steps", 0, "acceleration"],
                "unit_verified": False,
            },
            **_COATING_SUFFIX_FIELDS,
        },
        "indexed": {
            "solvents": _COATING_SOLVENT_INDEXED,
            "solutes": _COATING_SOLUTE_INDEXED,
            "spinsteps": [
                {
                    "excel_key": "Rotation speed {n} [rpm]",
                    "test": lambda n: 3000 + n,
                    "path": ["recipe_steps", "{i}", "speed"],
                    "unit_verified": False,
                    "config_key": "spinsteps",
                },
                {
                    "excel_key": "Rotation time {n} [s]",
                    "test": lambda n: 30 + n,
                    "path": ["recipe_steps", "{i}", "time"],
                    "unit_verified": False,
                },
                {
                    "excel_key": "Acceleration {n} [rpm/s]",
                    "test": lambda n: 1000 + n,
                    "path": ["recipe_steps", "{i}", "acceleration"],
                    "unit_verified": False,
                },
            ],
        },
        "optional": {
            # map_anti_solvent_quenching()
            "antisolvent": {
                "Anti solvent name": {
                    "test": "Toluene",
                    "path": ["quenching", "anti_solvent_2", "name"],
                },
                "Anti solvent volume [ml]": {
                    "test": 0.3,
                    "path": ["quenching", "anti_solvent_volume"],
                    "unit_verified": False,
                },
                "Anti solvent dropping time [s]": {
                    "test": 25,
                    "path": ["quenching", "anti_solvent_dropping_time"],
                    "unit_verified": False,
                },
                "Anti solvent dropping speed [uL/s]": {
                    "test": 50,
                    "path": ["quenching", "anti_solvent_dropping_flow_rate"],
                    "unit_verified": False,
                },
                "Anti solvent dropping heigt [mm]": {
                    "test": 30,
                    "path": ["quenching", "anti_solvent_dropping_height"],
                    "unit_verified": False,
                },
            },
            "gasquenching": _GAS_QUENCHING_FIELDS,
            "vacuumquenching": _VACUUM_QUENCHING_FIELDS,
        },
    },
    "Evaporation": {
        "meta": {"material_gated": True, "numeric_config": [], "boolean_config": []},
        # map_evaporation(coevaporation=False). "Organic" only decides whether the values
        # land in organic_evaporation or inorganic_evaporation, so it has no path of its
        # own; smart_databaser derives it back (data_manager._DERIVED_FIELDS).
        # "Power [%]" is not stored by the parser.
        "fields": {
            "Material name": {"test": "PCBM", "path": ["layer", 0, "layer_material_name"]},
            "Layer type": {
                "test": "Electron Transport Layer",
                "path": ["layer", 0, "layer_type"],
            },
            "Tool/GB name": {"test": "Evaporator 1", "path": ["location"]},
            "Organic": {"test": True},
            "Base pressure [bar]": {
                "test": 1e-6,
                "paths": [
                    ["organic_evaporation", 0, "pressure"],
                    ["inorganic_evaporation", 0, "pressure"],
                ],
                "unit_verified": False,
            },
            "Pressure start [bar]": {
                "test": 5e-6,
                "paths": [
                    ["organic_evaporation", 0, "pressure_start"],
                    ["inorganic_evaporation", 0, "pressure_start"],
                ],
                "unit_verified": False,
            },
            "Pressure end [bar]": {
                "test": 3e-6,
                "paths": [
                    ["organic_evaporation", 0, "pressure_end"],
                    ["inorganic_evaporation", 0, "pressure_end"],
                ],
                "unit_verified": False,
            },
            "Source temperature start[°C]": {
                "test": 150,
                "paths": [
                    ["organic_evaporation", 0, "temparature", 0],
                    ["inorganic_evaporation", 0, "temparature", 0],
                ],
                "unit_verified": False,
            },
            "Source temperature end[°C]": {
                "test": 160,
                "paths": [
                    ["organic_evaporation", 0, "temparature", 1],
                    ["inorganic_evaporation", 0, "temparature", 1],
                ],
                "unit_verified": False,
            },
            "Substrate temperature [°C]": {
                "test": 25,
                "paths": [
                    ["organic_evaporation", 0, "substrate_temparature"],
                    ["inorganic_evaporation", 0, "substrate_temparature"],
                ],
                "unit_verified": False,
            },
            "Thickness [nm]": {
                "test": 100,
                "paths": [
                    ["organic_evaporation", 0, "thickness"],
                    ["inorganic_evaporation", 0, "thickness"],
                ],
                "unit_verified": False,
            },
            "Rate [angstrom/s]": {
                "test": 1.0,
                "paths": [
                    ["organic_evaporation", 0, "target_rate"],
                    ["inorganic_evaporation", 0, "target_rate"],
                ],
                "unit_verified": False,
            },
            "Power [%]": {"test": 50},
            "Tooling factor": {
                "test": 1.5,
                "paths": [
                    ["organic_evaporation", 0, "tooling_factor"],
                    ["inorganic_evaporation", 0, "tooling_factor"],
                ],
            },
            "Notes": {"test": "Test note"},
        },
    },
    "Co-Evaporation": {
        "meta": {
            "material_gated": True,
            "numeric_config": [_MATERIALS_CONFIG],
            "boolean_config": [],
            "config_defaults": {"materials": 2},
        },
        # map_evaporation(coevaporation=True): one perovskite_evaporation entry per filled
        # "Material name {n}" (the parser reads materials 1 to 4).
        "fields": {
            "Material name": {"test": "MAPbI3", "path": ["layer", 0, "layer_material_name"]},
            "Layer type": {"test": "Absorber", "path": ["layer", 0, "layer_type"]},
            "Tool/GB name": {"test": "Evaporator 2", "path": ["location"]},
            "Notes": {"test": "Test note co-evaporation"},
        },
        "indexed": {
            "materials": [
                {
                    "excel_key": "Material name {n}",
                    "test": lambda n: "PbI2",
                    "path": ["perovskite_evaporation", "{i}", "chemical_2", "name"],
                    "config_key": "materials",
                },
                {
                    "excel_key": "Base pressure {n} [bar]",
                    "test": lambda n: 1e-6,
                    "path": ["perovskite_evaporation", "{i}", "pressure"],
                    "unit_verified": False,
                },
                {
                    "excel_key": "Pressure start {n} [bar]",
                    "test": lambda n: 5e-6,
                    "path": ["perovskite_evaporation", "{i}", "pressure_start"],
                    "unit_verified": False,
                },
                {
                    "excel_key": "Pressure end {n} [bar]",
                    "test": lambda n: 3e-6,
                    "path": ["perovskite_evaporation", "{i}", "pressure_end"],
                    "unit_verified": False,
                },
                {
                    "excel_key": "Source temperature start {n}[°C]",
                    "test": lambda n: 110 + n,
                    "path": ["perovskite_evaporation", "{i}", "temparature", 0],
                    "unit_verified": False,
                },
                {
                    "excel_key": "Source temperature end {n}[°C]",
                    "test": lambda n: 120 + n,
                    "path": ["perovskite_evaporation", "{i}", "temparature", 1],
                    "unit_verified": False,
                },
                {
                    "excel_key": "Substrate temperature {n} [°C]",
                    "test": lambda n: 25,
                    "path": ["perovskite_evaporation", "{i}", "substrate_temparature"],
                    "unit_verified": False,
                },
                {
                    "excel_key": "Thickness {n} [nm]",
                    "test": lambda n: 20 + n,
                    "path": ["perovskite_evaporation", "{i}", "thickness"],
                    "unit_verified": False,
                },
                {
                    "excel_key": "Rate {n} [angstrom/s]",
                    "test": lambda n: 0.5 + n,
                    "path": ["perovskite_evaporation", "{i}", "target_rate"],
                    "unit_verified": False,
                },
                {
                    "excel_key": "Tooling factor {n}",
                    "test": lambda n: 1.1 + n,
                    "path": ["perovskite_evaporation", "{i}", "tooling_factor"],
                },
            ]
        },
    },
    "Seq-Evaporation": {
        # Same columns as Co-Evaporation, but the parser runs map_evaporation() with
        # coevaporation=False on it: without an "Organic" column it stores neither
        # organic_evaporation nor inorganic_evaporation, and the resulting step is an
        # ordinary "Evaporation" step that smart_databaser resolves as Evaporation. A
        # Seq-Evaporation process can therefore never find a source step, so it carries no
        # paths; it is listed so a new experiment can still contain it.
        "meta": {
            "material_gated": True,
            "numeric_config": [_MATERIALS_CONFIG],
            "boolean_config": [],
            "config_defaults": {"materials": 2},
        },
        "fields": {
            "Material name": {"test": "MAPbI3"},
            "Layer type": {"test": "Absorber"},
            "Tool/GB name": {"test": "Evaporator 2"},
            "Notes": {"test": "Test note seq-evaporation"},
        },
        "indexed": {
            "materials": [
                {"excel_key": "Material name {n}", "test": lambda n: "PbI2"},
                {"excel_key": "Base pressure {n} [bar]", "test": lambda n: 1e-6},
                {"excel_key": "Pressure start {n} [bar]", "test": lambda n: 5e-6},
                {"excel_key": "Pressure end {n} [bar]", "test": lambda n: 3e-6},
                {"excel_key": "Source temperature start {n}[°C]", "test": lambda n: 110 + n},
                {"excel_key": "Source temperature end {n}[°C]", "test": lambda n: 120 + n},
                {"excel_key": "Substrate temperature {n} [°C]", "test": lambda n: 25},
                {"excel_key": "Thickness {n} [nm]", "test": lambda n: 20 + n},
                {"excel_key": "Rate {n} [angstrom/s]", "test": lambda n: 0.5 + n},
                {"excel_key": "Tooling factor {n}", "test": lambda n: 1.1 + n},
            ]
        },
    },
    "Sputtering": {
        "meta": {"material_gated": True, "numeric_config": [], "boolean_config": []},
        # map_sputtering()
        "fields": {
            "Material name": {"test": "ITO", "path": ["layer", 0, "layer_material_name"]},
            "Layer type": {"test": "Electrode", "path": ["layer", 0, "layer_type"]},
            "Tool/GB name": {"test": "Sputter tool", "path": ["location"]},
            "Gas": {"test": "Argon", "path": ["processes", 0, "gas_2", "name"]},
            "Temperature [°C]": {
                "test": 200,
                "path": ["processes", 0, "temperature"],
                "unit_verified": False,
            },
            "Pressure [mbar]": {
                "test": 0.01,
                "path": ["processes", 0, "pressure"],
                "unit_verified": False,
            },
            "Deposition time [s]": {
                "test": 300,
                "path": ["processes", 0, "deposition_time"],
                "unit_verified": False,
            },
            "Burn in time [s]": {
                "test": 60,
                "path": ["processes", 0, "burn_in_time"],
                "unit_verified": False,
            },
            "Power [W]": {"test": 150, "path": ["processes", 0, "power"], "unit_verified": False},
            "Rotation rate [rpm]": {
                "test": 30,
                "path": ["processes", 0, "rotation_rate"],
                "unit_verified": False,
            },
            "Thickness [nm]": {
                "test": 50,
                "path": ["processes", 0, "thickness"],
                "unit_verified": False,
            },
            "Gas flow rate [cm^3/min]": {
                "test": 20,
                "path": ["processes", 0, "gas_flow_rate"],
                "unit_verified": False,
            },
            "Notes": {"test": "Notes Sputtering"},
        },
    },
    "ALD": {
        "meta": {"material_gated": True, "numeric_config": [], "boolean_config": []},
        # map_atomic_layer_deposition()
        "fields": {
            "Material name": {"test": "Al2O3", "path": ["layer", 0, "layer_material_name"]},
            "Layer type": {
                "test": "Electron Transport Layer",
                "path": ["layer", 0, "layer_type"],
            },
            "Tool/GB name": {"test": "ALD tool", "path": ["location"]},
            "Source": {"test": "TMA", "path": ["properties", "source"]},
            "Thickness [nm]": {
                "test": 25,
                "path": ["properties", "thickness"],
                "unit_verified": False,
            },
            "Temperature [°C]": {
                "test": 150,
                "path": ["properties", "temperature"],
                "unit_verified": False,
            },
            "Rate [A/s]": {"test": 0.1, "path": ["properties", "rate"], "unit_verified": False},
            "Time [s]": {"test": 1800, "path": ["properties", "time"], "unit_verified": False},
            "Number of cycles": {"test": 250, "path": ["properties", "number_of_cycles"]},
            "Precursor 1": {"test": "TMA", "path": ["properties", "material", "material", "name"]},
            "Pulse duration 1 [s]": {
                "test": 0.2,
                "path": ["properties", "material", "pulse_duration"],
                "unit_verified": False,
            },
            "Manifold temperature 1 [°C]": {
                "test": 80,
                "path": ["properties", "material", "manifold_temperature"],
                "unit_verified": False,
            },
            "Bottle temperature 1 [°C]": {
                "test": 25,
                "path": ["properties", "material", "bottle_temperature"],
                "unit_verified": False,
            },
            "Precursor 2 (Oxidizer/Reducer)": {
                "test": "H2O",
                "path": ["properties", "oxidizer_reducer", "material", "name"],
            },
            "Pulse duration 2 [s]": {
                "test": 0.1,
                "path": ["properties", "oxidizer_reducer", "pulse_duration"],
                "unit_verified": False,
            },
            "Manifold temperature 2 [°C]": {
                "test": 70,
                "path": ["properties", "oxidizer_reducer", "manifold_temperature"],
                "unit_verified": False,
            },
        },
    },
    "Cleaning O2-Plasma": {
        "meta": {
            "material_gated": False,
            "numeric_config": [("solvents", "Solvents", 0, 20)],
            "boolean_config": [],
            "config_defaults": {"solvents": 1},
        },
        # map_cleaning(). CleaningTechnique.time is declared in minutes in
        # nomad-baseclasses while the columns say seconds, hence "multiply": 60.
        "fields": {
            "Gas-Plasma Gas": {"test": "Oxygen", "path": ["cleaning_plasma", 0, "plasma_type"]},
            "Gas-Plasma Time [s]": {
                "test": 180,
                "path": ["cleaning_plasma", 0, "time"],
                "multiply": 60,
            },
            "Gas-Plasma Power [W]": {
                "test": 50,
                "path": ["cleaning_plasma", 0, "power"],
                "unit_verified": False,
            },
        },
        "indexed": {
            "solvents": [
                {
                    "excel_key": "Solvent {n}",
                    "test": lambda n: "Hellmanex",
                    "path": ["cleaning", "{i}", "name"],
                    "config_key": "solvents",
                },
                {
                    "excel_key": "Time {n} [s]",
                    "test": lambda n: 900,
                    "path": ["cleaning", "{i}", "time"],
                    "multiply": 60,
                },
                {
                    "excel_key": "Temperature {n} [°C]",
                    "test": lambda n: 40,
                    "path": ["cleaning", "{i}", "temperature"],
                    "unit_verified": False,
                },
            ]
        },
    },
    "Cleaning UV-Ozone": {
        "meta": {
            "material_gated": False,
            "numeric_config": [("solvents", "Solvents", 0, 20)],
            "boolean_config": [],
            "config_defaults": {"solvents": 1},
        },
        "fields": {
            "UV-Ozone Time [s]": {"test": 900, "path": ["cleaning_uv", 0, "time"], "multiply": 60},
        },
        "indexed": {
            "solvents": [
                {
                    "excel_key": "Solvent {n}",
                    "test": lambda n: "Hellmanex",
                    "path": ["cleaning", "{i}", "name"],
                    "config_key": "solvents",
                },
                {
                    "excel_key": "Time {n} [s]",
                    "test": lambda n: 900,
                    "path": ["cleaning", "{i}", "time"],
                    "multiply": 60,
                },
                {
                    "excel_key": "Temperature {n} [°C]",
                    "test": lambda n: 40,
                    "path": ["cleaning", "{i}", "temperature"],
                    "unit_verified": False,
                },
            ]
        },
    },
    "Inkjet Printing": {
        "meta": {
            "material_gated": True,
            "numeric_config": [("solvents", "Solvents", 0, 20), ("solutes", "Solutes", 0, 20)],
            "boolean_config": [
                ("gasquenching", "Gas Quenching"),
                ("vacuumquenching", "Vacuum Quenching"),
            ],
            "config_defaults": {
                "solvents": 1,
                "solutes": 1,
                "pixORnotion": "Pixdro",
                "Wf Number of Pulses": 1,
                "gasquenching": False,
                "vacuumquenching": False,
            },
        },
        # map_inkjet_printing()
        "fields": {
            **_LAYER_FIELDS,
            "Printhead name": {
                "test": "Spectra 0.8uL",
                "path": ["properties", "print_head_properties", "print_head_name"],
            },
            "Printing run": {"test": "1", "path": ["properties", "printing_run"]},
            "Number of active nozzles": {
                "test": 128,
                "path": ["properties", "print_head_properties", "number_of_active_print_nozzles"],
            },
            "Droplet density [dpi]": {
                "test": 400,
                "path": ["properties", "drop_density"],
                "unit_verified": False,
            },
            "Quality factor": {"test": 3, "path": ["print_head_path", "quality_factor"]},
            "Step size": {"test": 10, "path": ["print_head_path", "step_size"]},
            "Printing direction": {"test": 10, "path": ["print_head_path", "directional"]},
            "Printed area [mm²]": {
                "test": 100,
                "path": ["properties", "printed_area"],
                "unit_verified": False,
            },
            "Droplet per second [1/s]": {
                "test": 5000,
                "path": ["properties", "print_head_properties", "print_nozzle_drop_frequency"],
                "unit_verified": False,
            },
            "Droplet volume [pL]": {
                "test": 10,
                "path": ["properties", "print_head_properties", "print_nozzle_drop_volume"],
                "unit_verified": False,
            },
            "Dropping Height [mm]": {
                "test": 12,
                "path": ["properties", "print_head_properties", "print_head_distance_to_substrate"],
                "unit_verified": False,
            },
            "Ink reservoir pressure [mbar]": {
                "test": 300,
                "path": ["properties", "cartridge_pressure"],
                "unit_verified": False,
            },
            "Table temperature [°C]": {
                "test": 40,
                "path": ["properties", "substrate_temperature"],
                "unit_verified": False,
            },
            "Nozzle temperature [°C]": {
                "test": 35,
                "path": ["properties", "print_head_properties", "print_head_temperature"],
                "unit_verified": False,
            },
            # map_atmosphere()
            "Room temperature [°C]": {
                "test": 21,
                "path": ["atmosphere", "temperature"],
                "unit_verified": False,
            },
            "rel. humidity [%]": {"test": 30, "path": ["atmosphere", "relative_humidity"]},
            **_COATING_SUFFIX_FIELDS,
        },
        "indexed": {
            "solvents": _COATING_SOLVENT_INDEXED,
            "solutes": _COATING_SOLUTE_INDEXED,
        },
        # map_inkjet_printing() only stores gas-assisted vacuum drying (GAVD) as its
        # quenching, which peroTF's sheet never writes; the gas and vacuum quenching columns
        # the sheet does write are not stored, so these blocks carry no paths.
        "optional": {
            "gasquenching": _without_paths(_GAS_QUENCHING_FIELDS),
            "vacuumquenching": _without_paths(_VACUUM_QUENCHING_FIELDS),
        },
    },
    "Slot Die Coating": {
        "meta": {
            "material_gated": True,
            "numeric_config": [("solvents", "Solvents", 0, 20), ("solutes", "Solutes", 0, 20)],
            "boolean_config": [],
            "config_defaults": {"solvents": 1, "solutes": 1},
        },
        # map_sdc(); the air knife columns go through map_air_knife_gas_quenching(), which
        # only stores anything when "Air knife angle [°]" is filled.
        "fields": {
            **_LAYER_FIELDS,
            "Coating run": {"test": "1", "path": ["properties", "coating_run"]},
            "Solution volume [um]": {
                "test": 100,
                "path": ["solution", 0, "solution_volume"],
                "unit_verified": False,
            },
            "Flow rate [uL/min]": {
                "test": 25,
                "path": ["properties", "flow_rate"],
                "unit_verified": False,
            },
            "Head gap [mm]": {
                "test": 0.3,
                "path": ["properties", "slot_die_head_distance_to_thinfilm"],
                "unit_verified": False,
            },
            "Speed [mm/s]": {
                "test": 15,
                "path": ["properties", "slot_die_head_speed"],
                "unit_verified": False,
            },
            "Air knife angle [°]": {"test": 45, "path": ["quenching", "air_knife_angle"]},
            "Air knife gap [cm]": {
                "test": 0.5,
                "path": ["quenching", "air_knife_distance_to_thin_film"],
            },
            "Bead volume [mm/s]": {"test": 2, "path": ["quenching", "bead_volume"]},
            "Drying speed [cm/min]": {"test": 30, "path": ["quenching", "drying_speed"]},
            "Drying gas temperature [°]": {
                "test": 25,
                "path": ["quenching", "drying_gas_temperature"],
                "unit_verified": False,
            },
            "Heat transfer coefficient [W m^-2 K^-1]": {
                "test": 10,
                "path": ["quenching", "heat_transfer_coefficient"],
                "unit_verified": False,
            },
            "Coated area [mm²]": {
                "test": 100,
                "path": ["properties", "coated_area"],
                "unit_verified": False,
            },
            **_COATING_SUFFIX_FIELDS,
        },
        "indexed": {
            "solvents": _COATING_SOLVENT_INDEXED,
            "solutes": _COATING_SOLUTE_INDEXED,
        },
    },
    "Dip Coating": {
        "meta": {
            "material_gated": True,
            "numeric_config": [("solvents", "Solvents", 0, 20), ("solutes", "Solutes", 0, 20)],
            "boolean_config": [],
            "config_defaults": {"solvents": 1, "solutes": 1},
        },
        # map_dip_coating()
        "fields": {
            **_LAYER_FIELDS,
            "Dipping duration [s]": {
                "test": 15,
                "path": ["properties", "time"],
                "unit_verified": False,
            },
            **_COATING_SUFFIX_FIELDS,
        },
        "indexed": {
            "solvents": _COATING_SOLVENT_INDEXED,
            "solutes": _COATING_SOLUTE_INDEXED,
        },
    },
    "Laser Scribing": {
        # peroTF's parser has its Laser Scribing branch commented out, so no peroTF batch
        # contains a laser scribing step and this process never autofills. The paths are
        # the ones map_laser_scribing() writes, kept for when the parser enables it.
        "meta": {"material_gated": False, "numeric_config": [], "boolean_config": []},
        "fields": {
            "Laser wavelength [nm]": {"test": 532, "path": ["properties", "laser_wavelength"]},
            "Laser pulse time [ps]": {"test": 8, "path": ["properties", "laser_pulse_time"]},
            "Laser pulse frequency [kHz]": {
                "test": 80,
                "path": ["properties", "laser_pulse_frequency"],
            },
            "Speed [mm/s]": {"test": 100, "path": ["properties", "speed"]},
            "Fluence [J/cm2]": {"test": 0.5, "path": ["properties", "fluence"]},
            "Power [%]": {"test": 75, "path": ["properties", "power_in_percent"]},
            "Recipe file": {"test": "test_scribing_recipe.xml", "path": ["recipe_file"]},
        },
    },
    "Close Space Sublimation": {
        "meta": {
            "material_gated": True,
            "numeric_config": [_MATERIALS_CONFIG],
            "boolean_config": [("milling", "Milling")],
            "config_defaults": {"materials": 1, "milling": False, "mixing_ratio": False},
        },
        # map_close_space_sublimation(); "Organic" is not stored. The sheet only writes
        # the "Source material ratio {n}" columns when materials > 1, and the parser reads
        # source materials 1 to 4.
        "fields": {
            "Material name": {"test": "CdTe", "path": ["layer", 0, "layer_material_name"]},
            "Layer type": {"test": "Absorber", "path": ["layer", 0, "layer_type"]},
            "Tool/GB name": {"test": "CSS tool", "path": ["location"]},
            "Organic": {"test": False},
            "Process pressure [mbar]": {
                "test": 40,
                "path": ["process", "pressure"],
                "unit_verified": False,
            },
            "Source temperature [°C]": {
                "test": 600,
                "path": ["process", "source_temperature"],
                "unit_verified": False,
            },
            "Substrate temperature [°C]": {
                "test": 500,
                "path": ["process", "substrate_temperature"],
                "unit_verified": False,
            },
            "Material state": {"test": "Powder", "path": ["process", "material_state"]},
            "Substrate source distance [mm]": {
                "test": 4,
                "path": ["process", "substrate_source_distance"],
                "unit_verified": False,
            },
            "Thickness [nm]": {
                "test": 500,
                "path": ["process", "thickness"],
                "unit_verified": False,
            },
            "Deposition Time [s]": {
                "test": 120,
                "path": ["process", "deposition_time"],
                "unit_verified": False,
            },
            "Carrier gas": {"test": "no", "path": ["process", "carrier_gas"]},
            "Notes": {"test": "Test note CSS"},
        },
        "indexed": {
            "materials": [
                {
                    "excel_key": "Source material name {n}",
                    "test": lambda n: "CdTe",
                    "path": [
                        "process",
                        "source_material_mixture",
                        "{i}",
                        "source_material",
                        "name",
                    ],
                    "config_key": "materials",
                },
                {
                    "excel_key": "Source material ratio {n}",
                    "test": lambda n: 1,
                    "path": ["process", "source_material_mixture", "{i}", "mixing_ratio"],
                },
            ]
        },
        "optional": {
            "milling": {
                "Milling rotation speed [rpm]": {
                    "test": 300,
                    "path": ["process", "process_preparation", "rotation_speed"],
                    "unit_verified": False,
                },
                "Milling rotation time [min]": {
                    "test": 30,
                    "path": ["process", "process_preparation", "rotation_time"],
                    "unit_verified": False,
                },
                "Milling rest time [min]": {
                    "test": 5,
                    "path": ["process", "process_preparation", "rest_time"],
                    "unit_verified": False,
                },
            }
        },
    },
    "Lamination": {
        # map_lamination() reads its own column names ("Temperature [°C]", "Time [s]",
        # "Stamp Material", ...), most of which peroTF's sheet spells differently, so only
        # the five columns below reach the archive; the rest carry no path. The step has
        # no method; smart_databaser recognises it by its entry type
        # (ENTRY_TYPES["lamination"]).
        "meta": {"material_gated": False, "numeric_config": [], "boolean_config": []},
        "fields": {
            "Interface": {"test": ""},
            "Tool/GB name": {"test": "Laminator", "path": ["location"]},
            "Temperature during process[°C]": {"test": 120},
            "Temperature at pressure relief [°C]": {"test": 60},
            "Pressure [MPa]": {
                "test": 1,
                "path": ["settings", "pressure"],
                "unit_verified": False,
            },
            "Force [N]": {"test": 100, "path": ["settings", "force"], "unit_verified": False},
            "Time lamination [s]": {"test": 300},
            "Heat up time [s]": {
                "test": 60,
                "path": ["settings", "heat_up_time"],
                "unit_verified": False,
            },
            "Cool down time [s]": {
                "test": 60,
                "path": ["settings", "cool_down_time"],
                "unit_verified": False,
            },
            "Total time [s]": {"test": 420},
            "Athmosphere in chamber": {"test": "Nitrogen"},
            "Humidity [%%rel]": {"test": 30},
            "Stamp 1 Material": {"test": "PDMS"},
            "Stamp 1 Thickness [mm]": {"test": 1},
            "Stamp 1 Area [mm^2]": {"test": 100},
            "Stamp 2 Material": {"test": "PDMS"},
            "Stamp 2 Thickness [mm]": {"test": 1},
            "Stamp 2 Area [mm^2]": {"test": 100},
            "Homogeniously pressed [1/0]": {"test": 1},
            "Sucessful adhesion [1/0]": {"test": 1},
            "Notes": {"test": "Test lamination"},
        },
    },
    "Annealing": {
        # map_annealing_class(). The step has no method; smart_databaser recognises it by
        # its entry type (ENTRY_TYPES["thermal_annealing"] and its lab variants).
        "meta": {"material_gated": False, "numeric_config": [], "boolean_config": []},
        "fields": {
            "Annealing time [min]": {
                "test": 60,
                "path": ["annealing", "time"],
                "unit_verified": False,
            },
            "Annealing temperature [°C]": {
                "test": 150,
                "path": ["annealing", "temperature"],
                "unit_verified": False,
            },
            "Annealing athmosphere": {"test": "Nitrogen", "path": ["annealing", "atmosphere"]},
            "Relative humidity [%]": {"test": 35, "path": ["atmosphere", "relative_humidity"]},
            "Notes": {"test": "Test annealing process"},
        },
    },
    "Generic Process": {
        # map_generic(). The step has no method; smart_databaser recognises it by its entry
        # type (ENTRY_TYPES["process"]).
        "meta": {"material_gated": False, "numeric_config": [], "boolean_config": []},
        "fields": {
            "Name": {"test": "Test Generic Process", "path": ["name"]},
            "Notes": {"test": "This is a test generic process"},
        },
    },
    "Multijunction Info": {
        # The parser creates no archive entry for this section, so it never autofills.
        "meta": {"material_gated": False, "numeric_config": [], "boolean_config": []},
        "fields": {
            "Recombination Layer": {"test": ""},
            "Notes": {"test": ""},
        },
    },
}

AVAILABLE_PROCESSES = ["Experiment Info"] + [k for k in PROCESSES if k != "Experiment Info"]


# ---------------------------------------------------------------------------
# Excel-generation API (kept from the upstream module; peroTF's sheet_experiment.py writes its
# labels inline and does not call these)
# ---------------------------------------------------------------------------


def _resolve_test(spec: dict, n: int | None = None):
    test = spec.get("test")
    if callable(test):
        return test(n)
    return test


def field_args(process_name: str, key: str, *, variant: str = "fields") -> tuple:
    """(key, test_value) ready for make_label(*field_args(...)) - looks up a single
    plain (non-indexed, non-optional) field. `variant` picks which field dict of the
    process to read ("fields" by default)."""
    spec = PROCESSES[process_name][variant][key]
    return (key, _resolve_test(spec))


def optional_block_args(process_name: str, block_key: str) -> list[tuple]:
    """[(key, test_value), ...] for every field in one optional block (e.g. Spin
    Coating's "gasquenching"), in declared order."""
    block = PROCESSES[process_name]["optional"][block_key]
    return [(key, _resolve_test(spec)) for key, spec in block.items()]


def indexed_group_args(process_name: str, group_key: str, n: int) -> list[tuple]:
    """[(formatted_key, test_value), ...] for one iteration (1-based n) of an indexed
    group (e.g. Spin Coating's "solvents"), in declared order."""
    entries = PROCESSES[process_name]["indexed"][group_key]
    return [(entry["excel_key"].format(n=n), _resolve_test(entry, n)) for entry in entries]


def atmospheric_args() -> list[tuple]:
    """[(key, test_value), ...] for the atmospheric block; always empty for peroTF (see
    _ATMOSPHERIC_FIELDS)."""
    return [(key, _resolve_test(spec)) for key, spec in _ATMOSPHERIC_FIELDS.items()]


# ---------------------------------------------------------------------------
# smart_databaser-facing API: archive field-path lookups
# ---------------------------------------------------------------------------


def _field_paths(spec: dict) -> list | None:
    if "paths" in spec:
        return spec["paths"]
    if "path" in spec:
        return [spec["path"]]
    return None


def _resolve_indexed_path(path_template: list, index0: int) -> list:
    return [index0 if segment == "{i}" else segment for segment in path_template]


def build_field_paths(
    processes: dict | None = None,
) -> dict[str, dict[str, tuple[list[list], bool]]]:
    """{process_type: {excel_field_key: (paths, unit_verified)}}. A field with neither
    "path" nor "paths" (deliberately unmapped, e.g. Notes) is simply absent. Indexed
    entries may give "path" or "paths" (alternatives), each with "{i}" placeholders. Pass
    `processes` to build from a different PROCESSES-shaped dict (e.g. a small synthetic
    one in a test) instead of the real module-level PROCESSES."""
    result: dict[str, dict[str, tuple[list[list], bool]]] = {}
    for process_type, spec in (processes if processes is not None else PROCESSES).items():
        field_paths: dict[str, tuple[list[list], bool]] = {}
        for key, field_spec in spec.get("fields", {}).items():
            paths = _field_paths(field_spec)
            if paths is not None:
                field_paths[key] = (paths, field_spec.get("unit_verified", True))
        for block in spec.get("optional", {}).values():
            for key, field_spec in block.items():
                paths = _field_paths(field_spec)
                if paths is not None:
                    field_paths[key] = (paths, field_spec.get("unit_verified", True))
        for group in spec.get("indexed", {}).values():
            for entry in group:
                start, end = entry.get("mapping_range", (1, 5))
                templates = entry.get("path_templates") or _field_paths(entry)
                if templates is None:
                    continue
                for n in range(start, end + 1):
                    excel_key = entry["excel_key"].format(n=n)
                    field_paths[excel_key] = (
                        [_resolve_indexed_path(t, n - 1) for t in templates],
                        entry.get("unit_verified", True),
                    )
        result[process_type] = field_paths
    return result


def build_indexed_config_keys(processes: dict | None = None) -> dict[str, dict[str, str]]:
    """{process_type: {config_key: excel_key_template}}, used by smart_databaser's
    infer_config_from_source_step to widen a target process's config to match how much data
    a source batch step actually has. Only considers entries that carry an archive path, so
    a process with no path data at all (e.g. Seq-Evaporation) yields nothing here. Pass
    `processes` to build from a different PROCESSES-shaped dict."""
    result: dict[str, dict[str, str]] = {}
    for process_type, spec in (processes if processes is not None else PROCESSES).items():
        mapping = {}
        for group_key, group in spec.get("indexed", {}).items():
            for entry in group:
                has_path = "path" in entry or "paths" in entry or "path_templates" in entry
                if has_path and entry.get("config_key") == group_key:
                    mapping[group_key] = entry["excel_key"]
                    break
        if mapping:
            result[process_type] = mapping
    return result


def build_field_value_multipliers(processes: dict | None = None) -> dict[str, dict[str, float]]:
    """{process_type: {excel_field_key: multiplier}}. Pass `processes` to build from a
    different PROCESSES-shaped dict."""
    result: dict[str, dict[str, float]] = {}
    for process_type, spec in (processes if processes is not None else PROCESSES).items():
        multipliers: dict[str, float] = {}
        for key, field_spec in spec.get("fields", {}).items():
            if "multiply" in field_spec:
                multipliers[key] = field_spec["multiply"]
        for block in spec.get("optional", {}).values():
            for key, field_spec in block.items():
                if "multiply" in field_spec:
                    multipliers[key] = field_spec["multiply"]
        for group in spec.get("indexed", {}).values():
            for entry in group:
                if "multiply" not in entry:
                    continue
                start, end = entry.get("mapping_range", (1, 5))
                for n in range(start, end + 1):
                    multipliers[entry["excel_key"].format(n=n)] = entry["multiply"]
        if multipliers:
            result[process_type] = multipliers
    return result


# ---------------------------------------------------------------------------
# GUI metadata API: process-type lists derived from "meta"
# ---------------------------------------------------------------------------


def build_configurable_process_types() -> set[str]:
    return {
        p
        for p, spec in PROCESSES.items()
        if spec["meta"]["numeric_config"] or spec["meta"]["boolean_config"]
    }


def build_material_gated_process_types() -> set[str]:
    return {p for p, spec in PROCESSES.items() if spec["meta"]["material_gated"]}


def build_default_config_by_process_type() -> dict[str, dict]:
    return {
        p: dict(spec["meta"]["config_defaults"])
        for p, spec in PROCESSES.items()
        if spec["meta"].get("config_defaults")
    }


def build_numeric_config_fields() -> list[tuple[str, str, set[str], int, int]]:
    """[(config_key, label, applicable_process_types, min, max), ...], grouped from each
    process's own declared numeric_config entries; a (key, label, min, max) combination is
    assumed identical everywhere it is declared."""
    grouped: dict[tuple[str, str, int, int], set[str]] = {}
    for process_type, spec in PROCESSES.items():
        for key, label, min_val, max_val in spec["meta"]["numeric_config"]:
            grouped.setdefault((key, label, min_val, max_val), set()).add(process_type)
    return [(key, label, types, mn, mx) for (key, label, mn, mx), types in grouped.items()]


def build_boolean_config_fields() -> list[tuple[str, str, set[str]]]:
    """[(config_key, label, applicable_process_types), ...]."""
    grouped: dict[tuple[str, str], set[str]] = {}
    for process_type, spec in PROCESSES.items():
        for key, label in spec["meta"]["boolean_config"]:
            grouped.setdefault((key, label), set()).add(process_type)
    return [(key, label, types) for (key, label), types in grouped.items()]
