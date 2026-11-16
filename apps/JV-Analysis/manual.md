# JV Analysis: user manual

## What the app is for

Analyse the current-voltage (JV) measurements of your solar cells stored in NOMAD:
- name the conditions you tested;
- filter out bad cells;
- compare Voc, Jsc, FF, PCE, hysteresis and the other parameters in boxplots;
- look at the JV curves;
- download the plots, summary tables, an Excel workbook and a PowerPoint slide.

The app only reads from NOMAD; it writes nothing back.

## Data it needs

The JV measurement entries in NOMAD that belong to the samples of the batches you select.
From each entry the app takes:

- **The sample**: the JV file name up to its first dot
  (`KIT_P1_20260101_1_0_3.px2Cycle_0.jv.csv` belongs to sample `KIT_P1_20260101_1_0_3`).
  From the sample name come the **batch** (the name without its last two parts,
  `KIT_P1_20260101_1`) and the **subbatch** (its second-to-last part, `0`).
- **The variation**: the sample's description in NOMAD, which the experiment Excel fills from
  its *Variation* column. A sample without one shows *No variation specified*.
- **Pixel and cycle** (optional): `px<N>` and `Cycle_<M>` in the entry's description or file
  name (`px2Cycle_0` is pixel `px2`, cycle 0). The cycle filter only appears when the data has
  cycle numbers.
- **Cell, scan direction and illumination** of every curve in the entry:
  - The cell is the first character of the curve's cell name (`A` for `A Forward`).
  - A cell name containing `[1]` is a reverse scan, `[2]` a forward scan. Otherwise a curve name
    containing "forward" or "reverse" decides, then a cell name containing "for" or "fwd"
    (forward) or "rev" or "back" (reverse). Anything else counts as reverse.
  - A cell name containing "dark" is a dark measurement, all others are light.
- **The JV parameters** NOMAD stores for each curve (see *What the numbers mean*), and the
  curve itself (voltage and current density).

## Step by step

The tabs are used from left to right; each step switches to the next tab by itself.

1. **Select Upload.**
   - *Log in.* On the Oasis this happens by itself with your NOMAD token. Elsewhere, choose
     *Username/Password* under *Auth Method*, enter them and click *Authenticate*.
     *Connection Settings* shows which Oasis the app talks to. The batch list appears after a
     successful login.
   - *Load.* Select one or several batches (*Search Batch* narrows the list) and click
     *Load Data*. *Show JV only*, under the list, keeps only the batches with JV measurements
     (this can take a moment); *Show all batches* brings the rest back.
   - The box below shows the progress: batches that were skipped and why, whether pixel and
     cycle numbers were found, and how many measurements, samples and cells were loaded.
     Loading again replaces the data.
2. **Add Variable Names.**
   - The table has one row per sample group: the samples whose names differ only in their last
     part and that share a variation. Each row is labelled with the variation. Type the
     condition each group stands for (for example "1000 rpm"); groups with the same text are
     combined in the plots.
   - *Defaults* chooses what the boxes start with: the *Variation* (preset), the *Batch name*
     (the group's name, for example `KIT_P1_20260101_1_0`) or nothing (*all*). Changing it
     rebuilds the table, so choose it before you type.
   - Click *Confirm variables*. An empty box falls back to the variation. Plots *by Variable*
     need this step; without it they are left out.
   - *Summary Statistics*, on the right, covers all loaded measurements before any filter: the
     mean PCE with its standard deviation, the best and worst sample by mean PCE, the best cell
     of every sample, the mean PCE per scan direction and the PCE quartiles.
3. **Select Filters.** The filters say which measurements to **keep**.
   - *Filter Conditions*: rows of parameter, comparison and value. `PCE(%)` `<` `40` keeps the
     measurements with a PCE below 40 %. *Add Filter* adds a row, *Remove Filter* removes the
     last one; a row without a value is ignored.
   - *Load Preset* loads the preset chosen above it. *Default* (loaded at start) is PCE < 40,
     FF < 89, FF > 24, Voc < 2.5, Voc > 0.5, Jsc < 0, Jsc > -30. *Preset 2* is FF < 15 and
     PCE >= 10.
   - *Filter by Cell Direction*: Both, Reverse or Forward.
   - *Cycle Filter* (only with cycle numbers):
     - *Best Cycle Only* (preset) keeps the cycle with the highest PCE of each sample, pixel,
       cell, scan direction and illumination;
     - *All Cycles* keeps every cycle;
     - *Specific Cycles* keeps the cycles you select in the list below it.
   - *Sample Selection* (click its title to fold it): one checkbox per sample, grouped by batch,
     with its variable and its number of cells and measurements. *Clear All* and *Select All*
     change all of them; *Selection Status* counts what is ticked per variable.
   - *Apply Filter*. The box on the right lists every step and how many measurements are left.
     The removed measurements are kept with the reason (for the Excel workbook). Then:
     - the number of colours is set to the number of variables;
     - the sample groups appear in the reorder list of *Select Plots*;
     - the plots of *Select Plots* are made right away.
4. **Select Plots.** Each row is one plot: *Plot Type*, *Option 1* and *Option 2*.
   - *Add Plot Type* adds a row, *Remove Plot Type* removes the last one. *Load Preset* fills
     the rows from *Presets*:
     - *Default* (loaded at start): PCE, Voc, Jsc, FF and Hysteresis boxplots by Variable, the
       best JV curve per condition, and the 2x2 grid by Variable;
     - *Preset 2*: Voc by Cell, the JV curves of the best device, and the grid by Variable;
     - *Advanced Analysis*: PCE, Voc, Jsc and FF by Subbatch, the best JV curve per condition,
       and the grid by Subbatch.
   - *Plot Selection* makes the plots (again).
   - **Boxplot.** Option 1 is the parameter: Voc, Jsc, FF, PCE, Hysteresis, R_ser, R_shu,
     V_mpp, J_mpp, P_mpp, or *all* for a 2x2 grid of PCE, FF, Jsc and Voc. Option 2 is what to
     group by:
     - *by Variable*: the names from *Add Variable Names*;
     - *by Batch*, *by Subbatch* and *by Sample*: taken from the sample name (see *Data it
       needs*). *by Subbatch* puts the same subbatch number of different batches into one box;
     - *by Cell*: the cell letter, over all samples;
     - *by Scan Direction*: reverse and forward.
   - *Separate Forward/Reverse in Boxplots* (on by default) draws the reverse `[R]` and forward
     `[F]` scans of every group as two boxes side by side, the reverse one darker. It does not
     apply to *by Scan Direction* or to Hysteresis.
   - **JV Curve.**
     - *Best device per condition*: for every variable, the one measurement with the highest PCE
       (forward or reverse, whichever is higher), in the colour of its boxes.
     - *Best device only*: all curves of the cell with the highest PCE.
   - **Reorder Variables for Boxplots** (appears after *Apply Filter*): drag the ≡ handle to
     change the order in which the sample groups appear in the plots; untick ✓ to leave a group
     out of all plots. Changes apply when you click *Plot Selection*.
   - **Color Scheme Selection**: the palette, *# Colors* and *Sampling*. The preview shows the
     colours used, one per group in the order of the plot; with more groups than colours they
     start again from the first.
   - **Plot Font Sizes**: *Axis Labels*, *Title*, *Legend* and *JV Line Width*, and *Reset to
     Default*. Like the colours, they apply to the next *Plot Selection*.
   - **The plots** appear under *Generated Plots*, each with a title; under a boxplot's title
     stands how many filtered measurements and groups there are:
     - drag the bottom-right corner to resize a plot, and the legend to move it;
     - hover over a point to see the values of that measurement;
     - the two camera icons in the toolbar above a plot save it as *SVG* or as
       *PNG (~600dpi)*, at the size shown.
5. **JV Curve Analysis.** A closer look at the JV curves with filters of its own. It starts from
   all loaded measurements: the filters of *Select Filters* do not apply here.
   - *Plot Settings*:
     - *Plot mode*: *Best device per condition* (the measurement with the highest PCE of each
       variable) or *All JV curves* (every curve that passes this tab's filters);
     - *Current axis*: linear or logarithmic (see *Known limits*);
     - *Color scheme*: one colour per variable;
     - *Plot style*: lines, points, or both.
   - *Condition Filter*: the variables to leave out.
   - *Numeric Filters*: rows as in *Select Filters* (✕ deletes a row), with V_mpp, J_mpp, P_mpp,
     R_series and R_shunt as well. Rows without a valid number are ignored.
   - *Sample-Specific Pixel / Cycle Selection*: choose a sample, then the pixels, cycles and
     scan directions to keep for it (an empty list keeps all). The choice is remembered per
     sample; *Copy to all samples* gives every sample the current choice.
   - *Legend Configuration*: what each curve's legend entry shows (batch name, condition,
     sample, pixel, cycle, scan direction, PCE). Here *Sample* is the last part of the sample
     name and the batch the part before it. The legend is shown as a table below the plot.
   - *Apply plot filter* (on by default) removes stray points at the ends of a curve: an end
     point at 0 V and 0 mA/cm², or one more than 0.5 V away from its neighbour. The JV curves
     of *Select Plots* are always cleaned this way.
   - *Plot JV Curves*. The box above the plot sums up how many measurements the filters kept.
6. **Download.**
   - *Create Download ZIP* (once plots exist) prepares the export; then click
     *Start ZIP Export* below it. It captures every plot on the page as it is shown now (size,
     moved legend) and saves `JV_Download_<date>_<time>.zip` with:
     - `svg/` and `png/`: every plot as SVG and as PNG;
     - `table/jv_variation_summary.csv`, `.png` and `.pdf`: one row per variable, from the
       filtered data. Each row has the number of measurements, the best PCE and the median
       PCE, each with its sample, pixel and scan direction;
     - `table/jv_detailed_pixel_data.xlsx`: the detailed workbook (see below);
     - `table/export_warnings.txt`: only when some plots could not be exported.
   - *Download Summary PPTX* (once plots exist) saves `JV_Summary_<date>_<time>.pptx`, one 16:9
     slide with:
     - the best JV curve per condition (left) and the 2x2 boxplot grid (right). Both are taken
       from the page; when they are not among your plots, the app draws them itself, and if that
       fails the place stays empty;
     - a table V_OC / J_SC / FF / PCE by *Baseline* and *Current batch* to fill in, a
       *Speculations:* field and the batch IDs;
     - "Process name" and "Stack: ..." as placeholders to overwrite.
   - *Theresa Style Download* (after *Apply Filter*) saves `Theresa_JV_<date>_<time>.zip`.
     It holds one HTML plot per sample, pixel and cycle, from the light measurements of all
     loaded data:
     - the reverse (blue dots) and forward (red crosses) curve with the highest PCE;
     - a table of PCE, FF, Jsc and Voc of both, and their hysteresis.

     Each file is named `<sample>_<pixel>_<cycle>.html`, with `_filtered` added when the
     filters removed a measurement of it.

   The detailed workbook `jv_detailed_pixel_data.xlsx` lists the variations in the order of the
   reorder list. Its sheets:
   - *Rohdaten*: every measurement with all parameters, *Included* or *Excluded*, the filter
     reason, and *Champion*/*Median* marks per variation;
   - *Zusammenfassung*: per variation the number of measurements (total, included, excluded)
     and, for PCE, FF, Jsc and Voc: N, mean, median, standard deviation, SEM, minimum, maximum,
     quartiles, IQR, whiskers and CV;
   - *Boxplot_RawData*: the included values, one column per variation and parameter, ready to
     paste into Origin;
   - *Boxplot_IndexedData*: one row per included measurement with variation, scan direction,
     PCE, FF, Jsc and Voc, for Origin's grouped box charts;
   - *Filter-Log*: every excluded measurement with its reason;
   - *Filter-Gruende*: how many measurements each reason removed.

Below the app, *Data Diagnostics* has the button *Diagnose Directions*. After loading, it lists
how many reverse and forward scans were found, with examples, so you can check the scan
direction of your files.

## What the numbers mean

- **Voc** (V), **FF** (%, the fill factor times 100), **PCE** (%), **V_mpp** (V), **R_ser** and
  **R_shu** (Ohm cm²): as stored in NOMAD.
- **Jsc** and **J_mpp** (mA/cm²) have the opposite sign of the values in NOMAD, so they are
  negative in the filters and tables (hence the default filter Jsc < 0). Boxplots, the Origin
  sheets and the Theresa tables show Jsc as a positive number.
- **P_mpp** (mW/cm²) = V_mpp x J_mpp.
- **Hysteresis** (%) = (PCE_reverse - PCE_forward) / PCE_reverse x 100, one value per cell (and
  pixel and cycle) that has both scan directions, from the light measurements. With several
  measurements per direction the highest PCE counts. A positive value means the reverse scan
  was better. The Theresa tables give the same ratio as a fraction (0.05 instead of 5 %).
- **Boxplots**: the box spans the 25 % to 75 % quartiles, the solid line in it is the median and
  the dashed line the mean; every measurement is shown as a dot.
- **Best cycle**: the cycle with the highest PCE.
- **Median in the variation summary**: the measurement whose PCE is closest to the median PCE
  (the higher one on a tie).
- **Workbook statistics** use the included measurements only:
  - SEM = standard deviation / sqrt(N);
  - IQR = Q3 - Q1;
  - *Whisker Low* and *Whisker High* = Q1 - 1.5 IQR and Q3 + 1.5 IQR, limited to the smallest
    and largest value;
  - CV = standard deviation / mean x 100;
  - *Champion* marks the measurement with the highest value of the parameter in its variation,
    *Median* the one closest to the median. Jsc is negative there, so its champion is the
    measurement with the smallest |Jsc|.

## Known limits

- Of the *JV Curve* options in *Select Plots*, only *Best device per condition* and *Best device
  only* make a plot at the moment. *All cells*, *Only working cells*, *Rejected cells* and the
  four *Separated by ...* options produce nothing; use the *JV Curve Analysis* tab instead.
- *Current axis: Logarithmic ln(|J|)* in *JV Curve Analysis* only changes the plot title; the
  axis stays linear.
- With no sample ticked in *Sample Selection*, the selection is ignored and all samples are used.
- *Selection Status* may end with "Note: Additional conditions selected": a leftover check,
  ignore it.
- When the data has cycle numbers, *Best Cycle Only* drops the measurements without a pixel
  number.
- A JV parameter missing in NOMAD counts as 0.
- Unticking a group in the reorder list removes it from the plots only; the tables in the ZIP
  still contain it.
- Colours, font sizes and the reorder list apply on the next *Plot Selection*. Reloading the page
  starts from scratch.
- The plots, the ZIP export and the HTML files of the Theresa download load their libraries from
  the internet, so the browser needs internet access. The PowerPoint export needs the server to
  download its library once; if that fails, the app says so.
- In the CSV file, text from NOMAD that starts with `=`, `+`, `-` or `@` (and is not a number)
  gets an apostrophe in front; in the Excel workbook, text starting with `=` is stored as text.
  So a spreadsheet shows it instead of running it as a formula.

## Contact

Questions and problems: contact the maintainers of the peroTF analysis apps
([Voila-Apps-V2](https://github.com/NOMADe-Joshua/Voila-Apps-V2)) or ask a Data Steward.
