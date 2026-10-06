"""
IV Converter Module
Converts Puri JV measurement files from _ivraw.csv format to old LTI format
"""

__author__ = "Felix Laufer and Joshua Damm"
__institution__ = "KIT"
__created__ = "January 2026"

import io
import os
import re
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def parse_filename_base(filename: str, suffix: str) -> Tuple[str, int]:
    """
    Strip file suffix, datetime stamp, and optional cycle info from a filename.

    Expected tail pattern: [_Cycle_{N}]_{YYMMDD}_{HHMMSS}{suffix}

    Returns:
        (base_name, cycle_number)  –  cycle_number defaults to 0 if not in filename
    """
    # Strip suffix (case-insensitive)
    if filename.lower().endswith(suffix.lower()):
        name = filename[: -len(suffix)]
    else:
        name = os.path.splitext(filename)[0]

    # Strip trailing datetime stamp  _YYMMDD_HHMMSS
    name = re.sub(r"_\d{6}_\d{6}$", "", name)

    # Extract and strip optional _Cycle_N
    cycle_match = re.search(r"_Cycle_(\d+)$", name, re.IGNORECASE)
    if cycle_match:
        cycle_num = int(cycle_match.group(1))
        name = name[: cycle_match.start()]
    else:
        cycle_num = 0

    return name, cycle_num


def extract_channel_from_block(block_lines: List[str]) -> Optional[int]:
    """Extract the channel/pixel number from a block header line.

    Block header format: Time(s):...,Channel:N,...
    Returns the integer channel number, or None if not found.
    """
    if block_lines:
        match = re.search(r"Channel:(\d+)", block_lines[0])
        if match:
            return int(match.group(1))
    return None


def parse_sample_blocks(lines: List[str]) -> List[List[str]]:
    """Parse lines into sample measurement blocks"""
    blocks = []
    block = []
    for line in lines:
        if line.startswith("Time(s):"):
            if block:
                blocks.append(block)
            block = [line]
        elif block:
            block.append(line)
    if block:
        blocks.append(block)
    return blocks


def extract_metadata(header_lines: List[str]) -> Dict[str, str]:
    """Extract metadata from header lines"""
    metadata = {}
    for line in header_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata


def format_old_file(
    sample_name: str,
    area: str,
    is_illuminated: bool,
    date: str,
    scan1: List[Tuple[float, float]],
    scan2: List[Tuple[float, float]],
    comment: str = "",
) -> str:
    """Format data into old LTI format"""
    header = [
        "LTI @ KIT\tPV cell J-V measurement - measured by Puri \t\t",
        f"Cell ID:\t{sample_name}\t\t",
        f"Cell area [cm²]:\t{area}\t\t",
        f"Cell illuminated\t{int(is_illuminated)}\t\t",
        f"{date}\t\t",
        "Jsc [mA/cm²]:\t0.000000E+0\t0.000000E+0\t",
        "Voc [V]:\t0.000000E+0\t0.000000E+0\t",
        "Fill factor:\t0.000000E+0\t0.000000E+0\t",
        "Efficiency:\t0.000000E+0\t0.000000E+0\t",
        f"Commentary:\t{comment}\t\t",
        "Hysteresis\t1\t\t",
        "Voltage [V]\tCurrent density [1] [mA/cm^2]\tCurrent density [2] [mA/cm^2]\tAverage current density [mA/cm^2]",
    ]

    data_lines = []
    for (v1, j1), (v2, j2) in zip(scan1, reversed(scan2)):
        avg = (j1 + j2) / 2
        data_lines.append(f"{v1:.6E}\t{j1:.6E}\t{j2:.6E}\t{avg:.6E}")

    return "\n".join(header + data_lines)


def parse_scan(scan_lines: List[str]) -> List[Tuple[float, float]]:
    """Parse scan data from lines"""
    try:
        data_start = scan_lines.index(
            next(line for line in scan_lines if line.startswith("Voltage"))
        )
        data = scan_lines[data_start + 1 :]
        return [(float(v), float(j)) for v, j in (row.split(",") for row in data)]
    except (ValueError, StopIteration):
        return []


def process_single_file(
    file_content: str, original_filename: str, output_folder: str = ""
) -> Dict[str, str]:
    """
    Process a single IV file and return dict of {output_filename: content}

    Args:
        file_content: Content of the input file
        original_filename: Original name of the file
        output_folder: Path to output folder (for cycle detection)

    Returns:
        Dictionary mapping output filenames to their content
    """
    results = {}

    lines = [line.strip() for line in file_content.split("\n") if line.strip()]

    # Extract header
    header_lines = []
    data_start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("Time(s):"):
            data_start_idx = i
            break
        header_lines.append(line)

    # Extract metadata
    metadata = extract_metadata(header_lines)
    sample_name = metadata.get("Sample Name", "unknown_sample")
    area = metadata.get("Active Area (cm2)", "1.0")
    date = metadata.get("Test Start Time", "20000000_00:00:00")
    comment = metadata.get("Remarks", "")

    try:
        date = datetime.strptime(date, "%Y%m%d_%H:%M:%S").strftime("%Y-%m-%d\t%H:%M:%S")
    except ValueError:
        date = "2000-01-01\t00:00:00"

    is_illuminated = float(metadata.get("Illumination Intensity (mW/cm2)", "0")) > 0

    # Parse blocks
    blocks = parse_sample_blocks(lines[data_start_idx:])

    # Resolve base name and starting cycle from the filename
    original_base = None
    base_cycle = 0
    for ext in ("_ivraw.csv", ".jv.csv", ".csv"):
        if original_filename.lower().endswith(ext):
            original_base, base_cycle = parse_filename_base(original_filename, ext)
            break
    if original_base is None:
        original_base = os.path.splitext(original_filename)[0]

    # channel -> next cycle number to assign (starts at base_cycle per channel)
    channel_cycle_counter: Dict[int, int] = {}

    # Process pairs of scans (forward + reverse per channel)
    for idx in range(0, len(blocks), 2):
        try:
            forward_lines = blocks[idx]
            reverse_lines = blocks[idx + 1]
        except IndexError:
            continue

        forward = parse_scan(forward_lines)
        reverse = parse_scan(reverse_lines)

        if not forward or not reverse:
            continue

        # Prefer channel number from block header; fall back to sequential index
        channel = extract_channel_from_block(forward_lines)
        if channel is None:
            channel = idx // 2 + 1

        # Determine cycle for this channel occurrence
        current_cycle = channel_cycle_counter.get(channel, base_cycle)

        # Resolve filename conflicts (e.g. if the same channel/cycle combo
        # was already produced by a previous measurement in this file)
        filename = f"{original_base}.px{channel}Cycle_{current_cycle}.jv.csv"
        while filename in results:
            current_cycle += 1
            filename = f"{original_base}.px{channel}Cycle_{current_cycle}.jv.csv"

        # Advance counter so the next occurrence of this channel gets Cycle+1
        channel_cycle_counter[channel] = current_cycle + 1

        content = format_old_file(
            sample_name, area, is_illuminated, date, forward, reverse, comment
        )
        results[filename] = content

    return results


def process_pt_file(file_content: str, original_filename: str) -> Dict[str, str]:
    """
    Process a PT (MPP tracking) file.

    Skips the file if it contains no numeric data rows after the column header.
    Pixel number is read from the "Discharge Channel: N" metadata line.
    Cycle number is parsed from the filename; defaults to 0 if absent.

    Returns:
        {output_filename: original_file_content}  or  {} when file is empty
    """
    lines = [line.strip() for line in file_content.split("\n") if line.strip()]

    # Locate the data-header line (starts with "Time(s)")
    data_header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("Time(s)"):
            data_header_idx = i
            break

    if data_header_idx is None:
        return {}

    # Check for at least one numeric data row after the header
    has_data = False
    for line in lines[data_header_idx + 1 :]:
        try:
            float(line.split(",")[0].strip())
            has_data = True
            break
        except (ValueError, IndexError):
            continue

    if not has_data:
        return {}

    # Extract pixel from "Discharge Channel: N" in the metadata section
    pixel = 1
    for line in lines[:data_header_idx]:
        match = re.match(r"Discharge\s+Channel\s*:\s*(\d+)", line, re.IGNORECASE)
        if match:
            pixel = int(match.group(1))
            break

    base_name, cycle_num = parse_filename_base(original_filename, "_PT.csv")
    output_filename = f"{base_name}.px{pixel}Cycle_{cycle_num}.mpp.csv"
    return {output_filename: file_content}


def process_files(files_dict: Dict[str, bytes], output_folder: str = "") -> Tuple[bytes, int]:
    """
    Process multiple files and return a zip file as bytes

    Args:
        files_dict: Dictionary mapping filenames to file content (as bytes)
        output_folder: Path to output folder (for cycle detection)

    Returns:
        Tuple of (zip_file_content, number_of_files_processed)
    """
    # Create in-memory zip file
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        total_processed = 0

        for filename, content in files_dict.items():
            # Normalize to bytes
            if isinstance(content, memoryview):
                content = content.tobytes()
            # Decode content
            try:
                file_content = content.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    file_content = content.decode("latin-1")
                except Exception:
                    continue

            # Route to the appropriate processor
            if filename.lower().endswith("_pt.csv"):
                results = process_pt_file(file_content, filename)
            elif filename.lower().endswith("_iv.csv"):
                continue  # summary files – skip
            else:
                results = process_single_file(file_content, filename, output_folder)

            # Add results to zip
            for output_name, output_content in results.items():
                zip_file.writestr(output_name, output_content)
                total_processed += 1

    zip_buffer.seek(0)
    return zip_buffer.read(), total_processed


def process_zip_file(zip_content: bytes) -> Tuple[bytes, int]:
    """
    Process files from an uploaded zip file

    Args:
        zip_content: Content of uploaded zip file

    Returns:
        Tuple of (output_zip_content, number_of_files_processed)
    """
    files_dict = {}

    # Extract files from input zip
    with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_ref:
        for file_info in zip_ref.filelist:
            if file_info.filename.lower().endswith(("_ivraw.csv", "_pt.csv", ".jv.csv", ".csv")):
                files_dict[os.path.basename(file_info.filename)] = zip_ref.read(file_info)

    return process_files(files_dict)
