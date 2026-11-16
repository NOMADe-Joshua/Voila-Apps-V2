# MPPT_Analysis: traps of this app

Read `FITTING.md` before changing any fitting maths: it defines T95/T80/Ts95/Ts80, the stabilization time, and the lifetime energy yield, and says which units go to NOMAD (times in seconds, LEY in kWh/m²).
- The fit results written back to NOMAD change stored numbers; a change to a definition needs the manual and `FITTING.md` updated in the same PR.
- Power is positive inside the app (the sign is detected per entry); NOMAD stores generated power as negative.
- A fit already stored in NOMAD is shown in the results table (`stored_fit_from_archive`); the processed archive may lack `fit_method` and `fit_parameters`.
- Writing back is guarded like Entry_Auditor's corrections (`write_fit_results_to_nomad`); do not weaken or reorder: only `ENTRY_TYPE_FAMILIES["mppt"]` entries of unpublished uploads with an archive mainfile, only paths below `FIT_RESULTS_PATH`; hash read, backup into the entry's OWN upload via `perotf_utils.upload_backups` (`mppt_fit_backups/`, hidden `.bak`), no backup means no write, hash read again right before `edit_entry` (NOMAD's edit endpoint has no concurrency check), then the processed entry is read back. One log per upload and run.
- Batches come from the shared batch list with `filter_entry_type=ENTRY_TYPE_FAMILIES["mppt"]`; HZB's slow `get_mppt_batch_ids` fallback (one query per 50 samples over every batch) is deliberately gone (rule 13).
