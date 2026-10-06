# peroTF NOMAD Analysis Apps

A suite of web-based analysis and visualization tools for perovskite solar cell
research, developed by the peroTF group at the
[Karlsruhe Institute of Technology (KIT)](https://www.kit.edu).

The apps run as Voila dashboards on the group's NOMAD Oasis and cover the
characterization workflow from JV and MPPT analysis to EQE, absolute PL, UV-Vis
and XRD, plus calculators and data-handling tools.

The repo structure follows HZB's
[nomad-pv-analysis-apps](https://github.com/nomad-hzb/nomad-pv-analysis-apps),
from whose earlier `nomad-hysprint-jupyter-scripts` (Michael Götte, Edgar
Nandayapa) these apps originally descend, so apps can be exchanged between the
two repos (see `CONTRIBUTING.md`).

---

## Apps

| App | Folder | Description |
|---|---|---|
| App Dashboard | `App_dashboard` | Entry point with a card for every app |
| JV Analysis | `JV-Analysis` | JV curve analysis: statistics, hysteresis, best devices, PPTX and Excel export |
| Process JV Overview | `Process_JV_Overview` | Processing steps of a batch next to its JV results |
| MPPT Analysis | `MPPT_Analysis` | Maximum power point tracking curves and fits |
| EQE Analysis | `EQE_Analysis` | EQE spectra and integrated Jsc against AM1.5G |
| Diode Analyzer | `Diode_Analyzer` | Diode-model fits of uploaded IV curves |
| AbsPL Analysis | `AbsPL_Analysis` | Absolute PL spectra, peak fits, QFLS and PLQY |
| UV-Vis Analyzer | `UVVis_Analyzer` | UV-Vis spectra from NOMAD |
| XRD Peak Fitting | `XRD_PF` | XRD pattern peak detection and fitting |
| Peak Explorer | `Peak_Explorer` | Interactive peak identification in uploaded spectra |
| SEM Crystal Counter | `SEM_crystal_counter` | Grain counting and size statistics from SEM images |
| XPS Automated | `XPS-Automated` | XPS spectra alignment (experimental) |
| Data Overview Machines | `Data_Overview_Machines` | What was measured and processed in the last week |
| Data Tools | `Data_Tools` | Converters and renamers for the ELN naming scheme |
| Excel Creator | `Excel_creator` | Experiment planning workbooks for NOMAD uploads |
| Design of Experiments | `DesignOfExperiments` | DoE planning and sampling |
| Hansen Green Calculator | `Hansen_green_calculator` | Hansen solubility parameters and green solvent blends |
| Perovskite Calculator | `Perovskite_calculator` | Precursor solution calculator |
| UV-Vis Simulator | `UVVis_Simulator` | Thin-film optics from a refractive index library |
| Wetting Envelope | `Wetting_envelope` | Wetting envelope plotter (Owens-Wendt) |

---

## Repository structure

```
Voila-Apps-V2/
├── bootstrap.py              # run by cell 0 of every notebook: installs shared/ and the app
├── shared/
│   ├── perotf_utils/         # shared library, imported as perotf_utils.<module>
│   │   ├── config.py         # the ONLY place for server URL, paths and NOMAD entry types
│   │   ├── api_calls.py, access_token.py, auth_manager.py, auth_ui.py,
│   │   └── batch_selection.py, error_handler.py, plotting_utils.py, process_handling.py
│   ├── utils.ipynb           # admin: usage-log dashboard and backup zip
│   └── log_view.ipynb        # admin: usage-log viewer
├── apps/<AppName>/           # one folder per app: pyproject.toml, notebook(s), modules
├── tests/<AppName>/          # one test folder per app, plus tests/structure and tests/shared
├── Learning/                 # tutorial notebooks
└── scripts/                  # fixture generator and git helpers
```

## Configuration

The server address, its URL paths and the NOMAD entry type names (`peroTF_Batch`,
`peroTF_JVmeasurement`, ...) are defined once, in
`shared/perotf_utils/config.py`. Apps import them from there; a test fails if
any of them appears as a literal anywhere else.

To point the apps at a different Oasis, override them with environment
variables instead of editing the file:

```bash
export PEROTF_URL_BASE=https://your-oasis.example.org
export PEROTF_API_ENDPOINT=/nomad-oasis/api/v1
```

On an Oasis, put the same names into a gitignored `oasis_local_config.py` next
to `bootstrap.py`; see [DEPLOYMENT.md](DEPLOYMENT.md).

For authentication the apps use `NOMAD_CLIENT_ACCESS_TOKEN`, which NOMAD sets
inside its NORTH tools, or offer a username/password login.

## Running an app locally

```bash
git clone https://github.com/NOMADe-Joshua/Voila-Apps-V2.git
cd Voila-Apps-V2
pip install -e ./shared -r requirements.txt voila
cd apps/JV-Analysis
voila jv-analysis.ipynb
```

The notebook's first cell runs `bootstrap.py`, which installs `shared/` and
the app's own dependencies on first launch. The app is then at
`http://localhost:8866`.

## Tests and linting

```bash
pip install pytest pytest-mock ruff
python -m pytest tests -m "not live"              # everything except live-server tests
python -m pytest tests/JV-Analysis                # one app
ruff check . && ruff format --check .
```

## Build your own analysis (with an LLM)

To query the Oasis from a notebook, a script or a chatbot, paste
[`NOMAD_DATA_ACCESS_PROMPT.md`](NOMAD_DATA_ACCESS_PROMPT.md) into the
conversation. It covers authentication, the two query endpoints, the peroTF
entry types and worked examples.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the issue, PR and versioning
process, and `CLAUDE.md` for the code conventions.

## Contact

peroTF group, Karlsruhe Institute of Technology (KIT).
GitHub: [@NOMADe-Joshua](https://github.com/NOMADe-Joshua)

## License

MIT License, see [LICENSE](LICENSE).
