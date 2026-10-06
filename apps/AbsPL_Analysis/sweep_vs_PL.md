# AbsPL: Sweep vs. Single PL – Unterscheidung

## Kontext
Parser: `KIT_abspl_parser.py`  
Schema-Klasse: `peroTF_AbsPLMeasurement` (in `perotf_package.py`)  
Beide Messtypen werden unter **derselben Schema-Klasse** gespeichert.

---

## Dateiformat-Unterschiede

### Single PL (`_FD7.abspl.txt`)
- Header: `key\tvalue` – genau **2 Felder pro Zeile**
- Erster Header-Eintrag ist ein einzelner Timestamp: `Time\t5/27/2026 2:04:23 PM`
- Datenspalten nach `---`: **4 Spalten** – `Wavelength`, `Luminescence flux density`, `Raw spectrum`, `Dark spectrum`
- Enthält kalibrierten **Lumineszenz-Fluss** und **Dark-Spektrum**

### Sweep (`_D1.abspl.txt`)
- Header: `key\tv1\tv2\t...vN` – **N+1 Felder pro Zeile** (eine Spalte pro Intensitätsstufe)
- Erster Header-Eintrag sind mehrere Timestamps: `10/9/2025\t3:14:10 PM\t3:14:13 PM\t...`
- Datenspalten nach `---`: **N+1 Spalten** – `Wavelength` + N × `Raw spectrum`
- Kein kalibrierter Flux, kein Dark-Spektrum

### Schnellster Datei-Typ-Check
```python
def detect_file_type(lines):
    """Returns 'sweep' or 'single'."""
    for line in lines:
        if line.strip().startswith("---"):
            break
        if "\t" in line:
            if len(line.split("\t")) > 2:
                return "sweep"
    return "single"
```

---

## Unterschiede im gespeicherten Archiv (auf dem Server)

| Feld | Single PL | Sweep |
|---|---|---|
| `len(results)` | **1** | **N** (eine pro Intensitätsstufe) |
| `results[0].luminescence_flux_density` | **befüllt** | `None` |
| `results[0].dark_spectrum_counts` | **befüllt** | `None` |
| `results[0].raw_spectrum_counts` | befüllt | befüllt |
| `settings.laser_intensity_suns` | ein Wert (z.B. `2.97`) | ein Wert (Mittelwert o.ä.) |

### Empfohlener Check im Archiv
```python
is_sweep = len(entry.results) > 1
# oder alternativ:
is_sweep = entry.results[0].luminescence_flux_density is None
```

---

## Warum verhält es sich so?

In `peroTF_AbsPLMeasurement.normalize()` (perotf_package.py):

1. Zuerst wird `parse_abspl_data()` aufgerufen → füllt `result_vals`
2. **Wenn `result_vals` nicht leer**: Single PL → setzt `luminescence_flux_density`, `dark_spectrum_counts`, genau **1 Result**
3. **Wenn `result_vals` leer**: Sweep → `parse_multiple_abspl()` wird aufgerufen → setzt **N Results**, nur `wavelength` + `raw_spectrum_counts` pro Result

Der Fallback auf `parse_multiple_abspl` ist das implizite Unterscheidungsmerkmal im aktuellen Code.
