"""
JV File Organizer Module
Handles renaming and organizing of JV measurement files
"""

import csv
import io
import os
import re
import zipfile


def process_mpp_files(files_dict):
    """
    Process MPP files - remove SPP prefix and reorganize

    Args:
        files_dict: {filename: content_bytes}

    Returns:
        {filename: modified_content_bytes}
    """
    mpp_files = {}

    for filename, content in files_dict.items():
        if "MPP" in filename.upper():
            try:
                # Parse CSV content
                content_str = content.decode("utf-8", errors="replace")
                lines = content_str.strip().split("\n")

                # Process CSV lines
                reader = csv.reader(lines)
                processed_lines = []

                for idx, row in enumerate(reader):
                    if idx == 0 and row and row[0].startswith("SPP"):
                        # Remove "SPP" prefix from first column
                        row[0] = row[0][3:]
                    processed_lines.append(row)

                # Write back to CSV format
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerows(processed_lines)

                mpp_files[filename] = output.getvalue().encode("utf-8")

            except Exception as e:
                print(f"Warning: Could not process {filename}: {e}")
                mpp_files[filename] = content

    return mpp_files


def filter_soak_files(files_dict, cycle_to_keep, preserve_cycle):
    """
    Filter soak files based on cycle selection

    Args:
        files_dict: {filename: content_bytes}
        cycle_to_keep: Cycle number to keep (0-9)
        preserve_cycle: Boolean, if True keep all cycles

    Returns:
        {filename: content_bytes} - Only soak files matching criteria
    """
    soak_files = {}
    cycle_pattern = re.compile(r"Cycle_(\d)_illu")

    for filename, content in files_dict.items():
        if "Cycle" in filename and "illu" in filename:
            # Check if this is a soak file (has Cycle_X_illu pattern)
            if cycle_pattern.search(filename):
                if preserve_cycle:
                    # Keep all cycle files
                    soak_files[filename] = content
                else:
                    # Only keep files with the selected cycle
                    if f"Cycle_{cycle_to_keep}_illu" in filename:
                        soak_files[filename] = content

    return soak_files


def rename_jv_files(files_dict, cycle_to_keep, preserve_cycle):
    """
    Rename JV files according to pattern rules

    Args:
        files_dict: {filename: content_bytes}
        cycle_to_keep: Cycle number to keep (0-9)
        preserve_cycle: Boolean, preserve cycle info in filename

    Returns:
        {new_filename: content_bytes}
    """
    rename_patterns = {"_01_C": ".px1C", "_02_C": ".px2C", "_03_C": ".px3C", "_04_C": ".px4C"}

    renamed_files = {}

    for filename, content in files_dict.items():
        # Only process cycle files
        if "Cycle" not in filename or "illu" not in filename:
            renamed_files[filename] = content
            continue

        # Skip if not matching cycle (unless preserving)
        if not preserve_cycle and f"Cycle_{cycle_to_keep}_illu" not in filename:
            continue

        new_name = filename

        # Remove _illu from filename
        new_name = new_name.replace("_illu", "")

        # Apply rename patterns
        for pattern, replacement in rename_patterns.items():
            if pattern in new_name:
                new_name = new_name.replace(pattern, replacement)

        # Replace .csv with .jv.csv if not already done
        if new_name.endswith(".csv") and not new_name.endswith(".jv.csv"):
            new_name = new_name[:-4] + ".jv.csv"

        renamed_files[new_name] = content

    return renamed_files


def process_files(files_dict, cycle_to_keep=0, preserve_cycle=False):
    """
    Main processing function - organizes and renames JV files

    Args:
        files_dict: {filename: content_bytes}
        cycle_to_keep: Cycle number to keep (0-9)
        preserve_cycle: Boolean, preserve cycle info

    Returns:
        (zip_bytes, num_processed, errors_list)
    """
    errors = []

    try:
        # Validate cycle
        if not isinstance(cycle_to_keep, int) or cycle_to_keep < 0 or cycle_to_keep > 9:
            cycle_to_keep = 0

        # Process MPP files
        mpp_files = process_mpp_files(files_dict)

        # Filter soak files
        soak_files = filter_soak_files(files_dict, cycle_to_keep, preserve_cycle)

        # Rename JV files (includes soak files)
        renamed_files = rename_jv_files(files_dict, cycle_to_keep, preserve_cycle)

        # Merge results (MPP + renamed files)
        result_files = {}

        # Add MPP files to MaxPowerPointTracking subdirectory
        for filename, content in mpp_files.items():
            new_filename = f"MaxPowerPointTracking/{filename}"
            result_files[new_filename] = content

        # Add Soak files to Soak subdirectory
        for filename, content in soak_files.items():
            new_filename = f"Soak/{filename}"
            result_files[new_filename] = content

        # Add renamed files (excluding soak files which go to Soak folder)
        for filename, content in renamed_files.items():
            # Skip if already in soak
            cycle_pattern = re.compile(r"Cycle_(\d)_illu")
            if not (cycle_pattern.search(filename) and "illu" in filename):
                result_files[filename] = content

        # Create ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for filename, content in result_files.items():
                zip_file.writestr(filename, content)

        zip_buffer.seek(0)
        num_processed = len(result_files)

        return zip_buffer.getvalue(), num_processed, errors

    except Exception as e:
        errors.append(str(e))
        return None, 0, errors


def process_zip_file(zip_content, cycle_to_keep=0, preserve_cycle=False):
    """
    Process a ZIP file containing JV measurements

    Args:
        zip_content: bytes of ZIP file
        cycle_to_keep: Cycle number to keep (0-9)
        preserve_cycle: Boolean, preserve cycle info

    Returns:
        (output_zip_bytes, num_processed, errors_list)
    """
    try:
        # Extract ZIP
        files_dict = {}
        with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_ref:
            for file_info in zip_ref.filelist:
                if not file_info.is_dir():
                    # Get just the filename, not the full path
                    filename = os.path.basename(file_info.filename)
                    files_dict[filename] = zip_ref.read(file_info)

        # Process files
        return process_files(files_dict, cycle_to_keep, preserve_cycle)

    except Exception as e:
        return None, 0, [str(e)]
