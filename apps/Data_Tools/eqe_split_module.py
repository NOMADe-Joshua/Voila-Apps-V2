"""
EQE Split Module
Splits single EQE measurement files containing multiple measurements into individual files
with naming convention: KIT_NaMe_YYYYMMDD_Batch_A_B.position.pxNCycle_M.eqe.txt
"""

__author__ = "Felix Laufer and Joshua Damm"
__institution__ = "KIT"
__created__ = "March 2026"

import io
import os
import re
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def parse_eqe_file(content: str) -> List[Dict]:
    """
    Parse EQE data file with multiple measurements arranged in columns.
    The file structure has multiple measurement blocks side by side:
    - Each block: columns N, N+1, N+2, N+3 contain [Lambda(nm), EQE(%), SR(A/W), Jsc(mA/cm^2)]
    - Metadata before the Lambda(nm) row

    Args:
        content: Raw file content as string

    Returns:
        List of dictionaries, each containing metadata and data for one measurement
    """
    lines = content.strip().split("\n")

    # Clean lines and split by tabs
    table = []
    for line in lines:
        row = line.split("\t")
        table.append(row)

    if not table:
        return []

    # Find the row that contains "Lambda(nm)" to know where data starts
    lambda_row_idx = None
    for idx, row in enumerate(table):
        if any("Lambda(nm)" in str(cell) for cell in row):
            lambda_row_idx = idx
            break

    if lambda_row_idx is None:
        return []

    # Find all columns that start a measurement block (columns with Lambda(nm))
    data_col_starts = []
    lambda_row = table[lambda_row_idx]
    for col_idx in range(len(lambda_row)):
        if "Lambda(nm)" in str(lambda_row[col_idx]):
            data_col_starts.append(col_idx)

    if not data_col_starts:
        return []

    measurements = []

    # Extract each measurement
    for meas_idx, data_col_start in enumerate(data_col_starts):
        measurement = {"index": meas_idx + 1, "metadata": {}, "data": []}

        # Extract metadata (rows before Lambda(nm) row)
        for row_idx in range(lambda_row_idx):
            row = table[row_idx]
            if data_col_start < len(row):
                cell_val = row[data_col_start].strip()

                # Skip empty cells and known header values
                if not cell_val or cell_val in [
                    "",
                    "Lambda(nm)",
                    "EQE (%)",
                    "SR (A/W)",
                    "Jsc (mA/cm^2)",
                ]:
                    continue

                # Try to get metadata key-value pairs
                # Check if next column has the value
                if data_col_start + 1 < len(row):
                    value_cell = row[data_col_start + 1].strip()
                    # If both cells have content and second cell looks like a value, it's metadata
                    if value_cell and not any(
                        x in value_cell for x in ["Lambda", "EQE", "SR", "Jsc"]
                    ):
                        measurement["metadata"][cell_val] = value_cell

        # Extract data rows (after Lambda(nm) row)
        for row_idx in range(lambda_row_idx + 1, len(table)):
            row = table[row_idx]
            if data_col_start < len(row):
                lambda_cell = row[data_col_start].strip()
                if not lambda_cell:
                    continue

                try:
                    lambda_val = float(lambda_cell.replace(",", "."))

                    # Get EQE, SR, Jsc from next columns
                    eqe_val = 0.0
                    sr_val = 0.0
                    jsc_val = 0.0

                    if data_col_start + 1 < len(row):
                        try:
                            cell = row[data_col_start + 1].strip().replace(",", ".")
                            eqe_val = float(cell or 0)
                        except ValueError:
                            pass

                    if data_col_start + 2 < len(row):
                        try:
                            cell = row[data_col_start + 2].strip().replace(",", ".")
                            sr_val = float(cell or 0)
                        except ValueError:
                            pass

                    if data_col_start + 3 < len(row):
                        try:
                            cell = row[data_col_start + 3].strip().replace(",", ".")
                            jsc_val = float(cell or 0)
                        except ValueError:
                            pass

                    measurement["data"].append(
                        {"lambda": lambda_val, "eqe": eqe_val, "sr": sr_val, "jsc": jsc_val}
                    )
                except (ValueError, IndexError):
                    continue

        # Only add measurement if it has data
        if measurement["data"]:
            measurements.append(measurement)

    return measurements


def generate_filename(
    name: str,
    date: str,
    batch: str,
    a: str,
    b: str,
    position: Optional[str] = None,
    n: Optional[str] = None,
    m: Optional[str] = None,
) -> str:
    """
    Generate filename with pattern: KIT_NaMe_YYYYMMDD_Batch_A_B.position.pxNCycle_M.eqe.txt

    Args:
        name: Sample name (required)
        date: Date in format YYYYMMDD (required)
        batch: Batch identifier (required)
        a: First identifier (required)
        b: Second identifier (required)
        position: Position (optional)
        n: Wavelength point number (optional)
        m: Cycle number (optional)

    Returns:
        Generated filename
    """
    filename = f"KIT_{name}_{date}_{batch}_{a}_{b}"

    if position:
        filename += f".{position}"

    n_value = str(n).strip() if n is not None else ""
    m_value = str(m).strip() if m is not None else ""

    # Optional tail rules:
    # - N + M -> .pxNCycle_M
    # - N only -> .pxN
    # - M only -> .Cycle_M (without px)
    # - neither -> omit the whole segment
    if n_value and m_value:
        filename += f".px{n_value}Cycle_{m_value}"
    elif n_value:
        filename += f".px{n_value}"
    elif m_value:
        filename += f".Cycle_{m_value}"

    filename += ".eqe.txt"

    return filename


def format_eqe_output(measurement: Dict, metadata: Dict) -> str:
    """
    Format measurement data into output format.

    Args:
        measurement: Measurement data dictionary
        metadata: Global metadata dictionary

    Returns:
        Formatted file content
    """
    lines = []
    lines.append("Lambda(nm)\tEQE (%)\tSR (A/W)\tJsc (mA/cm^2)")

    for point in measurement["data"]:
        lines.append(
            f"{point['lambda']:.1f}\t{point['eqe']:.6f}\t{point['sr']:.6f}\t{point['jsc']:.6f}"
        )

    return "\n".join(lines)


def process_eqe_file(file_content: bytes, file_configs: List[Dict]) -> Dict:
    """
    Process EQE file and create individual measurement files.

    Args:
        file_content: Raw file content
        file_configs: List of configuration dicts for each measurement with keys:
                     'b', 'position' (optional), 'n' (optional), 'm' (optional)
        Global settings should be in first config: 'name', 'date', 'batch', 'a'

    Returns:
        Dictionary with generated files: {filename: content}
    """
    # Convert bytes / bytearray / memoryview to string
    if isinstance(file_content, (bytes, bytearray, memoryview)):
        text_content = bytes(file_content).decode("utf-8", errors="ignore")
    else:
        text_content = str(file_content)

    # Parse measurements
    measurements = parse_eqe_file(text_content)

    if not measurements:
        raise ValueError("Could not parse any measurements from file")

    # Get global settings from first config
    if not file_configs:
        raise ValueError("No configuration provided")

    global_config = file_configs[0]
    name = global_config.get("name", "")
    date = global_config.get("date", "")
    batch = global_config.get("batch", "")
    a = global_config.get("a", "")

    if not all([name, date, batch, a]):
        raise ValueError("Missing required global parameters: name, date, batch, a")

    # Per-measurement configs follow the first global config
    measurement_configs = file_configs[1:]
    if len(measurement_configs) < len(measurements):
        raise ValueError(
            f"Insufficient measurement configs: expected {len(measurements)}, got {len(measurement_configs)}"
        )

    # Generate files for each measurement
    output_files = {}

    for meas_idx, measurement in enumerate(measurements):
        config = measurement_configs[meas_idx]
        b = config.get("b", "")
        position = config.get("position", None)
        n = config.get("n", None)
        m = config.get("m", None)

        # Per-measurement overrides fall back to global if not set
        meas_name = config.get("name") or name
        meas_date = config.get("date") or date
        meas_batch = config.get("batch") or batch
        meas_a = config.get("a") or a

        if not b:
            raise ValueError(f"Missing required parameter 'B' for measurement {meas_idx + 1}")

        # Generate filename
        filename = generate_filename(meas_name, meas_date, meas_batch, meas_a, b, position, n, m)

        # Format content
        content = format_eqe_output(measurement, global_config)

        output_files[filename] = content

    return output_files


def create_download_zip(output_files: Dict[str, str]) -> bytes:
    """
    Create a ZIP file from output files.

    Args:
        output_files: Dictionary with filenames as keys and content as values

    Returns:
        ZIP file as bytes
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in output_files.items():
            zip_file.writestr(filename, content)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()
