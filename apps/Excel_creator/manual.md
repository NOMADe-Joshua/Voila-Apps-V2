# Excel Creator: user manual

## What the app is for

Build the Excel file in which you describe the fabrication sequence of a batch of samples
(substrate cleaning, coatings, evaporation, and so on). You upload the finished file into a
NOMAD upload; the peroTF experiment parser turns every row into a sample and every process
column group into process steps. The app builds the empty sheet with the right columns; you
fill in the values in Excel. It only contacts NOMAD when you open *Optional: prefill from
NOMAD* (see below).

## Step by step

1. **Pick a template.** Choose one in the *Template* list and press *Apply*, or keep the start
   sequence, which holds only *Experiment Info*. Templates are stored in
   `templates/process_templates.json`. A template that cannot be applied (no name, no process
   sequence, or a process the app does not offer) is left out of the list and the reason is
   shown under *Status*; settings a process does not have are dropped with a note there.
2. **Adjust the process sequence.** Each row is one process step, in the order of the sheet.
   - The dropdown changes the process type (the first row, *Experiment Info*, is fixed).
     Changing the type resets that row's settings to the defaults of the new type.
   - The number boxes set how many columns of a kind the step gets: *Solvents*, *Solutes*,
     *Steps* (spin steps) of a coating, *Materials* of a co-evaporation, sequential evaporation
     or close space sublimation, *Pulses* of an inkjet waveform (1 to 3).
   - *Type* of an Inkjet Printing step picks the printer (*Pixdro* or *Notion*); the two have
     different waveform columns.
   - The checkboxes switch optional blocks on: *Antisolvent*, *Gas Quenching* and *Vacuum
     Quenching* of a coating, *Milling* of a close space sublimation.
   - The green **+** inserts a new step (a *Generic Process*) below the row; the red **-**
     removes it.
   - If one batch uses different methods for the same layer (for example spin coating and slot
     die coating), add each method as its own step.
3. **Press *Generate Excel*.** The download of `experiment_<date>_<time>.xlsx` starts right
   away. If the file cannot be built, the reason is shown under *Status* and no file is
   offered.

Process types you can choose: Experiment Info, Spin Coating, Evaporation, Co-Evaporation,
Seq-Evaporation, Sputtering, ALD, Cleaning O2-Plasma, Cleaning UV-Ozone, Inkjet Printing, Slot
Die Coating, Dip Coating, Close Space Sublimation, Lamination, Annealing, Generic Process,
Multijunction Info.

## The file you get

Three sheets:

- **Experiment Data**: row 1 names the steps (`<n>: <Process>`), row 2 holds the column names,
  and the data rows start at row 3. Row 3 is an example row: it shows what each column expects.
  Delete it (or overwrite it with your first sample) before uploading the file, otherwise NOMAD
  turns it into a sample. The *Nomad ID* column is a formula for rows 3 to 500: it joins
  *Project_Name*, *Date*, *Batch*, *Subbatch* and *Sample* as
  `KIT_<Project_Name>_<Date>_<Batch>_<Subbatch>_<Sample>` and stays empty while *Project_Name*
  of that row is empty, so the parser skips the row.
- **Data Entry Guide**: a table per process type (field, description, format, unit, example).
- **How to Cite**: how to cite NOMAD and the code of the apps.

Do not add, rename or move columns: the upload only reads the columns the app created.

## Inventory IDs of the substances

Every column that names a substance is followed by a column for the ID the substance has in
the inventory system:

| Column with the substance | Column with its ID |
|---|---|
| *Solvent n name*, *Solute n type* (coatings) | *Solvent n chemical ID*, *Solute n chemical ID* |
| *Anti solvent name* (spin coating) | *Anti solvent chemical ID* |
| *Solvent n* (cleaning) | *Solvent n chemical ID* |
| *Material name* (evaporation, sputtering) | *Material chemical ID* |
| *Material name n* (co- and sequential evaporation) | *Material chemical ID n* |
| *Source material name n* (close space sublimation) | *Source material chemical ID n* |
| *Precursor 1*, *Precursor 2 (Oxidizer/Reducer)* (ALD) | *Precursor 1 chemical ID*, *Precursor 2 chemical ID* |

The ID is optional: leave the cell empty when the substance has none. NOMAD stores it with the
substance in the process step (field `chemical_id`), where it can be read over the NOMAD API.
The ID columns are formatted as text, so an ID such as `000123` keeps its leading zeros. When
you paste IDs from another file, paste them as values only, otherwise Excel takes over the
format of the source cells. Gases (sputter, quenching, plasma and carrier gas) and the
substrate have no ID column.

## Prefill from NOMAD (optional)

If the samples of the batch already exist in NOMAD (for example from an earlier Excel of the
same batch), the sheet can start with them. Press *Optional: prefill from NOMAD* under
*Generate Excel*: a panel opens and lists your 100 newest NOMAD uploads. Pick the upload of the
batch; the panel says how many samples it found and which columns NOMAD has values for.
*Generate Excel* then writes one sample per row from row 3 on, sorted by name, and leaves the
example row out:

- its NOMAD lab_id into *Nomad ID* (instead of the formula),
- *Project_Name*, *Date*, *Batch*, *Subbatch* and *Sample*, read back from a lab_id that has
  the form the formula makes (`KIT_<Project_Name>_<Date>_<Batch>_<Subbatch>_<Sample>`); for any
  other lab_id these stay empty,
- everything NOMAD knows of the sample and its substrate: *Variation*, *Sample dimension*,
  *Sample area*, *Number of pixels*, *Pixel area*, *Number of junctions*, *Substrate material*,
  *Substrate conductive layer* (the first one listed), *Bottom Cell Name* and *Notes*. A column
  NOMAD has no value for stays empty.

All process columns (solvents, solutes, ...) stay for you to fill in: those belong to process
entries, not to the sample.

Press the button again to close the panel: a closed panel means no prefill, and the next file
has its example row again. The app uses the NOMAD login of your session; if it cannot reach
NOMAD, the panel shows why and the Excel file can still be generated without prefill.

### Uploading the prefilled file

Upload the generated file into **the same upload** the samples come from. NOMAD links the
processes to the samples of the upload the file is in; in another upload they would point to
samples that do not exist there. The upload must not be published yet.

NOMAD never replaces an entry that already exists in the upload: samples and process steps
recorded by an earlier Excel are kept as they are, and new values for them in this file are
ignored. Process steps that are new are added. Measurements find their samples by name and need
no new Excel.

## Fixing a mistake after the upload

Because a second Excel never changes existing entries, correct mistakes in NOMAD itself:

- **One value or one entry: in the NOMAD GUI.** Open the entry (the process step or the sample)
  in NOMAD, change the field in the entry's form and save. This also adds a value that was left
  empty.
- **A whole process step is wrong** (wrong process type or wrong samples): delete that step's
  entry file in the upload in NOMAD, correct the step in the Excel and upload the file again.
  Only the deleted step is created anew; everything else is kept.

## Known limits

- The *Nomad ID* formula covers 498 data rows; for more samples copy it down.
- Column names live in `sheet_experiment.py`; the allowed processes and their settings come from
  the shared process catalog (`shared/perotf_utils/process_specs.py`). A new process type has
  to be added to both, and to the peroTF experiment parser.

## Contact

Questions and problems: contact the maintainers of the peroTF analysis apps
([Voila-Apps-V2](https://github.com/NOMADe-Joshua/Voila-Apps-V2)) or ask a Data Steward.
