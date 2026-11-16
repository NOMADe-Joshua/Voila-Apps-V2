# EQE Analysis: user manual

## What the app is for

Look at the external quantum efficiency (EQE) measurements of your samples in NOMAD:
- plot the EQE curves of several samples in one figure, over wavelength or photon energy;
- combine repeated measurements (pixels, cycles, samples with the same name) into one line,
  either the best curve or the median or mean with its spread;
- show band gap, Jsc, J0rad, Voc rad, Urbach energy and light bias in the legend, and draw the
  band gap and the cumulative Jsc into the plot;
- download the plot and a summary table.

Single-junction and multijunction devices (tandem, triple junction) are supported. The app only
reads from NOMAD; it writes nothing back. Band gap, integrated Jsc, J0rad, Voc rad and Urbach
energy are computed by NOMAD when the EQE file is processed; the app shows them and does not
recompute them. The only thing it computes itself is the shape of the cumulative Jsc curve
(see *How the numbers are computed*).

## Data it needs

- **EQE measurement entries** of the samples in the selected batches, of both EQE entry types
  of the peroTF schema (EQE measurements and TFL GammaBox EQE measurements). The app looks for
  them in three ways and merges the results (an entry found twice is used once): entries that
  reference the sample, entries whose sample is one of the batch's samples, and EQE entries in
  the upload of the batch whose sample, entry name or file name matches a sample of the batch.
- **Per curve**: the photon energy, wavelength and EQE arrays as NOMAD stores them, and the
  values stored with the curve: band gap, integrated Jsc, integrated J0rad, Voc rad, Urbach
  energy, light bias and, for multijunction devices, the sub-cell position (*top*, *mid* or
  *bottom*). Values NOMAD has not recorded stay empty. An entry with several measurements gives
  one curve per measurement; a measurement without curve data is left out.
- **Pixel and cycle numbers** are read from the entry name or the file name: `px3` (or `px 3`)
  is pixel 3; `cycle2`, `cycle_2` or `Cycle 2` is cycle 2 (upper or lower case). A curve whose
  name holds neither has no pixel or cycle number.
- **Sample descriptions**: a sample's description in NOMAD is the default name of its curves.

## Step by step

1. **Log in.** On the Oasis (NORTH) the app logs you in with your NOMAD session: the
   *Connection Settings* panel at the top shows "Authenticated as ..." and folds itself away.
   Outside NORTH, enter your NOMAD user name and password in that panel and press
   *Authenticate*. The *Connection Settings* button opens and closes the panel.
2. **Select Upload** (tab).
   - Type in *Search Batch* to narrow the list, select one or more batches (Ctrl- or
     Shift-click) and press *Load Data*.
   - *Show EQE only*, under the batch list, keeps only the batches with EQE measurements (this
     can take a moment); *Show all batches* brings the rest back.
   - The box below the list shows a one-line summary of what was found (samples, samples with
     EQE, entries, measurements, parsed and dropped). When nothing usable was found, a
     diagnostic report follows. When loading worked, the app moves on to the next tab.
   - *Data Diagnostics* (at the bottom of the tab): *Run EQE Diagnostics* lists what each of
     the three lookups found, the structure of the first entries and why measurements were
     dropped. *Multijunction Diagnostics* shows how the top, mid and bottom sub-cells were
     recognised and grouped. Use them when curves are missing, and send their output along
     when you ask for help.
3. **Add Variable Names** (tab). One row per sample with EQE curves: the sample ID, an
   *Include* checkbox and the *Name in plot*.
   - The name starts as the sample's description in NOMAD, or the sample ID when it has none.
     An empty name falls back to the sample ID.
   - **Samples with the same name are one group in the plot.** Give the samples of one
     variation the same name (for example `Ref` and `2% additive`).
   - Untick *Include* to leave a sample out of the plot and the table.
   - Press *Confirm Variables*: the names and ticks are taken over and the app moves on to the
     filters. After every later change press *Confirm Variables* and then *Apply Filters*
     again.
4. **Select Filters** (tab). Everything here takes effect when you press *Apply Filters*.
   - *Add Filter* adds a row: a value (*Column*: `bandgap_eqe`, `integrated_jsc`,
     `integrated_j0rad`, `voc_rad`, `urbach_energy` or `light_bias`), a comparison (`<`, `<=`,
     `==`, `>=`, `>`, `!=`) and a number. A measurement is kept only when it passes every row;
     a measurement without that value is dropped. *Remove Filter* removes the last row. A row
     with an empty or non-numeric number is ignored. A new row reads `bandgap_eqe >= 0`, which
     already drops the measurements without a band gap.
   - The numbers are compared in the unit NOMAD stores: band gap in eV, Jsc and J0rad in
     mA/cm², Voc rad in V, **Urbach energy in eV** (the legend shows meV), light bias in
     mW/cm².
   - *Cycle filter*, shown only when the loaded curves have more than one cycle number:
     - *Best EQE per sample* (default): per sample and pixel, only the measurement with the
       highest integrated Jsc is kept. For a multijunction device the app takes the cycle whose
       top cell has the highest Jsc and keeps all sub-cells of that cycle.
     - *All cycles*: every cycle is kept.
     - *Manual selection*: only the cycles selected in the *Cycles* list are kept (Ctrl-click
       for several). With none selected, all cycles are kept.
   - *WL min* and *WL max* (nm) are set to the shortest and longest wavelength in the data when
     it loads. Curve points outside this range are cut off, also when the x axis shows photon
     energy. The values in the legend and the table stay NOMAD's values for the whole curve.
   - The box below reports how many measurements and curve points remain and which filter
     removed how many. When measurements remain, the app moves on to the plot tab.
5. **Select Plots** (tab). Set the options, then press *Plot EQE Curves*; a change shows on the
   next press.
   - *Color Scheme Selection*: the palette (*Viridis*, *Plasma*, *Inferno*, *Magma*, *Plotly*,
     *D3*, *Set2*) with a preview. The plot always takes one color per group, spread over the
     palette. *Apply Filters* sets *# Colors* to the number of groups, so the preview shows the
     plot's colors; moving the slider changes only the preview.
   - *Plot Font Sizes*: the font size of the axis labels and the legend, and the line widths
     of the EQE curves, the band gap lines and the Jsc curves. *Reset to Default* restores 12,
     10, 2, 1.5 and 1.5.
   - *Group curves with same name* (on by default): all curves of a group become one line in
     the *Group style* below. Unticked, every curve is drawn on its own; the curves of one
     sample share a color and one legend entry, with the values of its first curve.
   - *Group style*:
     - *Best EQE curve* (default): only the curve with the highest EQE peak of the group is
       drawn, with its own values in the legend. In a multijunction group: the sample whose
       top cell has the highest EQE peak, with all its sub-cells.
     - *Median + IQR*: the median of the group's curves, with a band from the 25th to the 75th
       percentile.
     - *Mean + Std*: the mean, with a band of plus and minus one standard deviation.
   - *Separate by pixel/cycle* (on by default) works together with the *px* and *Cycle* boxes
     in the legend row: *px* splits the groups by pixel and adds `px<N>` to the name, *Cycle*
     splits them by cycle and adds `Cycle <N>`. With *Separate by pixel/cycle* unticked, *px*
     and *Cycle* do nothing and the groups are the names only.
   - *X Axis*: *Wavelength* (nm) or *Photon energy* (eV).
   - *Werte in Legende anzeigen* (show values in the legend): *Eg* (band gap), *Jsc*, *J0rad*,
     *Vocrad*, *UE* (Urbach energy, in meV) and *LB* (light bias). *Eg* and *Jsc* are ticked by
     default. A group shows the mean over its curves (with *Best EQE curve*: the values of the
     curve shown). With *Best EQE curve*, or with grouping off, a multijunction device shows
     one value per sub-cell, in the order top, mid, bottom, and the positions after its name,
     e.g. `Ref (top, bottom)`.
   - *Eg in Plot*: a dashed vertical line at the band gap of every measurement in the plot.
     With *Best EQE curve* the lines of all curves of the group are drawn, not only the one of
     the curve shown.
   - *Jsc in Plot*: the cumulative Jsc as a dotted line of the same color on a second y axis
     on the right (mA/cm²); see below.
   - In the plot: drag its bottom-right corner to resize it and drag the legend to move it.
     Clicking a legend entry hides that group together with its Eg line and Jsc curve. The two
     camera buttons in the plot's toolbar save it as SVG or as PNG at about 600 dpi.
6. **Download** (tab).
   - *Download ZIP (SVG + PNG + Table)*, after plotting: prepares the export and shows a
     *Start ZIP Export* button. Press it to download `EQE_Download_<date>_<time>.zip`, with a
     status line and a progress bar. The ZIP holds the plot as it is on the page
     (`svg/eqe_curves.svg`, and `png/eqe_curves.png` scaled up six times) and
     the summary table as `table/eqe_summary.csv` and `table/eqe_summary.png`.
   - The summary table has one row per measurement left after the filters: *Variable Name*
     (the group), *Sample*, *Pixel*, *Cycle*, *Eg (eV)*, *Jsc (mA/cm²)*, *J0rad (mA/cm²)*,
     *Vocrad (V)*, *UE (meV)* and *LB*. For multijunction data it adds *Position* and
     *Junction Type*: *SJ*, *Tandem* or *TJ* (triple junction), per sample, pixel and cycle.
     It is built when you press *Download ZIP*, with the grouping settings of the plot tab.
   - *Download Data JSON*: downloads the filtered measurements with their curve points as
     `eqe_filtered_data.json`.

## How the numbers are computed

- **Band gap, Jsc, J0rad, Voc rad, Urbach energy** come from NOMAD, computed when the EQE file
  was processed (the integrated Jsc from the EQE and the AM1.5G sun spectrum). The legend
  rounds the band gap to 2 decimals, Jsc to 1, Voc rad to 3 and the Urbach energy (in meV) to
  1, and shows J0rad in scientific notation. The table rounds the band gap to 3 decimals, Jsc
  to 2, Voc rad to 3 and the Urbach energy (meV) to 1.
- **Cumulative Jsc** (*Jsc in Plot*): the app multiplies the EQE by the photon flux of the
  AM1.5G spectrum and integrates from short to long wavelengths (trapezoid rule), times the
  elementary charge. The spectrum is the file `AM15G.dat.txt` that comes with the app (photon
  flux per eV from 0.31 to 4.43 eV, i.e. 280 to 4000 nm, converted to per nm); EQE outside it
  counts as zero. The running integral is then scaled so that it ends exactly at NOMAD's
  integrated Jsc of the curve. So the shape (which wavelengths contribute how much current)
  comes from the app, the end value from NOMAD. For *Median + IQR* and *Mean + Std* the app
  computes one such curve per measurement of the group, each ending at the group's mean Jsc,
  and draws their mean. Points cut off with *WL min* or *WL max* are not part of the integral.
- **Band gap line**: at Eg on the photon energy axis, at 1239.8 / Eg nm on the wavelength axis.
- **Median and mean**: the group's curves are interpolated to 500 common points over the range
  that all of them cover (the overlap of their x ranges); a group whose curves do not overlap
  is left out of the plot.
- **"Best" means two different things**: the cycle filter *Best EQE per sample* keeps the
  measurement with the highest integrated Jsc, the group style *Best EQE curve* draws the curve
  with the highest EQE peak.

## Known limits

- With *Median + IQR* or *Mean + Std*, the sub-cells of a multijunction device in one group are
  averaged into one line and one set of legend values. For tandem and triple-junction devices
  use *Best EQE curve*, or untick *Group curves with same name*.
- The shaded band of *Median + IQR* and *Mean + Std* is light blue for every group, whatever
  the color of the group's line.
- If no sample is ticked under *Include*, the filter keeps all samples.
- The summary table lists every measurement left after the filters, also those not drawn with
  *Best EQE curve*.
- The ZIP export loads a helper script (JSZip) from the internet; without internet access in
  the browser it fails with "Could not load JSZip".
- Pixel and cycle numbers come only from the entry or file name (see *Data it needs*).
- Text from NOMAD that starts with `=`, `+`, `-` or `@` (and is not a number) gets an apostrophe
  in front in the CSV file, so a spreadsheet shows it as text instead of running it as a
  formula.

## Contact

Questions and problems: contact the maintainers of the peroTF analysis apps
([Voila-Apps-V2](https://github.com/NOMADe-Joshua/Voila-Apps-V2)) or ask a Data Steward.
