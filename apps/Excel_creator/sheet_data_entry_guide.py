from perotf_utils.config import GUI_ENDPOINT, URL_BASE


# Method for adding a sheet with information on how to fill up the columns
def add_guide_sheet(workbook):
    guide_ws = workbook.create_sheet(title="Data Entry Guide")
    row = 1

    # 1. Introduction (multi-line text)
    intro_lines = [
        "Perovskite Solar Cell Fabrication Sequence",
        "Data Entry Guide",
        "",
        "1. Introduction",
        "This guide provides instructions for filling out the spreadsheet that tracks the fabrication sequence of perovskite solar cells, supporting automated data upload to NOMAD.",
        "• Note: This guide is a reference. For specific questions or custom spreadsheet requests, please contact a Data Steward.",
        "• Customization: Each scientist may follow different fabrication steps. Data Stewards can provide a tailored spreadsheet for your workflow.",
        "• Coverage: Most Hysprint and IRIS lab processes are included. If you need to track additional information, contact a Data Steward.",
        "• Important: Do not add columns to the spreadsheet, as they will not be parsed.",
        "",
        "Available Processes:",
        "• Cleaning: O2-Plasma, UV-Ozone",
        "• Coating: Spin Coating, Slot Die Coating, Dip Coating, Inkjet Printing",
        "• Deposition: Evaporation, Co-Evaporation, Seq-Evaporation, Close Space Sublimation, Sputtering, ALD",
        "• Processing: Annealing, Lamination, Laser Scribing",
        "• Info: Experiment Info, Multijunction Info, Generic Process",
        "",
        "Example Fabrication Sequence:",
        "• Cleaning: UV-Ozone with 1 solvent (ITO substrates)",
        "• Spin Coating: 1 solvent, 1 solute, 1 step (SAM)",
        "• Spin Coating: 2 solvents, 2 solutes, 2 steps, with antisolvent (Perovskite)",
        "• Co-Evaporation: 2 materials (C60, BCP)",
        "• Evaporation: Copper electrode",
        "",
        "2. Detailed Field Descriptions",
        "Upload Name: Choose a descriptive upload name (e.g., project name + batch).",
        "",
    ]
    for line in intro_lines:
        guide_ws.cell(row=row, column=1, value=line)
        row += 1

    # Helper to write a table
    def write_table(ws, start_row, title, table_data):
        ws.cell(row=start_row, column=1, value=title)
        start_row += 1
        headers = ["Field Name", "Description", "Data Format", "Units", "Example"]
        for col, header in enumerate(headers, 1):
            ws.cell(row=start_row, column=col, value=header)
        for r, entry in enumerate(table_data, start_row + 1):
            for c, val in enumerate(entry, 1):
                ws.cell(row=r, column=c, value=val)
        return start_row + len(table_data) + 2  # leave a blank row after table

    # Experiment Info Table
    experiment_info = [
        ["Date", "Date of experiment", "DD-MM-YYYY", "", "26-02-2025"],
        ["Project_Name", "Scientist initials/project name", "Text", "", "AnAl"],
        ["Batch", "General experiment batch number", "Number", "", "1"],
        ["Subbatch", "Subset for variations", "Number", "", "2"],
        ["Sample", "Sample serial number", "Number", "", "1"],
        ["Nomad ID", "Auto-generated sample ID", "Alphanumeric", "", "KIT_AnAl_26-02-2025_1_2_1"],
        ["Variation", "Subbatch variation", "Alphanumeric", "", "1000 rpm"],
        ["Sample Dimension", "Sample size", "Text", "", "16x16"],
        ["Sample area", "Active area (e.g., ITO overlap)", "Number", "cm²", "0.105"],
        ["Number of pixels", "Number of pixels", "Number", "", "4"],
        ["Pixel area", "Area per pixel", "Number", "cm²", "0.105"],
        ["Number of junctions", "Number of junctions", "Number", "", "1"],
        ["Substrate Material", "Substrate material", "Text", "", "Glass"],
        ["Substrate Conductive Layer", "Conductive layer material", "Text", "", "ITO"],
        ["Bottom Cell Name", "Bottom cell identifier for multijunction", "Text", "", ""],
        ["Notes", "Additional notes or methods", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Experiment Info", experiment_info)

    # Multijunction Info
    multijunction_info = [
        ["Recombination Layer", "Material for recombination layer", "Text", "", "ITO"],
        ["Notes", "Additional notes for multijunction", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Multijunction Info", multijunction_info)

    # Cleaning Processes
    cleaning_o2 = [
        ["Solvent 1", "First cleaning solvent", "Text", "", "Hellmanex"],
        ["Time 1", "Ultrasonic bath time", "Number", "s", "900"],
        ["Temperature 1", "Bath temperature", "Number", "°C", "40"],
        ["Gas-Plasma Gas", "Plasma gas type", "Text", "", "O2"],
        ["Gas-Plasma Time", "Plasma treatment duration", "Number", "s", "900"],
        ["Gas-Plasma Power", "Plasma power", "Number", "W", "100"],
    ]
    row = write_table(guide_ws, row, "Cleaning O2-Plasma", cleaning_o2)

    cleaning_uv = [
        ["Solvent 1", "First cleaning solvent", "Text", "", "Hellmanex"],
        ["Time 1", "Ultrasonic bath time", "Number", "s", "900"],
        ["Temperature 1", "Bath temperature", "Number", "°C", "40"],
        ["UV-Ozone Time", "UV-Ozone duration", "Number", "s", "900"],
    ]
    row = write_table(guide_ws, row, "Cleaning UV-Ozone", cleaning_uv)

    # Spin Coating
    spin_coating = [
        [
            "Material Name",
            "Coated material",
            "Text",
            "",
            "Cs0.05(MA0.17FA0.83)0.95Pb(I0.83Br0.17)3",
        ],
        ["Layer Type", "Type of layer", "Text", "", "Absorber"],
        ["Tool/GB name", "Tool used", "Text", "", "HZB-HySprintBox"],
        ["Solvent 1 name", "First solvent", "Text", "", "DMF"],
        ["Solvent 1 volume", "Volume of solvent 1", "Number", "µL", "10"],
        ["Solute 1 type", "First solute type", "Text", "", "PbI2"],
        ["Solute 1 Concentration", "Concentration of solute 1", "Number", "mM", "1.42"],
        ["Solution volume", "Total solution volume", "Number", "µL", "100"],
        ["Spin Delay", "Delay before spinning", "Number", "s", "0.5"],
        ["Rotation Speed", "Spin speed (single step)", "Number", "rpm", "3000"],
        ["Rotation time", "Spin time (single step)", "Number", "s", "30"],
        ["Acceleration", "Acceleration (single step)", "Number", "rpm/s", "1000"],
        ["Anti solvent name", "Antisolvent (if used)", "Text", "", "Toluene"],
        ["Anti solvent volume", "Antisolvent volume", "Number", "ml", "0.3"],
        ["Anti solvent dropping time", "When to add antisolvent", "Number", "s", "25"],
        ["Anti solvent dropping speed", "Antisolvent dropping speed", "Number", "µL/s", "50"],
        ["Anti solvent dropping heigt", "Antisolvent dropping height", "Number", "mm", "30"],
        ["Annealing Time", "Annealing duration", "Number", "min", "30"],
        ["Annealing Temperature", "Annealing temperature", "Number", "°C", "120"],
        ["Annealing athmosphere", "Annealing atmosphere", "Text", "", "Nitrogen"],
        ["Notes", "Additional notes", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Spin Coating", spin_coating)

    # Slot Die Coating
    slot_die = [
        ["Material name", "Coated material", "Text", "", "Perovskite"],
        ["Layer type", "Type of layer", "Text", "", "Absorber"],
        ["Tool/GB name", "Tool used", "Text", "", "HZB-SlotDie"],
        ["Solvent 1 name", "First solvent", "Text", "", "DMF"],
        ["Solvent 1 volume", "Volume of solvent 1", "Number", "µL", "100"],
        ["Solute 1 type", "First solute type", "Text", "", "PbI2"],
        ["Solute 1 Concentration", "Concentration of solute 1", "Number", "mM", "1.5"],
        ["Coating run", "Coating run number", "Number", "", "1"],
        ["Solution volume", "Total solution volume", "Number", "µm", "500"],
        ["Flow rate", "Coating flow rate", "Number", "µL/min", "25"],
        ["Head gap", "Head to substrate gap", "Number", "mm", "0.3"],
        ["Speed", "Coating speed", "Number", "mm/s", "15"],
        ["Air knife angle", "Air knife angle", "Number", "°", "45"],
        ["Air knife gap", "Air knife gap", "Number", "cm", "0.5"],
        ["Bead volume", "Bead volume", "Number", "mm/s", "2"],
        ["Drying speed", "Drying speed", "Number", "cm/min", "30"],
        ["Drying gas temperature", "Drying gas temperature", "Number", "°C", "25"],
        ["Heat transfer coefficient", "Heat transfer coefficient", "Number", "W m^-2 K^-1", "10"],
        ["Coated area", "Coated area", "Number", "mm²", "100"],
        ["Annealing time", "Annealing duration", "Number", "min", "30"],
        ["Annealing temperature", "Annealing temperature", "Number", "°C", "120"],
        ["Annealing athmosphere", "Annealing atmosphere", "Text", "", "Air"],
        ["Notes", "Additional notes", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Slot Die Coating", slot_die)

    # Inkjet Printing
    inkjet = [
        ["Material name", "Printed material", "Text", "", "PEDOT:PSS"],
        ["Layer type", "Type of layer", "Text", "", "Hole Transport Layer"],
        ["Tool/GB name", "Tool used", "Text", "", "HZB-Inkjet"],
        ["Solvent 1 name", "First solvent", "Text", "", "Water"],
        ["Solvent 1 volume", "Volume of solvent 1", "Number", "µL", "50"],
        ["Solute 1 type", "First solute type", "Text", "", "PEDOT:PSS"],
        ["Solute 1 Concentration", "Concentration of solute 1", "Number", "mM", "10"],
        ["Printhead name", "Printhead model", "Text", "", "Spectra 0.8µL"],
        ["Printing run", "Printing run number", "Number", "", "1"],
        ["Number of active nozzles", "Active nozzles count", "Number", "", "128"],
        ["Droplet density", "Print resolution", "Number", "dpi", "400"],
        ["Quality factor", "Print quality factor", "Number", "", "3"],
        ["Step size", "Step size", "Number", "", "10"],
        ["Printing direction", "Print direction", "Text", "", "Bidirectional"],
        ["Printed area", "Printed area", "Number", "mm²", "100"],
        ["Droplet per second", "Droplet frequency", "Number", "1/s", "5000"],
        ["Droplet volume", "Volume per droplet", "Number", "pL", "10"],
        ["Dropping Height", "Print head height", "Number", "mm", "12"],
        ["Ink reservoir pressure", "Ink pressure", "Number", "mbar", "300"],
        ["Table temperature", "Substrate temperature", "Number", "°C", "40"],
        ["Nozzle temperature", "Nozzle temperature", "Number", "°C", "35"],
        ["Room temperature", "Room temperature", "Number", "°C", "22"],
        ["rel. humidity", "Relative humidity", "Number", "%", "45"],
        ["Wf Number of Pulses", "Number of waveform pulses", "Number", "", "1"],
        ["Annealing time", "Annealing duration", "Number", "min", "15"],
        ["Annealing temperature", "Annealing temperature", "Number", "°C", "100"],
        ["Annealing athmosphere", "Annealing atmosphere", "Text", "", "Air"],
        ["Notes", "Additional notes", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Inkjet Printing", inkjet)

    # Evaporation
    evaporation = [
        ["Material Name", "Evaporated material", "Text", "", "PCBM"],
        ["Layer Type", "Type of layer", "Text", "", "Electron Transport Layer"],
        ["Tool/GB name", "Tool used", "Text", "", "Hysprint Evap"],
        ["Organic", "Is the layer organic?", "Boolean", "", "True"],
        ["Base Pressure", "Base pressure", "Number", "bar", "1e-6"],
        ["Pressure start", "Start pressure", "Number", "bar", "5e-6"],
        ["Pressure end", "End pressure", "Number", "bar", "3e-6"],
        ["Source temp. start", "Source temp. (start)", "Number", "°C", "150"],
        ["Source temp. end", "Source temp. (end)", "Number", "°C", "160"],
        ["Substrate temperature", "Substrate temp.", "Number", "°C", "25"],
        ["Thickness", "Layer thickness", "Number", "nm", "100"],
        ["Rate", "Deposition rate", "Number", "Å/s", "1.0"],
        ["Power", "Evaporation power", "Number", "%", "50"],
        ["Tooling factor", "Tooling factor", "Number", "", "1.5"],
        ["Notes", "Additional notes", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Evaporation", evaporation)

    # Co-Evaporation
    co_evap = [
        ["Material name", "Primary material", "Text", "", "C60"],
        ["Layer type", "Type of layer", "Text", "", "Electron Transport Layer"],
        ["Tool/GB name", "Tool used", "Text", "", "IRIS Evap"],
        ["Material name 1", "First co-evaporated material", "Text", "", "C60"],
        ["Base pressure 1", "Base pressure for material 1", "Number", "bar", "1e-6"],
        ["Pressure start 1", "Start pressure for material 1", "Number", "bar", "5e-6"],
        ["Pressure end 1", "End pressure for material 1", "Number", "bar", "3e-6"],
        ["Source temperature start 1", "Source temp. start (material 1)", "Number", "°C", "150"],
        ["Source temperature end 1", "Source temp. end (material 1)", "Number", "°C", "160"],
        ["Substrate temperature 1", "Substrate temp. (material 1)", "Number", "°C", "25"],
        ["Thickness 1", "Thickness of material 1", "Number", "nm", "50"],
        ["Rate 1", "Deposition rate (material 1)", "Number", "Å/s", "0.5"],
        ["Tooling factor 1", "Tooling factor (material 1)", "Number", "", "1.0"],
        ["Material name 2", "Second co-evaporated material", "Text", "", "BCP"],
        ["Base pressure 2", "Base pressure for material 2", "Number", "bar", "1e-6"],
        ["Pressure start 2", "Start pressure for material 2", "Number", "bar", "5e-6"],
        ["Pressure end 2", "End pressure for material 2", "Number", "bar", "3e-6"],
        ["Source temperature start 2", "Source temp. start (material 2)", "Number", "°C", "100"],
        ["Source temperature end 2", "Source temp. end (material 2)", "Number", "°C", "110"],
        ["Substrate temperature 2", "Substrate temp. (material 2)", "Number", "°C", "25"],
        ["Thickness 2", "Thickness of material 2", "Number", "nm", "10"],
        ["Rate 2", "Deposition rate (material 2)", "Number", "Å/s", "0.2"],
        ["Tooling factor 2", "Tooling factor (material 2)", "Number", "", "1.1"],
    ]
    row = write_table(guide_ws, row, "Co-Evaporation", co_evap)

    # Seq-Evaporation (Sequential Evaporation)
    seq_evap = [
        ["Material name", "Primary material", "Text", "", "CuI"],
        ["Layer type", "Type of layer", "Text", "", "Hole Transport Layer"],
        ["Tool/GB name", "Tool used", "Text", "", "IRIS Evap"],
        ["Material name 1", "First material (sequential)", "Text", "", "CuI"],
        ["Base pressure 1", "Base pressure for material 1", "Number", "bar", "1e-6"],
        ["Pressure start 1", "Start pressure for material 1", "Number", "bar", "5e-6"],
        ["Pressure end 1", "End pressure for material 1", "Number", "bar", "3e-6"],
        ["Source temperature start 1", "Source temp. start (material 1)", "Number", "°C", "200"],
        ["Source temperature end 1", "Source temp. end (material 1)", "Number", "°C", "210"],
        ["Substrate temperature 1", "Substrate temp. (material 1)", "Number", "°C", "25"],
        ["Thickness 1", "Thickness of material 1", "Number", "nm", "30"],
        ["Rate 1", "Deposition rate (material 1)", "Number", "Å/s", "0.3"],
        ["Tooling factor 1", "Tooling factor (material 1)", "Number", "", "1.2"],
        ["Material name 2", "Second material (sequential)", "Text", "", "CsPbI3"],
        ["Base pressure 2", "Base pressure for material 2", "Number", "bar", "1e-6"],
        ["Pressure start 2", "Start pressure for material 2", "Number", "bar", "5e-6"],
        ["Pressure end 2", "End pressure for material 2", "Number", "bar", "3e-6"],
        ["Source temperature start 2", "Source temp. start (material 2)", "Number", "°C", "300"],
        ["Source temperature end 2", "Source temp. end (material 2)", "Number", "°C", "310"],
        ["Substrate temperature 2", "Substrate temp. (material 2)", "Number", "°C", "25"],
        ["Thickness 2", "Thickness of material 2", "Number", "nm", "500"],
        ["Rate 2", "Deposition rate (material 2)", "Number", "Å/s", "1.0"],
        ["Tooling factor 2", "Tooling factor (material 2)", "Number", "", "1.0"],
        ["Notes", "Additional notes", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Seq-Evaporation (Sequential Evaporation)", seq_evap)

    # Close Space Sublimation
    css = [
        ["Material name", "Sublimed material", "Text", "", "CdTe"],
        ["Layer type", "Type of layer", "Text", "", "Absorber"],
        ["Tool/GB name", "Tool used", "Text", "", "CSS Chamber"],
        ["Organic", "Is the material organic?", "Boolean", "", "False"],
        ["Source material name 1", "First source material (optional)", "Text", "", "CdCl2"],
        ["Source material name 2", "Second source material (optional)", "Text", "", "MgCl2"],
        ["Source material name 3", "Third source material (optional)", "Text", "", ""],
        ["Source material name 4", "Fourth source material (optional)", "Text", "", ""],
        [
            "Source material ratio 1",
            "Relative ratio for material 1 (e.g., A:B = 3:1)",
            "Number",
            "",
            "3",
        ],
        [
            "Source material ratio 2",
            "Relative ratio for material 2 (e.g., A:B = 3:1)",
            "Number",
            "",
            "1",
        ],
        [
            "Source material ratio 3",
            "Relative ratio for material 3 (e.g., A:B = 3:1)",
            "Number",
            "",
            "2",
        ],
        ["Process pressure [mbar]", "Process pressure", "Number", "mbar", "40"],
        ["Source temperature [°C]", "Source temperature", "Number", "°C", "650"],
        ["Substrate temperature [°C]", "Substrate temperature", "Number", "°C", "550"],
        ["Material state", "Material physical state", "Text", "", "Powder"],
        ["Substrate source distance [mm]", "Distance substrate-source", "Number", "mm", "5"],
        ["Thickness [nm]", "Layer thickness", "Number", "nm", "2000"],
        ["Deposition Time [s]", "Deposition duration", "Number", "s", "300"],
        ["Carrier gas", "Carrier gas type", "Text", "", "Ar"],
        [
            "Milling rotation speed [rpm]",
            "Planetary mill rotation speed (optional)",
            "Number",
            "rpm",
            "350",
        ],
        [
            "Milling rotation time [min]",
            "Planetary mill rotation time (optional)",
            "Number",
            "min",
            "20",
        ],
        ["Milling rest time [min]", "Planetary mill rest time (optional)", "Number", "min", "5"],
        ["Notes", "Additional notes", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Close Space Sublimation", css)

    # ALD (Atomic Layer Deposition)
    ald = [
        ["Material Name", "Deposited material", "Text", "", "Al2O3"],
        ["Layer Type", "Type of layer", "Text", "", "Passivation Layer"],
        ["Tool/GB name", "Tool used", "Text", "", "IRIS ALD"],
        ["Source", "Precursor source", "Text", "", "TMA"],
        ["Thickness", "Film thickness", "Number", "nm", "25"],
        ["Temperature", "Deposition temperature", "Number", "°C", "150"],
        ["Rate", "Deposition rate", "Number", "Å/s", "0.1"],
        ["Time", "Deposition time", "Number", "s", "1800"],
        ["Number of cycles", "Number of ALD cycles", "Number", "", "250"],
        ["Precursor 1", "First precursor", "Text", "", "TMA"],
        ["Pulse Duration 1", "Pulse duration (precursor 1)", "Number", "s", "0.2"],
        ["Manifold temp. 1", "Manifold temp. (precursor 1)", "Number", "°C", "80"],
        ["Bottle temp. 1", "Bottle temp. (precursor 1)", "Number", "°C", "25"],
        ["Precursor 2", "Second precursor", "Text", "", "H2O"],
        ["Pulse Duration 2", "Pulse duration (precursor 2)", "Number", "s", "0.1"],
        ["Manifold temp. 2", "Manifold temp. (precursor 2)", "Number", "°C", "70"],
    ]
    row = write_table(guide_ws, row, "ALD (Atomic Layer Deposition)", ald)

    # Sputtering
    sputtering = [
        ["Material Name", "Sputtered material", "Text", "", "TiO2"],
        ["Layer Type", "Type of layer", "Text", "", "Electron Transport Layer"],
        ["Tool/GB name", "Tool used", "Text", "", "Hysprint Sputter"],
        ["Gas", "Sputtering gas", "Text", "", "Argon"],
        ["Temperature", "Deposition temperature", "Number", "°C", "200"],
        ["Pressure", "Chamber pressure", "Number", "mbar", "0.01"],
        ["Deposition Time", "Deposition time", "Number", "s", "300"],
        ["Burn in time", "Burn-in time", "Number", "s", "60"],
        ["Power", "Sputtering power", "Number", "W", "150"],
        ["Rotation rate", "Substrate rotation rate", "Number", "rpm", "30"],
        ["Thickness", "Film thickness", "Number", "nm", "50"],
        ["Gas flow rate", "Gas flow rate", "Number", "cm³/min", "20"],
        ["Notes", "Additional notes", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Sputtering", sputtering)

    # Annealing
    annealing = [
        ["Annealing time", "Annealing duration", "Number", "min", "60"],
        ["Annealing temperature", "Annealing temperature", "Number", "°C", "150"],
        ["Annealing athmosphere", "Annealing atmosphere", "Text", "", "Nitrogen"],
        ["Relative humidity", "Relative humidity during annealing", "Number", "%", "35"],
        ["Notes", "Additional notes", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Annealing", annealing)

    # Lamination
    lamination = [
        ["Interface", "Interface material", "Text", "", "EVA"],
        ["Tool/GB name", "Tool used", "Text", "", "Laminator"],
        ["Temperature during process", "Process temperature", "Number", "°C", "150"],
        ["Temperature at pressure relief", "Temperature at pressure relief", "Number", "°C", "120"],
        ["Pressure", "Applied pressure", "Number", "MPa", "0.1"],
        ["Force", "Applied force", "Number", "N", "1000"],
        ["Time lamination", "Lamination duration", "Number", "s", "300"],
        ["Heat up time", "Heat up duration", "Number", "s", "60"],
        ["Cool down time", "Cool down duration", "Number", "s", "120"],
        ["Total time", "Total process time", "Number", "s", "480"],
        ["Athmosphere in chamber", "Chamber atmosphere", "Text", "", "Air"],
        ["Humidity", "Relative humidity", "Number", "%", "50"],
        ["Stamp 1 Material", "First stamp material", "Text", "", "Steel"],
        ["Stamp 1 Thickness", "First stamp thickness", "Number", "mm", "5"],
        ["Stamp 1 Area", "First stamp area", "Number", "mm²", "100"],
        ["Stamp 2 Material", "Second stamp material", "Text", "", "Silicone"],
        ["Stamp 2 Thickness", "Second stamp thickness", "Number", "mm", "2"],
        ["Stamp 2 Area", "Second stamp area", "Number", "mm²", "100"],
        ["Homogeniously pressed", "Homogeneous pressing (1/0)", "Number", "", "1"],
        ["Sucessful adhesion", "Successful adhesion (1/0)", "Number", "", "1"],
        ["Notes", "Additional notes", "Text", "", ""],
    ]
    row = write_table(guide_ws, row, "Lamination", lamination)

    # Laser Scribing
    laser = [
        ["Laser wavelength", "Laser wavelength", "Number", "nm", "532"],
        ["Laser pulse time", "Pulse duration", "Number", "ps", "8"],
        ["Laser pulse frequency", "Pulse frequency", "Number", "kHz", "80"],
        ["Speed", "Scribing speed", "Number", "mm/s", "100"],
        ["Fluence", "Laser fluence", "Number", "J/cm²", "0.5"],
        ["Power", "Laser power", "Number", "%", "75"],
        ["Recipe file", "Recipe filename", "Text", "", "scribe_recipe.xml"],
    ]
    row = write_table(guide_ws, row, "Laser Scribing", laser)

    # 3. Data Entry Best Practices
    best_practices = [
        "",
        "3. Data Entry Best Practices",
        "• Decimal Points: Use a dot or comma as appropriate for your Excel/language settings.",
        "• Consistency: Use consistent names for materials, processes, and equipment.",
        "• Completeness: Record as many parameters as possible for each step.",
        "• Units: Always include units as specified in the field descriptions.",
        "• Boolean Values: Use True/False or 1/0 for boolean fields.",
        "",
        "4. File Naming Conventions",
        "• Standard Format: Each measurement file should be saved as Nomad_id.comment.measurement_type.file_format",
        "  Example: KIT_AnAl_26-02-2025_1_2_1.jv.txt",
        "",
        "5. Process Configuration",
        "• Spin Coating: Configure number of solvents, solutes, spin steps, and optional features (antisolvent, gas/vacuum quenching)",
        "• Co-Evaporation: Specify number of materials (typically 2-3)",
        "• Inkjet Printing: Choose between Pixdro and Notion waveform types",
        "• Cleaning: Configure number of solvents for ultrasonic cleaning steps",
        "",
    ]
    for line in best_practices:
        guide_ws.cell(row=row, column=1, value=line)
        row += 1

    # Add hyperlinks for Voila Dashboard and How-to-guide
    voila_row = row  # current row for Voila Dashboard
    guide_row = row + 1  # next row for How-to-guide

    guide_ws.cell(row=voila_row, column=1, value="• File Uploader Voila Dashboard")
    guide_ws.cell(row=voila_row, column=1).hyperlink = f"{URL_BASE}{GUI_ENDPOINT}/search/voila"
    guide_ws.cell(row=voila_row, column=1).style = "Hyperlink"

    guide_ws.cell(
        row=guide_row,
        column=1,
        value="The Voila notebook automatically formats measurement files, so manual renaming is not required. We recommend using this method from now on. For how-to-guide, click here",
    )
    guide_ws.cell(
        row=guide_row, column=1
    ).hyperlink = (
        "https://scribehow.com/viewer/How_to_Work_on_the_HZB_Nomad_Oasis__bRbhHOaCR2S3dBIeQLYw8A"
    )
    guide_ws.cell(row=guide_row, column=1).style = "Hyperlink"

    # Set column widths for readability
    for col in "ABCDE":
        guide_ws.column_dimensions[col].width = 28
