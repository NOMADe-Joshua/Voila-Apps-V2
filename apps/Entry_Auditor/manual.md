# Entry Auditor: user manual

## What the app is for

Check how consistently the fields of your NOMAD entries are filled in (for example the
spelling of a material, solvent or tool name, or a concentration, across all the samples of a
batch), and correct a wrong value in all entries at once instead of editing every entry by hand.

**Corrections change entries in NOMAD.** Read the section on corrections before you use them.

## Data it needs

The batches you select. For their samples the app reads the batch, sample and substrate entries
and every process step that refers to the samples (spin coating, evaporation, annealing,
cleaning, ... including the device-specific ones such as *CR_SpinBox_SpinCoating*); each entry
type found gets its own block. Measurements (JV, EQE, MPP tracking, SEM, ...) are not audited:
their values come from the measured files. Text and number fields are audited (a number is
shown as text, for example a concentration of 1.42); yes/no flags are not; identifiers and
NOMAD's own schema references are left out.

## Tab *Audit*

1. **Select batches.** Select one or several batches (Ctrl- or Cmd-click for more than one) and
   click *Load Data*. A progress bar shows the entry types being read; the status line then says
   how many samples were found in how many entry types. *Load demo data* uses a small bundled
   data set (without NOMAD, so no corrections are possible). The fold-out *Debug log* lists the
   counts per entry type.
2. **Audit Results.** Each entry type with data gets a block with the number of entries, the
   number of unique samples and the number of auditable fields. *Show table* / *Hide table*, or
   *Expand all* and *Collapse all* for every block at once.
3. **The table.** One row per field, one column per entry, ordered by sample and then by file
   name. A field whose value **differs between entries** is shown in red on a red background and
   listed first, because that is usually what you look for ("this value is spelled differently
   here"). Fields with the same value everywhere are shown in black. Empty values are shown as
   `-`. *Add NOMAD links* turns each value into a link to the sample in NOMAD.
4. **Correct values** (below the table, see next section).

## Corrections

The corrections form works on one field of one entry type:

1. Choose the *Field* (clicking a field name in the table selects it), then in *Change name* the
   wrong value (the list shows the values that occur in the data), in *Sample* either all
   entries with that value or one specific entry, and type the correct value under *To*.
2. Click *Preview correction*. Nothing is changed yet. The app checks every affected entry and
   lists which ones **will change**, which are skipped because the value is not at this path
   (they are left alone) and which have errors (for example a published upload).
3. Check the list, then *Confirm: change N* (or *Cancel*). For every entry the app then:
   - stores the entry's original file as a backup **in the entry's own upload** (see below).
     If the backup cannot be stored, the entry is not changed;
   - changes only the one field you chose, in the entry's own file, and puts the file back
     into its own folder of the upload;
   - lets NOMAD refuse the change if somebody changed the entry after the app read it. The
     entry is then left as it is and reported as failed: load the batch again and repeat;
   - waits for NOMAD to process the file and reads both the file and the processed entry back.
     Only when both hold the new value does the entry count as *updated and verified*.

   The result lists every entry with what happened to it, and gives how many were updated and
   verified, skipped, failed and (if NOMAD was still processing) written but not confirmed.
   Check unconfirmed ones in NOMAD before correcting again.
4. The table is updated with the new values of the entries that were confirmed.

**Backups and the correction log** are stored in the folder `entry_auditor_backups/` of the
entry's own upload, so exactly the people who can see the entry can see them:
- `entry_auditor_backups/<folder of the file>/.<file name>.<time>.bak`: the original file,
  so a wrong correction can be put back by hand (download it in NOMAD, remove the leading dot
  and the time and `.bak` from the name, and upload it into the entry's folder again);
- `entry_auditor_backups/.<time>_corrections.log`: who changed which field from what to what,
  in which entries, with each backup and result.

Their names start with a dot on purpose: NOMAD never reads such a file as an entry.

**What is never changed:**
- entries in **published** uploads (NOMAD does not allow it);
- the identifying fields `lab_id`, the position in the experimental plan and time stamps
  (`datetime`, start and end times): they link and order the entries, and are not offered;
- entries whose file is not a NOMAD archive file (`*.archive.json` or `*.archive.yaml`),
  because NOMAD derives their values while parsing;
- entries you have no write access to (they are reported as errors).

## Tab *Corrections*

Lists the corrections stored in the uploads of the batches loaded in the *Audit* tab (the wrong
value, the value it was corrected to, the field, who made it and when), read from the
correction logs of those uploads. *Refresh* reads them again and *Export CSV* downloads
`corrections.csv` straight away.

## Known limits

- A correction changes the entry in NOMAD, not the experiment Excel it was created from. The
  experiment parser never overwrites an existing entry, so a normal reprocessing keeps the
  correction; the admin app *Reprocess Uploads*, which deletes the process entries and lets the
  parser write them again from the Excel, brings the old value back. Correct the Excel too when
  that matters.
- Text from NOMAD that starts with `=`, `+`, `-` or `@` (and is not a number) gets an apostrophe in
  front in the CSV files, so a spreadsheet shows it as text instead of running it as a formula.
- Text and number fields are audited, and a correction replaces whole values (it does not search
  inside longer texts). A number field only accepts a number as its corrected value and is
  written back as a number. A field with more than 50 different values is not listed. A field
  that only some entries have (for example the fourth solute) is listed too; the other entries
  count as empty. Stored plots (`figures`) and a sample's JV history (`jv_history_...`) are not
  listed: NOMAD recomputes them from the JV measurements, so a correction there would not last.
- The demo data cannot be corrected.

## Contact

Questions and problems: contact the maintainers of the peroTF analysis apps
([Voila-Apps-V2](https://github.com/NOMADe-Joshua/Voila-Apps-V2)) or ask a Data Steward.
