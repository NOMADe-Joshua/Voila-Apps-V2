# Voila-Apps-V2: peroTF NOMAD Analysis Apps monorepo

A suite of Voila/Jupyter apps for perovskite solar cell characterization,
built around the peroTF NOMAD Oasis at KIT. Each app lives in `apps/<AppName>/`
and can run standalone; shared logic lives in `shared/perotf_utils/`. The
structure mirrors HZB's `nomad-hzb/nomad-pv-analysis-apps` (this repo is a
GitHub fork of it, remote `upstream`) so apps can be exchanged; see
`CONTRIBUTING.md` section 5. The per-app checklist for deeper unification
passes is `UNIFICATION_PROMPT.md`; read it in full before doing one. This file
is the condensed, everyday version.

## How the apps run: Voila on NORTH

Every app is a Jupyter notebook served by Voila: Voila runs all cells top to
bottom in a fresh kernel and shows only their outputs (widgets, HTML, plots),
never the code; users cannot edit or re-run cells. Everything interactive after
that first run happens in ipywidgets callbacks. What follows from that:

- **On the Oasis** the `voila` NORTH tool runs the notebooks in a per-user
  container with the repo upload mounted (`/home/jovyan/uploads/<hash>/`); the
  App Dashboard links into it via `NORTH_ENDPOINT`. NOMAD sets
  `NOMAD_CLIENT_ACCESS_TOKEN`, `NOMAD_CLIENT_USER` and `JUPYTERHUB_USER` there,
  so apps authenticate without a login. Outside NORTH they fall back to
  username/password (or an exported `NOMAD_CLIENT_ACCESS_TOKEN`).
- **One kernel per browser tab.** Opening or reloading the page starts a new
  kernel that runs the notebook again; closing the tab shuts it down. No state
  survives a reload, and an edited `.py` module takes effect on the next page
  load (in JupyterLab only after a kernel restart).
- **Every cell's stdout ends up in the UI**: `print()`, import banners and the
  value of a cell's last expression. Hence the `_ =` in cell 0 and the banner
  silencing in `bootstrap.py`.
- **Errors are invisible by default.** An exception while a cell runs shows
  only Voila's generic "error when executing cell" note (the traceback needs
  `--show_tracebacks=True`), and an exception inside a widget callback shows
  nothing at all. Catch errors in callbacks and show them in the app (an
  `Output` or `HTML` status widget, `perotf_utils.error_handler.ErrorHandler`).
- **`display()` from a callback** needs an `Output()` widget, see the gotcha
  below.

**Running an app locally** (Windows): use the repo's `.venv` (the `python` on
PATH lacks the dependencies) and start Voila from the app folder, because
cell 0 resolves `../../bootstrap.py` relative to it:
```bash
cd apps/Process_JV_Overview
../../.venv/Scripts/python.exe -m voila process_jv_overview.ipynb --show_tracebacks=True
```
The app is then at `http://localhost:8866`. Tests and lint use the same
environment (`.venv/Scripts/python.exe -m pytest tests -m "not live"`,
`.venv/Scripts/ruff.exe`). The Oasis may not be reachable from the dev machine
(it refused connections during a Claude session on 2026-11-03), so behaviour
against live data is checked in NORTH. Tear down whatever you start (see the
gotcha below).

## Layout

```
apps/<AppName>/
    pyproject.toml
    app.py                  # entry point of modular apps, imports the rest as plain names
    data_manager.py         # modular apps; ideally zero widget imports
    plot_manager.py         # modular apps; ideally zero widget imports
    gui_components.py       # modular apps; ipywidgets code
    <app>.ipynb             # cell 0 is always the bootstrap cell
shared/perotf_utils/        # DO NOT DUPLICATE ANYTHING FROM HERE
    config.py               # URL_BASE, API_ENDPOINT, GUI_ENDPOINT, NORTH_ENDPOINT, ENTRY_TYPES: the ONLY place
    api_calls.py, access_token.py, auth_manager.py, auth_ui.py,
    batch_selection.py, error_handler.py, plotting_utils.py, process_handling.py
    process_specs.py        # smart_databaser's process catalog, see below
shared/utils.ipynb          # admin notebook (old usage dashboard + backup zip), not an app
tests/<AppName>/            # ONE folder per app, at repo root, never inside apps/
    conftest.py
    test_<app_name>.py      # exactly one test file per app
tests/structure/            # repo-wide rules (literals, bootstrap cell, pyproject)
tests/shared/               # perotf_utils
tests/conftest.py           # load-bearing, see gotcha below
pyproject.toml              # root: pytest config + the ONLY ruff config in the repo
```

Two app shapes exist after the migration from the old flat repo
(`nomad-perotf-jupyter-voila-scripts`):

- **Modular apps** (JV-Analysis, Process_JV_Overview, EQE_Analysis,
  AbsPL_Analysis, UVVis_Analyzer, XRD_PF, DesignOfExperiments, Excel_creator,
  smart_databaser):
  `app.py` plus modules, and a notebook with exactly 3 code cells (bootstrap,
  `log_notebook_usage()`, start the app).
- **Notebook apps** (all others): the analysis code still lives in the
  notebook cells, with only the bootstrap cell and config imports added. Moving
  that code into `app.py` + modules is the next unification step per app.

## Hard rules: apply to every edit in `apps/`

1. **Never duplicate `perotf_utils` code.** If logic already exists there
   (auth, API calls, plotting helpers, error handling), import it; don't
   reimplement it in an app. If something is genuinely missing and should be
   shared, propose adding it there; don't silently create a new shared module.
2. **Don't touch `shared/perotf_utils/` unless explicitly asked.** It's shared
   across every app; a change there is cross-cutting and needs to be flagged
   and approved first, not applied inline while working on one app.
3. **Import convention:** shared modules always get the `perotf_utils.` prefix
   (`from perotf_utils.config import URL_BASE`, `from perotf_utils import
   access_token`). App-local modules (`data_manager`, `plot_manager`,
   `gui_components`, `utils`, `config`) are imported as plain names, never
   prefixed.
4. **The server address, its paths and NOMAD entry type names are never
   literals** in an app, a notebook or another shared module. Import them from
   `perotf_utils.config` (`URL_BASE`, `API_ENDPOINT`, `GUI_ENDPOINT`,
   `NORTH_ENDPOINT`, `ENTRY_TYPES["jv"]`, ...) **directly, without a
   `try/except` fallback literal**: `bootstrap.py` guarantees the package, and a
   fallback would scatter the address across the repo again (HZB uses a
   fallback; we deliberately don't). A new entry type gets a key in
   `ENTRY_TYPES` first. `tests/structure/test_repo_structure.py` fails on
   `elnserver`, `/nomad-oasis`, `peroTF_`, `HySprint_` or `baseclasses.` outside
   `config.py`, comments and display strings included (the HZB pattern is the host
   `nomad-hzb-se.`, so a GitHub link to an HZB repo is fine).
5. **No bare `print()`** for status/debug/errors in new code: use
   `logging.getLogger(__name__)` at module level, appropriate levels, and always
   `%s`/`%d` placeholders (never an f-string as the log message itself).
   **Exception:** `print()` inside `with some_ipywidgets_output:` to render into
   an `Output()` widget is a legitimate display mechanism; don't convert it
   blindly. Legacy apps still have many prints (see Known gaps).
6. **Run `ruff check --fix --unfixable F401` and `ruff format`** on every file
   you touch; leave `ruff check` clean. `F401` is excluded from autofix because
   several modules re-export names on purpose (e.g. JV's `gui_components`
   re-exports `AuthenticationUI`); mark real re-exports `# noqa: F401`. The ruff
   config lives ONLY in the root `pyproject.toml`.
7. **`pyproject.toml` per app** declares `"perotf-utils"` as a bare
   requirement plus every third-party package the app imports (`bootstrap.py`
   installs the app's own directory from cell 0, so this list is what actually
   installs an app's requirements on the Oasis). Never pin a
   `file:///home/jovyan/uploads/<hash>/shared` path. Also needs
   `[tool.hatch.metadata] allow-direct-references = true` and
   `[tool.hatch.build.targets.wheel] packages = ["."]`. `pytest`/`pytest-mock`
   belong only in CI and the root, never per-app.
8. **Notebooks start with the bootstrap cell** (see gotcha below). Modular
   apps' notebooks have exactly 3 code cells. No `sys.path.append`/`insert`
   anywhere in an app file or notebook; `bootstrap.py` is the one exception.
   An app that builds on another app's modules (smart_databaser uses
   Excel_creator's `sheet_experiment`/`experiment_excel_builder`) declares it
   in its `pyproject.toml` instead:
   ```toml
   [tool.perotf]
   uses-apps = ["Excel_creator"]
   ```
   `bootstrap.py` then appends `apps/Excel_creator/` to `sys.path` (after the
   app's own folder, so same-named modules of the calling app win), and the
   `app_loader` test fixture does the same. A change to such a shared app module
   can break the dependent app: run both apps' tests.
9. **Tests live at `tests/<AppName>/test_<app_name>.py`**, never inside
   `apps/`. A per-app `conftest.py` gets the app's modules through the root
   `app_loader` fixture (`app_loader("JV-Analysis", ["app", "data_manager"])`),
   and test files use those module objects instead of importing
   `data_manager` & co. by bare name, so two apps' same-named modules never
   collide. Tests must not reach the network (an autouse fixture makes every
   `requests` call fail unless the test is marked `live`).
10. **No em-dashes in any output you produce.**
11. **No regressions.** If making a checklist item pass would break an app's
    currently-working behavior or an already-passing test, stop and flag it;
    don't force the fix through.

## Smart Databaser, Excel_creator and `process_specs.py`

`apps/smart_databaser` (ported from HZB) reads the processing steps of earlier
NOMAD batches and autofills a new experiment Excel, which it writes through
Excel_creator's own `sheet_experiment.add_experiment_sheet` /
`ExperimentExcelBuilder` (declared via `[tool.perotf] uses-apps`). Its process
catalog is `shared/perotf_utils/process_specs.py`: per process type the Excel
column labels, test values and the archive path each label is autofilled from
(paths follow the nomad-baseclasses `map_*` functions that nomad_perotf's
experiment parser calls). Unlike at HZB, our Excel_creator does NOT read
`process_specs.py`; the catalog has to mirror the labels `sheet_experiment.py`
writes. `tests/smart_databaser` checks that for every process type, so a label
change in Excel_creator fails there: update the catalog in the same change.
Process classes whose archive steps carry no `method` (generic process, thermal
annealing incl. CR_/TFL_ variants, lamination) are recognised by their m_def,
taken from `ENTRY_TYPES`. Only confirm a path against the real `map_<type>`
function, never guess; mark unconfirmed units `unit_verified: False`.

## NOMAD process data: what the archive actually holds

Verified against the backend sources listed below:

- **Values come in the schema's unit**, not in SI and not in the Excel column's
  unit: NOMAD converts an assigned quantity to the unit its `Quantity` declares
  and stores the magnitude (nomad-FAIR `metainfo/data_type.py`, `normalize`).
  Evaporation sources, for example, hold `thickness` in nm, `pressure`,
  `pressure_start` and `pressure_end` in mbar, `temparature` in °C and the
  rates in angstrom/s, while the Excel columns say `[bar]`; the parser converts.
- **Unset quantities are left out of the JSON**, so the variations of one step
  often differ in which keys and how many list entries (e.g. evaporation
  sources) they have. `perotf_utils.process_handling.merge_step_data` therefore
  groups the processes of a step by class (`m_def`) and fills gaps with `None`;
  don't go back to grouping by key structure.
- Field names keep the schema's spelling: `positon_in_experimental_plan`,
  `temparature`, `substrate_temparature`.
- `positon_in_experimental_plan` is the index of the step's column group in the
  experiment Excel (`Experiment Info` is 0, Excel_creator labels the groups
  `<n>: <Process>`). Step types the parser skips leave gaps in it.
- The experiment Excel stays in the upload as the mainfile of the experiment
  entry, but the apps show only what is stored in NOMAD and never read the
  Excel back (user decision 2026-11-03; an Excel fallback in
  Process_JV_Overview was removed again). A value missing in NOMAD is fixed in
  the parser, not worked around in an app.

Backend sources, a read-only reference: change nothing there from this repo
unless the user asks. On the main dev machine they are under
`\\wsl$\Ubuntu\home\joshua\nomad-distro-dev\packages\`:
- `nomad-perotf/src/nomad_perotf/schema_packages/perotf_package.py`: the peroTF classes
- `nomad-perotf/src/nomad_perotf/parsers/perotf_batch_parser.py`: the experiment Excel parser
- `nomad-baseclasses/src/baseclasses/`: the base sections; `helper/solar_cell_batch_mapping.py`
  holds the `map_*` functions the parser calls
- `nomad-FAIR/`: NOMAD itself

peroTF-specific backend changes go into nomad-perotf only. nomad-baseclasses is
shared by many groups and is not changed for peroTF (user decision 2026-11-03).

## Change management: versions, commits, releases

We work directly in our own repo `NOMADe-Joshua/Voila-Apps-V2`: a change needs
no GitHub issue and no PR, so don't propose filing one. `CONTRIBUTING.md`
sections 1, 2 and 4 still describe the older issue/PR process; where they
differ, this section wins.

- **Commit only when the user asks**, on the current branch, with a
  descriptive message that names the app (e.g. `Process_JV_Overview: keep every
  evaporation source in the step tables`). The commit messages are the
  changelog.
- **Bump that app's `pyproject.toml` `version`** (SemVer: patch for a fix,
  minor for a non-breaking feature, major for a breaking change) in the same
  change, for that app only. Not for internal refactors, test-only changes, or
  `shared/perotf_utils/` edits.
- The repo is still a GitHub fork of HZB's: remote `upstream` and a plain
  `gh pr create` point at `nomad-hzb/nomad-pv-analysis-apps`. Never push to or
  open a PR against HZB unless the user asks for it.
- "What's new" is the GitHub Releases page, linked from the App Dashboard
  (`apps/App_dashboard/gui_components.py::WHATS_NEW_URL`).
  `gh release create <tag> --generate-notes` only lists merged PRs, so write the
  notes from the commits since the last tag (`git log <last-tag>..HEAD
  --oneline`) and pass them with `--notes-file`.

## Known environment gotcha: `tests/conftest.py` is load-bearing

1. A gitignored root `secrets.py` would shadow the *stdlib* `secrets` module
   whenever the repo root is on `sys.path[0]` (default for `python -m pytest`
   from the root). numpy and plotly's `narwhals` need `secrets.randbits` /
   `secrets.token_hex`, so without the fix almost every test fails with
   `ImportError: cannot import name 'randbits'/'token_hex' from 'secrets'`.
   `tests/conftest.py` strips the repo root from `sys.path` first.
2. It puts `shared/` on `sys.path`, provides `app_loader` (imports an app's
   modules with the app dir on `sys.path` only while importing, then restores
   `sys.modules` so the next app's `data_manager` is not shadowed) and the
   autouse no-network guard.

Because of (2) and the unique `test_<app_name>.py` basenames, the whole suite
runs in one go (`python -m pytest tests -m "not live"`), unlike in HZB's repo.
If numpy/pandas import errors or cross-app module mix-ups appear in tests,
check this file first.

## Known environment gotcha: `display()` inside a widget callback needs an `Output()` under Voila

A plain `display(...)` call (e.g. `display(Javascript(...))`) made from inside
an ipywidgets event callback (`Button.on_click`, `observe`, ...) is **silently
dropped under Voila**. The callback fires from a comm message, not a cell
execution, so there's no current output area; classic Jupyter has fallback
routing for this, Voila does not.

**How to apply:** route such calls through a real `ipywidgets.Output()` that
stays part of the displayed widget tree:
```python
js_output = widgets.Output(layout=widgets.Layout(width="0px", height="0px"))
# js_output must remain in the tree passed to display(app) / returned by setup_app


def on_click(_button):
    with js_output:
        js_output.clear_output(wait=True)
        display(Javascript("..."))
```
See `apps/App_dashboard/app.py::setup_app` (the `js_output` widget).

## Known environment gotcha: always tear down local test processes (Voila, kernels, Playwright)

`python -m voila` spawns a server plus one kernel per browser connection; a
Playwright script launches its own Chromium. None of these self-terminate
reliably when a script errors out or times out, and across a long session they
pile up until even `tasklist`/PowerShell stop responding. Every time you launch
`voila`, a notebook executor or Playwright for manual verification, track the
PID/port and kill it once you're done. On Windows, if `tasklist`/PowerShell
hang, use Git Bash's `ps aux` / `kill -9 <pid>`.

## Known environment gotcha: every notebook bootstraps via `bootstrap.py`, never its own install cell

`perotf_utils` becomes importable in the *current* kernel only if something
puts `shared/` on `sys.path` directly; a plain `pip install` needs a kernel
restart first (the "Voila apps need to be run twice" problem). Every
notebook's cell 0 is exactly:
```python
import runpy

_ = runpy.run_path("../../bootstrap.py")
```
The `_ =` is load-bearing: `runpy.run_path()` returns the executed module's
globals, and a notebook auto-displays the last expression, so without the
binding cell 0 dumps every bootstrap global into the app's UI under Voila.

`bootstrap.py` (repo root):
- applies `oasis_local_config.py` (repo root, gitignored, opt-in): every
  uppercase string it defines becomes an environment variable, so
  `PEROTF_URL_BASE` reaches `perotf_utils.config` before any app imports it and
  `HTTP_PROXY`/`HTTPS_PROXY` are set before pip runs. Container-level variables
  win. No proxy is applied by default (HZB's version defaults to the HZB proxy;
  ours deliberately does not).
- installs `shared/` and inserts it into `sys.path` (a sanctioned exception to
  rule 8; fatal if it fails and the package cannot be imported).
- installs **the app's own directory** when the cwd has a `pyproject.toml`
  (once per container, keyed on path + `pyproject.toml` contents; a failure
  only warns).
- appends the folders of sibling apps listed under `[tool.perotf] uses-apps`
  in that `pyproject.toml` to `sys.path` (see rule 8).
- silences import-time stdout banners for the rest of the kernel's life
  (stderr untouched; `PEROTF_KEEP_IMPORT_OUTPUT=1` disables it).

Don't reimplement any of this per app. See `DEPLOYMENT.md` for the deployment
side.

## Known gaps (tracked, not silently fixed)

- **Notebook apps are still monolithic** (MPPT_Analysis,
  Data_Tools, SEM_crystal_counter, UVVis_Simulator). Next step per app: move
  the code into
  `app.py` + modules and reduce the notebook to 3 cells, following
  `UNIFICATION_PROMPT.md`.
- **No app has gone through the full checklist yet**: no Pydantic row models,
  no `load_offline` demo mode or fixtures, tests are import/construction smoke
  tests only, and most apps still use `print()` (so `T20` is not in the ruff
  ruleset).
- `Process_JV_Overview` keeps its own copies of JV-Analysis modules
  (`plot_manager`, `utils`, `resizable_plot_utility`, ...) that have drifted
  slightly; consolidating them is a separate change.
- `perotf_utils.auth_manager.AuthenticationManager.authenticate_with_token()`
  calls `access_token.get_token(self.url_base)` with the bare host instead of
  `URL_BASE + API_ENDPOINT`. Harmless while `NOMAD_CLIENT_ACCESS_TOKEN` is set
  (always the case in NORTH), wrong for the interactive fallback. Pre-existing.
- The `KIT_` lab-ID prefix is still written literally in `Excel_creator`
  (Excel ID formula) and `Data_Tools` (renamers). If it should become
  configurable, add it to `perotf_utils.config` first.
- `apps/Excel_creator/sheet_how_to_cite.py` writes a "How to Cite" sheet into
  every generated workbook that cites HZB's `nomad-hzb/nomad-hysprint` schema
  repo and names the "nomad-hzb-se OASIS"; `sheet_data_entry_guide.py` links an
  HZB scribehow how-to, and its example values name HZB tools
  ("HZB-HySprintBox", "Hysprint Evap"). `apps/JV-Analysis/manual.html` (not
  loaded by the app) still addresses "HZB Users". All unchanged from the old
  repo; what peroTF content should say there is a content decision, not a
  structural one, and needs a version bump when changed.
- `log_notebook_usage()` writes next to `perotf_utils/access_token.py`, i.e.
  `shared/perotf_utils/notebook_usage.log` inside the upload; the log contains
  user names and is gitignored. `apps/log_view` (dashboard card "Usage Log" under
  Administration) and `shared/utils.ipynb` read it from there. The card and the
  data are admin-only: `perotf_utils.config.ADMIN_USERS` (default `nomade`,
  override `PEROTF_ADMIN_USERS`) is compared with `NOMAD_CLIENT_USER`; the
  dashboard hides `AppEntry(admin_only=True)` cards for everyone else
  (`data_manager.visible_categories`) and `log_view` checks again itself, since
  the notebook URL still works. This is a display rule, not file access control:
  anyone with access to the upload can still open the log file itself.
- Not in this repo on purpose; all remain in `nomad-perotf-jupyter-voila-scripts`:
  - targeted the HZB server: `File_Uploader`, `Ink_Jet_Absorber_Analysis`,
    `NMR_Analysis`;
  - never used by the group and never adapted to it (removed after the
    migration): `Diode_Analyzer`, `XPS-Automated`, `Wetting_envelope`,
    `Perovskite_calculator` (the latter came with the original HZB scripts and
    is no longer in HZB's repo either), `Peak_Explorer` (TRPL, not in the
    ELN), `Data_Overview_Machines`, `Hansen_green_calculator`, and `SEM_crystal_counter`'s crystal counter
    notebooks (`SEM_Analyzer*.ipynb`, `SEM_bad.ipynb`; only the grain size
    analysis `image_analysis.ipynb` is kept).
  - HZB extras dropped from this fork: the `Learning/` tutorials, the
    `NOMAD_DATA_ACCESS_PROMPT.md` LLM reference with its dashboard section
    "Build Your Own", and the git hooks that reset `Learning/` on pull.
- **Smart Databaser is untested against live peroTF data** (no token was
  available during the port; HZB's live tests were not ported). Most numeric
  catalog paths are `unit_verified: False`; solvent volume is probably off by
  1000 (schema ml vs. column uL) and needs checking in the NOMAD GUI before a
  multiplier is added. Not autofillable because nomad_perotf's parser does not
  store the data: Seq-Evaporation (stored as an evaporation without sources, see
  below), Multijunction Info, most Lamination columns, Inkjet waveform and
  gas/vacuum quenching columns. Laser Scribing is no longer offered at all
  (Excel_creator 1.1.0): the parser deliberately creates no entry for it. HZB's child-sample `_C-n`
  ids were dropped (peroTF ids have no such suffix), so the GUI no longer
  creates child rows.
- **Seq-Evaporation sources are not in NOMAD**: nomad-baseclasses'
  `map_evaporation()` returns before adding any source when the "Organic"
  column is missing, which is always the case for Seq-Evaporation. Being fixed
  in nomad-perotf's own parser (`parsers/perotf_mapping.py`, uncommitted as of
  2026-11-03). Existing uploads keep their entries without sources: the parser
  never overwrites a process entry it already created
  (`create_archive(..., overwrite=False)`).
- Still open, as at HZB: whether this repo should become an installable NOMAD
  plugin (NORTH tool entry points, Docker images). Nothing of that exists; don't
  scaffold it without explicit sign-off.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community
structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when
  graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for
  relationships and `graphify explain "<concept>"` for focused concepts. These
  return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw
  grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of
  raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when
  query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current
  (AST-only, no API cost).
- Notebook-only apps are mostly invisible to the graph (it extracts `.py`
  files); search their `.ipynb` files directly.
