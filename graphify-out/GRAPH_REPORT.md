# Graph Report - Voila-Apps-V2  (2026-10-06)

## Corpus Check
- 164 files · ~170,387 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 44 file(s) not represented in the graph (top: .ipynb 39, (none) 2, .csv 1)

## Summary
- 3048 nodes · 4663 edges · 208 communities (50 shown, 158 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 216 edges (avg confidence: 0.85)
- Token cost: 133,609 input · 0 output

## Community Hubs (Navigation)
- Hansen UNIFAC and External Imports
- Data Tools File Converters
- Diagnostics and Resizable Plots
- Excel Experiment Builder
- App Dashboard Catalog
- JV Export Utilities
- AbsPL GUI Components
- DoE Data Processing
- DoE Application
- DoE Sampling Base
- XRD Peak Analysis App
- DoE Maximin Sampling
- JV Curve Analysis UI
- Process JV Data Manager
- DoE Variables and Plots
- DoE Data Manager
- UVVis Common Widgets
- JV Data Manager
- XRD GUI Components
- Shared Auth UI
- Shared Module Imports
- AbsPL Plot Manager
- Batch Loading and Fixtures
- Shared NOMAD API Calls
- Drag-and-Drop Upload Widget
- JV Filter UI
- XRD GUI Layouts
- JV Plot UI
- Peak Explorer Export
- Bootstrap Installer
- Dashboard Tests
- EQE Analysis App
- UVVis Analysis App
- UVVis Plot Manager
- XRD Spectrum Data
- JV Color Schemes
- EQE Data Manager
- MPPT Fitting Tools
- Peak Explorer Peak Detection
- XRD Fitting Engine
- XRD Peak Detector
- JV Analysis App
- XRD CSV Loader
- Repo Conventions Docs
- App Package Manifests
- auth manager
- XRD PF fitting engine
- UVVis Analyzer common widgets
- XRD PF exporters
- XRD PF plot manager
- UNIFICATION PROMPT
- JV-Analysis gui components
- XRD PF gui layouts
- EQE Analysis plot manager
- Peak Explorer pl fitting models
- test repo structure
- DesignOfExperiments gui components (2)
- XRD PF data manager
- AbsPL Analysis app
- AbsPL Analysis data manager
- EQE Analysis gui components
- JV-Analysis data manager
- auth manager (2)
- Process JV Overview app
- AbsPL Analysis resizable plot utility
- DesignOfExperiments gui components (3)
- error handler
- JV-Analysis diagnostic helper
- JV-Analysis font size ui
- MPPT Analysis font size ui
- UVVis Analyzer font size ui
- UVVis Analyzer gui components
- DesignOfExperiments utils
- Peak Explorer pl data loader
- Process JV Overview app (2)
- Process JV Overview app (3)
- XRD PF gui layouts (3)
- NOMAD DATA ACCESS PROMPT
- conftest
- process handling
- DesignOfExperiments sampling algorithms
- EQE Analysis gui components (2)
- JV-Analysis gui components (2)
- JV-Analysis gui components (3)
- JV-Analysis plot manager
- Process JV Overview plot manager
- UVVis Analyzer data manager
- UVVis Analyzer diagnostic helper
- DEPLOYMENT
- XRD PF utils
- test api connectivity
- DesignOfExperiments utils (2)
- Excel creator guide
- JV-Analysis app (2)
- JV-Analysis manual
- JV-Analysis resizable plot utility
- UVVis Analyzer gui components (2)
- XRD PF plot manager (2)
- test config
- EQE Analysis app
- EQE Analysis font size ui
- MPPT Analysis mppt manual
- JV-Analysis pptx generator
- Process JV Overview app (4)
- Process JV Overview app (5)
- Process JV Overview resizable plot utility
- UVVis Analyzer common widgets (2)
- DesignOfExperiments sampling algorithms (2)
- EQE Analysis resizable plot utility
- JV-Analysis app (5)
- JV-Analysis gui components (4)
- Peak Explorer pl visualization
- XRD PF gui layouts (5)
- AbsPL Analysis sweep vs PL
- JV-Analysis app (7)
- JV-Analysis data manager (2)
- JV-Analysis gui components (5)
- JV-Analysis resizable plot utility (2)
- Process JV Overview app (6)
- XRD PF fitting engine (3)
- EQE Analysis batch selection
- EQE Analysis gui components (3)
- JV-Analysis gui components (6)
- Process JV Overview app (7)
- DesignOfExperiments gui components (6)
- DesignOfExperiments utils (3)
- process handling (2)
- AbsPL Analysis data manager (2)
- JV-Analysis app (8)
- JV-Analysis gui components (7)
- Perovskite calculator ChemicalSolutionCalculator
- Process JV Overview app (8)
- UVVis Analyzer gui components (3)
- conftest (2)
- conftest (3)
- JV-Analysis plot manager (7)
- Process JV Overview plot manager (7)
- XRD PF data manager (2)
- conftest (4)
- conftest (5)
- conftest (6)
- conftest (7)
- conftest (8)
- conftest (9)
- conftest (10)
- conftest (11)
- conftest (12)
- conftest (13)
- conftest (14)
- git-pull-safe
- setup git safety

## God Nodes (most connected - your core abstractions)
1. `JVAnalysisApp` - 45 edges
2. `Variable` - 44 edges
3. `PLAnalysisApp` - 41 edges
4. `GUIComponents` - 36 edges
5. `PlotManager` - 33 edges
6. `PlotManager` - 33 edges
7. `PlotUI` - 30 edges
8. `CLAUDE.md Codebase Conventions` - 30 edges
9. `AbsPLPlotManager` - 29 edges
10. `EQEAnalysisApp` - 29 edges

## Surprising Connections (you probably didn't know these)
- `What's New in JV Analysis (August 2025)` --semantically_similar_to--> `GitHub Releases as What's New`  [INFERRED] [semantically similar]
  apps/JV-Analysis/whats_new.html → CONTRIBUTING.md
- `display() in Widget Callback Needs Output() Under Voila` --references--> `setup_app()`  [EXTRACTED]
  CLAUDE.md → apps/App_dashboard/app.py
- `Pre-Shipping Gates G1-G12` --semantically_similar_to--> `CI Workflow (GitHub Actions)`  [INFERRED] [semantically similar]
  UNIFICATION_PROMPT.md → .github/workflows/ci.yml
- `Root Aggregated requirements.txt` --semantically_similar_to--> `Wetting Envelope requirements.txt (legacy)`  [INFERRED] [semantically similar]
  requirements.txt → apps/Wetting_envelope/requirements.txt
- `AbsPLAppController` --uses--> `AuthenticationManager`  [INFERRED]
  apps/AbsPL_Analysis/app.py → shared/perotf_utils/auth_manager.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Bootstrap Deployment Pipeline (cell 0 to env, proxy, install, banner suppression)** — claude_bootstrap_cell, deployment_oasis_local_config, deployment_bootstrap_ordering, deployment_dependency_install_order, deployment_import_banner_suppression [EXTRACTED 1.00]
- **Issue to PR to Version Bump to Release Change Flow** — github_issue_template_bug_report, github_issue_template_feature_request, contributing_issue_first_workflow, github_pull_request_template, contributing_semver_version_bump, contributing_github_releases [EXTRACTED 1.00]
- **Per-App User Manuals and Guides** — apps_jv_analysis_manual, apps_mppt_analysis_mppt_manual, apps_sem_crystal_counter_manual_for_values, apps_excel_creator_guide, apps_wetting_envelope_readme, apps_abspl_analysis_sweep_vs_pl [INFERRED 0.85]

## Communities (208 total, 158 thin omitted)

### Community 0 - "Hansen UNIFAC and External Imports"
Cohesion: 0.05
Nodes (5): calculate_activity_coefficients_unifac(), calculate_overall_donor_number_with_unifac(), parse_smiles_to_unifac_groups(), _flatten_multiindex_columns(), _flatten_multiindex_columns()

### Community 1 - "Data Tools File Converters"
Cohesion: 0.05
Nodes (28): extract_x_y(), get_oldest_file_date(), process_files(), process_zip_file(), rename_files(), create_download_zip(), format_eqe_output(), generate_filename() (+20 more)

### Community 2 - "Diagnostics and Resizable Plots"
Cohesion: 0.06
Nodes (9): add_diagnostic_button_to_app(), _on_click(), _on_mj_click(), diagnose_eqe_loading(), diagnose_multijunction(), create_resizable_plot(), display_resizable_plot(), ResizablePlotWidget (+1 more)

### Community 3 - "Excel Experiment Builder"
Cohesion: 0.05
Nodes (11): ExperimentExcelBuilder, add_guide_sheet(), add_experiment_sheet(), generate_steps_for_process(), make_label(), lighten_color(), add_citation_sheet(), create_experiment_app() (+3 more)

### Community 4 - "App Dashboard Catalog"
Cohesion: 0.05
Nodes (25): DiagnosticLogger, setup_app(), open_app(), open_whats_new(), render_app_card(), render_learning_card(), AppEntry, build_jupyter_url() (+17 more)

### Community 5 - "JV Export Utilities"
Cohesion: 0.04
Nodes (16): clean_filename(), create_new_results_folder(), generate_detailed_export_excel(), is_running_in_jupyter(), save_combined_excel_data(), save_full_data_frame(), clean_filename(), create_new_results_folder() (+8 more)

### Community 6 - "AbsPL GUI Components"
Cohesion: 0.06
Nodes (7): AbsPLGUIComponents, _parse_curve_bound(), remove_row(), _render_fit_curve_ranges(), _set_curve_range(), _remove(), ColorSchemeSelector

### Community 7 - "DoE Data Processing"
Cohesion: 0.05
Nodes (5): DataProcessor, ExperimentalDesignUtils, FileHandler, safe_float_conversion(), ValidationUtils

### Community 9 - "DoE Sampling Base"
Cohesion: 0.06
Nodes (5): HaltonSampling, RandomSampling, SamplingAlgorithm, SobolSampling, UniformGridSampling

### Community 13 - "Process JV Data Manager"
Cohesion: 0.05
Nodes (4): DataManager, _norm_cycle(), _norm_text(), should_include_curve()

### Community 16 - "UVVis Common Widgets"
Cohesion: 0.07
Nodes (5): ColorSchemeSelector, create_resizable_plot(), display_resizable_plot(), ResizablePlotManager, ResizablePlotWidget

### Community 19 - "Shared Auth UI"
Cohesion: 0.07
Nodes (7): AuthenticationUI, create_manual(), only_curve_name(), only_sample_name(), plot_options, sample_and_curve_name(), WidgetFactory

### Community 20 - "Shared Module Imports"
Cohesion: 0.08
Nodes (5): launch_abspl_app(), get_batch_ids(), create_batch_selection(), extract_date(), sort_by_date_desc()

### Community 22 - "Batch Loading and Fixtures"
Cohesion: 0.10
Nodes (15): _extract_xrd_arrays(), _search(), _to_1d(), _fetch_abspl(), _fetch_eqe(), _fetch_mppt(), _fetch_xrd(), main() (+7 more)

### Community 23 - "Shared NOMAD API Calls"
Cohesion: 0.13
Nodes (19): get_specific_data_of_sample(), get_token(), log_notebook_usage(), get_all_batches_wth_data(), get_all_measurements_except_JV(), get_all_uploads(), get_efficiencies(), get_entry_data() (+11 more)

### Community 24 - "Drag-and-Drop Upload Widget"
Cohesion: 0.08
Nodes (3): DragDropMultiUploadWidget, DragDropUploadWidget, update_list()

### Community 29 - "Bootstrap Installer"
Cohesion: 0.09
Nodes (9): _app_install_marker(), _apply_config_env(), _apply_proxy_env(), _build_isolation_args(), _install_app(), _install_shared(), _load_local_config(), _pip_install() (+1 more)

### Community 30 - "Dashboard Tests"
Cohesion: 0.08
Nodes (8): _entry(), _registered(), test_build_jupyter_url_never_hardcodes_an_upload_id(), test_build_voila_url_matches_expected_nomad_structure(), test_categories_cover_every_app_folder_without_repeating_a_notebook(), test_every_registered_notebook_exists_on_disk(), test_get_uploads_path_keeps_a_repo_subdirectory_inside_the_upload(), test_get_uploads_path_uses_the_leftmost_uploads_segment()

### Community 37 - "MPPT Fitting Tools"
Cohesion: 0.13
Nodes (12): calculate_ley(), erfc_linear(), erfc_params(), extrapolate(), find_T80(), find_tS(), find_Ts80(), fit_model (+4 more)

### Community 43 - "Repo Conventions Docs"
Cohesion: 0.16
Nodes (13): CLAUDE.md Codebase Conventions, graphify Knowledge Graph Usage Rules, NOMAD Plugin Packaging (Unscaffolded Goal), Apps Deliberately Not Migrated (HZB-targeted), notebook_usage.log Location Gap, CONTRIBUTING.md Change Process, Migration from Old Flat Repo (nomad-perotf-jupyter-voila-scripts), Bug Report Issue Template (+5 more)

### Community 44 - "App Package Manifests"
Cohesion: 0.10
Nodes (21): abspl-analysis, app-dashboard, data-overview-machines, data-tools, designofexperiments, diode-analyzer, eqe-analysis, excel-creator (+13 more)

### Community 51 - "UNIFICATION PROMPT"
Cohesion: 0.16
Nodes (14): app_loader Test Fixture, No App Has Passed Full Unification Checklist, Autouse No-Network Test Guard, T20 (flake8-print) Not Yet Enabled, CI Workflow (GitHub Actions), CI Test Suite Discovery Job, CI Ruff Lint Job, CI Per-Suite Test Matrix Job (+6 more)

### Community 54 - "EQE Analysis plot manager"
Cohesion: 0.17
Nodes (8): _build_legend_annotation(), _build_mj_legend_annotation(), _compute_cumulative_jsc_am15g(), _compute_group_stats(), create_eqe_figure(), _format_ann_val(), _get_am15g(), _positions_label()

### Community 57 - "test repo structure"
Cohesion: 0.22
Nodes (9): _code_cells(), _offending_lines(), _rel(), test_app_has_a_notebook(), test_app_has_pyproject_depending_on_perotf_utils(), test_no_hysprint_utils_imports(), test_notebook_code_has_no_server_literals_or_sys_path(), test_notebook_starts_with_bootstrap_cell() (+1 more)

### Community 59 - "XRD PF data manager"
Cohesion: 0.15
Nodes (3): get_axes_from_extent(), get_h5_path_from_ipython(), H5DataLoader

### Community 63 - "JV-Analysis data manager"
Cohesion: 0.13
Nodes (6): extract_px_and_cycle_info(), extract_status_from_metadata(), extract_px_and_cycle_info(), extract_status_from_metadata(), _fetch_jv(), get_all_JV()

### Community 65 - "Process JV Overview app"
Cohesion: 0.14
Nodes (3): format_date(), get_upload_name(), variation_from_identifier()

### Community 66 - "AbsPL Analysis resizable plot utility"
Cohesion: 0.15
Nodes (4): create_resizable_plot(), display_resizable_plot(), ResizablePlotManager, ResizablePlotWidget

### Community 69 - "JV-Analysis diagnostic helper"
Cohesion: 0.15
Nodes (4): add_diagnostic_button_to_app(), on_diagnose_click(), DebugLogger, diagnose_direction_values()

### Community 77 - "Process JV Overview app (2)"
Cohesion: 0.27
Nodes (3): count_samples(), format_error(), plural()

### Community 81 - "NOMAD DATA ACCESS PROMPT"
Cohesion: 0.22
Nodes (9): authenticate_with_token Uses Bare Host Bug, KIT_ Lab-ID Prefix Literal Gap, Launch and Verify Checklist (App Dashboard + /info 200), NOMAD Oasis Data Access LLM Prompt, POST entries/archive/query (metadata + archive data), POST entries/query (metadata only), lab_id vs entry_id Distinction, NOMAD Data Model (uploads, entries, archive, references) (+1 more)

### Community 82 - "conftest"
Cohesion: 0.18
Nodes (3): app_loader(), load_app_modules(), _no_network()

### Community 83 - "process handling"
Cohesion: 0.21
Nodes (6): batch_process, create_step_description(), param_selection_buttons(), flatten_layers(), make_table(), manufacturing_parameter

### Community 86 - "JV-Analysis gui components (2)"
Cohesion: 0.23
Nodes (4): clear_all_samples(), create_sample_checkbox_handler(), handler(), select_all_samples()

### Community 94 - "DEPLOYMENT"
Cohesion: 0.29
Nodes (5): Wetting Envelope requirements.txt (legacy), DEPLOYMENT.md Oasis Deployment Guide, NORTH Terminal Git Cheat Sheet, PEROTF_* Environment Variable Overrides, Root Aggregated requirements.txt

### Community 95 - "XRD PF utils"
Cohesion: 0.18
Nodes (5): debug_print(), format_timestamp(), generate_output_filename(), safe_divide(), validate_time_index()

### Community 96 - "test api connectivity"
Cohesion: 0.27
Nodes (5): _skip_if_no_credentials(), test_api_reachable(), test_get_ids_in_batch_returns_list(), test_get_sample_description_returns_dict(), test_token_authentication()

### Community 97 - "DesignOfExperiments utils (2)"
Cohesion: 0.18
Nodes (4): Constants, format_percentage(), generate_experiment_id(), truncate_string()

### Community 98 - "Excel creator guide"
Cohesion: 0.22
Nodes (11): Excel Creator Quick Guide, Example Values on First Row Toggle, Generated Workbook Sheets (Experiment Data, Guide, Citation), Excel Creator Process Configuration Controls, SEM Perovskite Grain Size Analysis Manual, Cluster Filters (Min Cluster Size, Max Border Pixels), Canny Edge Detection Parameters (threshold, sigma, histogram equalization), Kernel Size Neighborhood Grouping (+3 more)

### Community 100 - "JV-Analysis manual"
Cohesion: 0.29
Nodes (11): JV Analysis Dashboard User Manual v3.0, JV Color Schemes (30+ Palettes), Advanced Combination Plots (Status/Direction/Cell by Variable), JV Numerical Filters (PCE, FF, Voc, Jsc), Status-Based Analysis (L1/L2/D1 Filename Markers), Six-Step JV Analysis Workflow, What's New in JV Analysis (August 2025), Resizable Interactive Plots (+3 more)

### Community 101 - "JV-Analysis resizable plot utility"
Cohesion: 0.24
Nodes (4): create_resizable_plot(), display_resizable_plot(), ResizablePlotWidget, test_resizable_plot()

### Community 108 - "MPPT Analysis mppt manual"
Cohesion: 0.24
Nodes (9): JV Data and Plot Export Options, MPPT Analysis Tool User Manual, Statistical Area Plots (quartiles, std dev), Filter MPPT Batches and Load Data, MPPT Export Package (Excel, HTML/PNG, README), MPPT Curve Fit Models (linear, exp, biexp, logistic+exp, stretched exp, erf x linear), MPPT Sample Naming Conventions, Fitted Stability Parameters (t80, T80, tS) (+1 more)

### Community 110 - "JV-Analysis pptx generator"
Cohesion: 0.22
Nodes (3): _fig_to_png_bytes(), generate_jv_pptx_bytes(), _add_figure()

### Community 111 - "Process JV Overview app (4)"
Cohesion: 0.20
Nodes (3): get_batches_with_uploads(), get_upload_ids_with_entries(), parse_batch_id()

### Community 121 - "EQE Analysis resizable plot utility"
Cohesion: 0.22
Nodes (4): create_resizable_plot(), display_resizable_plot(), ResizablePlotManager, ResizablePlotWidget

### Community 123 - "JV-Analysis app (5)"
Cohesion: 0.28
Nodes (3): _norm_cycle(), _norm_text(), should_include_curve()

### Community 127 - "AbsPL Analysis sweep vs PL"
Cohesion: 0.46
Nodes (7): AbsPL Sweep vs Single PL Distinction, detect_file_type(), Archive is_sweep Check (len(results) > 1), KIT_abspl_parser.py, peroTF_AbsPLMeasurement Schema Class, Single PL File Format (_FD7.abspl.txt), Sweep File Format (_D1.abspl.txt)

### Community 131 - "JV-Analysis data manager (2)"
Cohesion: 0.32
Nodes (3): _norm_cycle(), _norm_text(), should_include_curve()

### Community 142 - "EQE Analysis batch selection"
Cohesion: 0.38
Nodes (3): create_batch_selection(), extract_date(), sort_by_date_desc()

### Community 153 - "process handling (2)"
Cohesion: 0.40
Nodes (3): merge_process(), merge_step_data(), NpEncoder

## Knowledge Gaps
- **28 isolated node(s):** `abspl-analysis`, `app-dashboard`, `data-overview-machines`, `data-tools`, `designofexperiments` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1443 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **158 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JVAnalysisApp` connect `JV Analysis App` to `JV-Analysis app (6)`, `JV-Analysis app (7)`, `error handler`, `JV-Analysis app (9)`, `JV-Analysis app (3)`, `JV Curve Analysis UI`, `Shared Module Imports`, `JV-Analysis app`, `JV-Analysis app (4)`, `JV-Analysis app (5)`, `JV-Analysis app (8)`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `JVAnalysisApp` (e.g. with `EnhancedJVCurveAnalysisUI` and `ErrorHandler`) actually correct?**
  _`JVAnalysisApp` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `abspl-analysis`, `app-dashboard`, `data-overview-machines` to the rest of the system?**
  _28 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Hansen UNIFAC and External Imports` be split into smaller, more focused modules?**
  _Cohesion score 0.051643192488262914 - nodes in this community are weakly interconnected._
- **Why does `GUIComponents` connect `DesignOfExperiments gui components (3)` to `DesignOfExperiments gui components (4)`, `DesignOfExperiments gui components (8)`, `Diagnostics and Resizable Plots`, `DesignOfExperiments gui components (5)`, `DesignOfExperiments gui components`, `DesignOfExperiments gui components (6)`, `DesignOfExperiments gui components (2)`, `DesignOfExperiments gui components (7)`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `PLAnalysisApp` (e.g. with `ResultExporter` and `FittingEngine`) actually correct?**
  _`PLAnalysisApp` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `Data Tools File Converters` be split into smaller, more focused modules?**
  _Cohesion score 0.05093167701863354 - nodes in this community are weakly interconnected._