# Process & JV Overview: User Manual

Shows, per batch, how the samples were made (the process steps stored in NOMAD) next to how
they performed (JV boxplots by variation).

## 1. Sign in
In NORTH the app signs you in with your NOMAD token. Run locally, open "Connection Settings"
and enter your NOMAD username and password.

## 2. Select batches
Only batches with JV measurements are listed. Batch names follow `KIT_Name_YYYYMMDD_rest`.

- **Names**: pick one or more names; none selected means all names.
- **Date from / Date to**: `YYYYMMDD`; an empty field means no limit.
- **Search**: part of a batch or upload name.
- **Reset filters** clears all of the above.
- **All matches / None** select or clear every batch the filters show.
- **Load data** loads the selected batches. A progress bar shows each step; batches appear one
  below the other as soon as they are loaded.

## 3. Read a batch
Each batch has three parts:

- **Variations**: click to see which samples belong to which variation (the variation is the
  sample description in NOMAD).
- **Process steps**: one row per step of the experiment. Click **details** to see the
  parameters of every variation of that step in a table; an empty cell means that variation has
  no value for the parameter. The buttons under the table select parameters for the overview
  of selected parameters.
- **JV boxplots by variation**: every JV parameter (PCE, Voc, Jsc, FF, ...) per variation, best
  cycle only, with the JV app's default filter. Dark boxes are reverse scans, light ones forward
  scans.

## 4. Detail table options
- **hide nonvaried values**: only parameters that differ between variations.
- **hide text values**: only numbers.
- **abbreviate value names**: short column names instead of the full path in the archive.

## Notes
- The app shows only what is stored in NOMAD. A value that is in the experiment Excel but
  missing here was not stored by the parser; the admin app "Reprocess Uploads" can let a fixed
  parser write it again.
- Values are shown in the unit NOMAD stores them in (for example pressures in mbar, even though
  the experiment Excel asks for bar).
