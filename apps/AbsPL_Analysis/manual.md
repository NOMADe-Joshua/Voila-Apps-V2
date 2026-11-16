# AbsPL Analysis: user manual

## What the app is for

Plot the absolute photoluminescence (AbsPL) measurements stored in NOMAD for the samples of one
or more batches:
- the PL spectra, with an optional Gaussian or Voigt fit of the peak (peak position and FWHM);
- the spectra of laser-intensity sweeps;
- the luminescence quantum yield (LuQY, also called PLQY) and the quasi-Fermi level splitting
  (QFLS) against the laser intensity, with the diode ideality factor from the slope of the QFLS.

The plots can be downloaded as SVG or PNG. The app only reads from NOMAD; it writes nothing
back.

## Data it needs

- **The AbsPL entries of the samples in the selected batches.** One entry is one measured file;
  NOMAD links it to its sample.
- **Single PL or sweep** is recognised per entry and shown as *Type*:
  - *pl*: a single PL measurement, one spectrum at one laser intensity, with the calibrated
    luminescence flux density.
  - *sweep*: one measurement made of several PL spectra while the laser power is varied. Each
    spectrum is a *sweep step* (1, 2, ...), one laser intensity each. An entry with more than one
    spectrum is a sweep, and so is an entry with a single spectrum that has raw counts but no
    flux density.
- **Per spectrum** the app reads the wavelength (nm), the luminescence flux density, the raw
  spectrum counts, the laser intensity in suns (stored per spectrum, otherwise the one value in
  the measurement settings), the luminescence quantum yield and the QFLS. A spectrum without
  wavelengths or intensities is skipped.
- **A sweep has no calibrated flux**, only raw counts. The app puts the raw counts where a plot
  asks for the flux density, so sweep spectra are in counts (see Known limits).
- **Labels used by the filters and the colours:**
  - *Cycle*: the repetition of the same measurement on a sample, read from `Cycle_N` in the
    description notes of the entry (also inside a longer word such as `px2Cycle_4`). All steps
    of one sweep share its cycle. An entry without `Cycle_N` counts as cycle 0, and the
    *Diagnostics* tab says how many there were.
  - *Spot size*: the laser spot size from the measurement settings, "Unknown" when it was not
    recorded.
  - *Condition*: the description of the sample in NOMAD, or the sample ID when it has none.
  - *Batch*: the name of the NOMAD upload the measurement is in.

## Step by step

The app has four tabs. After loading it moves on to *Select Filters*, after *Apply Filters* to
*Select Plots*.

1. **Select Upload: log in and load batches.**
   - On the Oasis the app logs in with your NOMAD session by itself. Elsewhere open *Connection
     Settings*, enter your NOMAD username and password and press *Authenticate*; the batch list
     appears after a successful login.
   - Type in *Search Batch* to narrow the list, and select one or more batches (Ctrl+click or
     Shift+click for several). *Show AbsPL only*, under the list, keeps only the batches with
     AbsPL measurements (it asks NOMAD once, which can take a moment); *Show all batches* brings
     the rest back.
   - Click *Load Data*. The box below reports *Loaded successfully*, that no AbsPL data was
     found, or the error.
2. **Select Filters: choose the measurements.**
   - Each row has four lists: *Sample*, *Type* (pl or sweep), *Spot* (laser spot size) and
     *Cycle*. Each list only offers the values that exist for the choices to its left (Sample,
     then Type, then Spot, then Cycle). *All* does not restrict.
   - A measurement is kept when it matches every list of at least one row, so rows add up: one
     row for sample A and one for sample B keep both. A row with *All* everywhere is ignored;
     without a restricting row, all loaded data is used. After loading there is one such row.
   - *Add Selection* adds a row, *Remove* deletes one, *Clear Selections* deletes all.
   - *Apply Filters* applies the rows; tick *Apply instantly* to apply every change right away.
     The number of measurements left is shown in the box on the *Select Upload* tab.
3. **Select Plots: set up and draw the plots.**
   - **Plot rows.** Every row is one plot (or one plot per sample or condition, see below).
     *Add Plot* adds a row, *Remove* deletes it, *Clear Plot Rows* deletes all. In each row
     choose the *Plot* type and its options (see "The plot types").
   - **Presets.** *Load Preset* replaces all rows: *Default* (PL (only), PL + PL (sweep ~1 sun),
     Sweep, LuQY vs Laser Intensity), *PL* (the first two) or *Sweep Analysis* (Sweep, LuQY vs
     Laser Intensity). The app starts with *Default*.
   - **Color Scheme**: the palette of all plots. The colours are spread over the whole palette,
     so a few lines still differ clearly.
   - **Trace Order (Drag & Drop)** appears after loading, with one line per sample. Drag the ≡
     handle to change the order in which the samples are drawn, listed in the legend and given
     their colours. Untick a sample to leave it out of all plots.
   - *Legend as table below* (per row) takes the legend out of the plot and lists it as a table
     under it, useful with many lines or long names.
   - **Create Plots** draws all rows below, in order. The trace order, the unticked samples and
     the colour scheme are read at this moment. A plot that fails is left out, and the
     *Diagnostics* tab says why.
4. **Use the plots.**
   - Drag the bottom-right corner to resize a plot, and drag the legend to move it. Drag a box
     to zoom; a double-click zooms out. Hovering a line or point shows its values; clicking a
     legend entry hides or shows that line.
   - The toolbar above the plot has two camera icons: *Download SVG* and *Download PNG
     (~600dpi)* (six times the resolution on screen). Both save the plot at its current size,
     named `<date>_<time>_<plot name>.svg` or `..._600dpi.png`, where the plot name is the
     heading above the plot (e.g. `abspl_plot_1` for the first row).
5. **Diagnostics.** A log of what the app did, newest first: how many measurements were loaded
   (PL and sweep, from how many samples), entries without a cycle, the result of each filter and
   plot, and errors. *Refresh Diagnostics* updates it, *Clear Diagnostics* empties it.

## The plot types

- **PL (only)**: every single PL spectrum (intensity against wavelength in nm), one line per
  measurement.
  - *Color by*: Sample, Condition, Batch or Spot size. Lines with the same value share a colour
    and a legend name.
  - *Source*: *Auto* (the flux density where there is one, otherwise the raw counts), *Flux
    density* or *Raw counts*.
  - *Peak fit*: see below.
- **PL + PL (sweep ~1 sun)**: as *PL (only)*, plus for every sample the one sweep spectrum whose
  laser intensity is closest to 1 sun (over all its sweeps). It stays empty when the data holds
  no single PL measurement.
- **Sweep**: every sweep spectrum.
  - *Mode*: *Combined* (one plot) or *Separate substrates* (one plot per condition).
  - *Color by*: Sample, Condition (the default), Batch or Spot size. *Source* is always the flux
    density, which for sweeps holds the raw counts.
  - When all lines of a plot have the same *Color by* value, each sweep step gets its own colour
    from the palette, in order of laser intensity, and the legend shows the intensity (e.g.
    `0.5 sun`). Otherwise the lines are coloured by the *Color by* value, and the intensity is
    in the hover text. *Separate substrates* with *Color by: Condition* therefore gives one plot
    per condition with the steps coloured by intensity.
  - *Peak fit*: see below.
- **LuQY vs Laser Intensity**: the luminescence quantum yield of every sweep step against its
  laser intensity (suns), as markers joined by a line in order of intensity.
  - *Mode*: *Combined (all files)* (one plot) or *Per sample* (one plot per sample).
  - *Color by*: Sample, Condition, Batch or Measurement type.
  - *X scale*: Linear or Log.
  - The hover text shows the sample, cycle, type, sweep step, intensity and value. There is no
    fit for this plot.
- **QFLS vs Laser Intensity**: the same for the QFLS (eV), with an optional fit:
  - Tick *Linear fit*; *xmin* and *xmax* (in suns, both optional) limit the points used. The fit
    is a dashed line in the colour of its data; its hover text shows slope and intercept.
  - With *X scale: Log* the fit is QFLS against the natural logarithm of the intensity, and the
    legend shows the ideality factor, e.g. `A=1.523` (see below). With a linear X scale the fit
    is a straight line in the intensity itself, without A.
- **PLQY + QFLS vs Laser Intensity**: both in one plot, the PLQY on the left axis (solid lines,
  circles) and the QFLS on the right axis (dotted lines, diamonds). The options are those of
  *QFLS vs Laser Intensity*; the fit applies to the QFLS only.

The three intensity plots use sweep measurements only; single PL measurements are not in them.

### Peak fit (PL and Sweep plots)

- Tick *Peak fit* and choose *Gaussian* or *Voigt*. Every spectrum in the plot is fitted on its
  own, with the peak model plus a constant background.
- The legend name gets the result, e.g. `S1, Peak = 771.85 nm, FWHM = 43.20 nm`; the fit is
  drawn as a dashed line and the peak as an x marker. The hover text of the fit also shows the
  fit window.
- **Fit window.** By default it is centred on the highest point of the spectrum and reaches
  about one peak width (the full width at half maximum) to either side, at least 6 data points.
  For a single curve you can set it yourself: choose the curve in *Curve* (listed by type,
  sample, cycle, sweep step and laser intensity, e.g. `sweep | S1 | C2 | step 3 | 0.5 sun`),
  enter *xmin* and *xmax* in nm and press *Set range*. The ranges set are listed below the row; empty both fields and press *Set range* again
  to remove one. With *All curves* chosen, *Set range* does nothing.
- A fit that does not converge, or a window with fewer than 5 points, leaves the curve without
  a fit and without values in the legend.

## What the numbers mean

- **LuQY (PLQY) and QFLS** are the values NOMAD stores for each spectrum, computed when the
  measurement file was processed. The app plots them as they are and does not recompute them
  from the spectra.
- **Laser intensity** is in suns, one value per spectrum (per sweep step for a sweep).
- **Peak position**: the centre of the fitted peak in nm, not simply the highest data point.
  **FWHM**: the full width at half maximum of the fitted peak in nm. Gaussian: FWHM = 2.3548 σ.
  Voigt: the usual approximation FWHM ≈ 0.5346·fL + √(0.2166·fL² + fG²), with the Lorentzian
  width fL = 2γ and the Gaussian width fG = 2.3548 σ.
- **Ideality factor A** (QFLS plots with *Linear fit* and *X scale: Log*). The QFLS grows with
  the logarithm of the light intensity I: QFLS = A · kT · ln(I) + const. The app fits the slope
  of the QFLS against ln(I) and divides it by kT = 0.02569 eV (T = 298.15 K, 25 °C). As a rule
  of thumb, A close to 1 means mostly radiative recombination, and values towards 2 mean that
  trap-assisted (Shockley-Read-Hall) recombination dominates. Use *xmin*/*xmax* to fit only the
  range where the points lie on a straight line.

## Known limits

- The app has no table and no data export: read values from the hover text, and download the
  plots as SVG or PNG. The iVoc, band gap, derived Jsc and second QFLS value that NOMAD may store
  are loaded but not shown.
- Sweep spectra are raw counts: compare them with each other, not with the calibrated flux of
  single PL measurements (this also applies to *PL + PL (sweep ~1 sun)*).
- In the intensity plots, several sweeps (cycles) of one sample with the same *Color by* value
  are joined into one line, sorted by intensity. Filter to one cycle to see one sweep at a time.
- If NOMAD holds no laser intensity per sweep step, every step gets the one value from the
  measurement settings, and the intensity plots show all steps at the same intensity.
- If the filters leave no measurement, *Create Plots* uses all loaded data.
- The *Curve* list of a plot row is filled when data is loaded. Rows added, or a preset loaded,
  after loading offer only *All curves*: click *Load Data* again to fill them.
- *Fit mode* (Auto/Manual) has no effect at the moment: the fit window is the automatic one
  unless a range is set for the curve.
- The colour scheme *Default (old)* is drawn with Viridis.
- The drag & drop order sets the order of the intensity plots only when they are coloured by
  sample.
- The left axis of *PLQY + QFLS vs Laser Intensity* is labelled "PLQY (%)", but the values are
  plotted as stored in NOMAD, without conversion.
- The ideality factor assumes 25 °C, whatever the temperature of the measurement.

## Contact

Questions and problems: contact the maintainers of the peroTF analysis apps
([Voila-Apps-V2](https://github.com/NOMADe-Joshua/Voila-Apps-V2)) or ask a Data Steward.
