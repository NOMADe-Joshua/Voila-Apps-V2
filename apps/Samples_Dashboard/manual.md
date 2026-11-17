# Samples Dashboard: User Manual

Admin tool: how many samples each person uploaded, and when. It replaces the samples dashboard
of the old admin scripts. Nothing in this app changes NOMAD.

## Loading
On the Oasis (opened from the App Dashboard) you are signed in automatically and the samples
load right away; outside NOMAD, sign in with username and password first. **Load samples**
reads them again.

The line under the button says how many samples, uploads and NOMAD authors were found, and
whether they are **all uploads of the Oasis** or **only the uploads this account can see**.
Only the NOMAD admin account sees every upload; with any other account NOMAD refuses the full
query and the app shows what that account can see.

A sample is every entry of the peroTF sample type. It counts for the **main author of its
upload** (the person who created the upload in NOMAD), at the time the upload was created.

## Overview
- **From / To** limit the plots to uploads created in that period (both days included).
- **Group by** day, week (labelled with its Monday), month or year.
- **Stacked / Side by side**: how the authors' bars of one period are drawn.
- **Apply attribution overrides**: count the uploads for the person they are credited to (see
  below) instead of their NOMAD main author.

The first plot shows the samples per author, the second the samples per author over time.
The **Download** buttons save what is shown: the numbers as CSV, the plots as interactive HTML
files, and the list of all samples in the period (with the author each one is credited to).

## Attribution
Some uploads were made from a shared account, or by someone on behalf of a colleague. An
attribution override credits such an upload to the right person for the counting in this app.
It does not change NOMAD.

1. **Find uploads**: filter by author (NOMAD author or credited name), upload name, upload id
   and creation date. The list shows each upload's date, name, number of samples, NOMAD author
   and, after the arrow, the person it is credited to.
2. Select uploads (Ctrl or Shift for several, or **Select all shown**).
3. Enter or pick a name under **Credit to** and press **Credit selected uploads**, or press
   **Remove their overrides** to count them for their NOMAD author again.
4. **Save overrides** writes the overrides to the file; until then the changes are only in your
   browser tab, and the line above the buttons counts them. **Discard changes** loads the file
   again.

Saving refuses to overwrite the file if someone else saved it after you loaded it; then
discard, and redo your changes. The previous file is kept as a `.bak` copy.

**Download overrides (CSV)** saves the current overrides. **Import CSV** reads an overrides
file, for example the `attribution_overrides.csv` of the old admin scripts, and adds its
overrides to the current ones (an upload in the file gets the file's name); save afterwards to
keep them.

The overrides file is `sample_attribution_overrides.csv` next to the usage log of the apps, in
the folder of the apps on the Oasis. It holds upload ids and names; only admins should open it.

## Known limits
- The counts use the NOMAD main author of each upload; co-authors are not counted.
- The old dashboard's cache is gone: the app reads everything with one query each time.
