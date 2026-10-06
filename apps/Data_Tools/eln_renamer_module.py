"""
ELN Renamer Module
Renames files according to ELN naming schema: KIT_{kuerzel}_{datum}_{filename}_0_{i}.px{pixel}Cycle_{cycle}.{prozessart}.csv
"""

import datetime
import io
import os
import re
import zipfile


def extract_x_y(filename):
    """Extract pixel (x) and cycle (y) from filename pattern"""
    pattern = r"_([0-9]{2})_Cycle_([0-9]+)_illu\.csv$"
    match = re.search(pattern, filename)
    if match:
        x = match.group(1)
        y = match.group(2)
        return int(x), int(y)
    return None


def get_oldest_file_date(files_dict):
    """
    Get the oldest file date from a dictionary of files

    Args:
        files_dict: {filename: content_bytes}

    Returns:
        Date string in YYYYMMDD format
    """
    try:
        if not files_dict:
            return datetime.datetime.now().strftime("%Y%m%d")

        # Since we don't have file modification times, use current date
        # In real file system, this would check os.path.getmtime()
        return datetime.datetime.now().strftime("%Y%m%d")
    except Exception:
        return datetime.datetime.now().strftime("%Y%m%d")


def rename_files(files_dict, kuerzel, datum, prozessart):
    """
    Rename files according to ELN schema

    Args:
        files_dict: {filename: content_bytes}
        kuerzel: Name abbreviation (e.g., RaPe, DaBa, ThFe)
        datum: Date string in YYYYMMDD format
        prozessart: Process type (e.g., jv, eqe)

    Returns:
        {new_filename: content_bytes}
    """
    renamed_files = {}
    file_counter = {}  # Track counter for each base name
    last_base = None
    i = 0

    # Sort files to process them in order
    sorted_files = sorted(files_dict.keys())

    for filename in sorted_files:
        content = files_dict[filename]

        # Extract pixel and cycle info
        stringabfrage = extract_x_y(filename)

        # Determine cut position for filename
        if stringabfrage:
            pixel, cycle_measurement = stringabfrage
            cut = 20 if len(filename) > 20 else 4
            base_name = filename[:-cut]  # Remove _XX_Cycle_Y_illu
        else:
            cut = 4  # Remove .csv
            base_name = filename[:-cut]
            cycle_measurement = 0
            pixel = 0

        # Replace underscores with dashes in base name
        base_name_formatted = base_name.replace("_", "-")

        # Increment counter for new base names
        if last_base is None or last_base != base_name:
            i = 0
            last_base = base_name
        else:
            i += 1

        # Build new filename
        if stringabfrage:
            pixel, cycle_measurement = stringabfrage
            new_filename = f"KIT_{kuerzel}_{datum}_{base_name_formatted}_0_{i}.px{pixel}Cycle_{cycle_measurement}.{prozessart}.csv"
        else:
            new_filename = (
                f"KIT_{kuerzel}_{datum}_{base_name_formatted}_0_{i}.px0Cycle_0.{prozessart}.csv"
            )

        renamed_files[new_filename] = content

    return renamed_files


def process_files(files_dict, kuerzel, datum, prozessart, use_auto_date=False):
    """
    Main processing function for ELN renaming

    Args:
        files_dict: {filename: content_bytes}
        kuerzel: Name abbreviation
        datum: Date string (YYYYMMDD)
        prozessart: Process type
        use_auto_date: If True, use oldest file date (ignored in this version)

    Returns:
        (zip_bytes, num_processed, errors_list)
    """
    errors = []

    try:
        # Validate inputs
        if not kuerzel or not kuerzel.strip():
            errors.append("Kürzel (name abbreviation) is required")

        if not datum or not datum.strip():
            datum = datetime.datetime.now().strftime("%Y%m%d")

        # Validate date format
        try:
            datetime.datetime.strptime(datum, "%Y%m%d")
        except ValueError:
            errors.append(f"Invalid date format: {datum}. Use YYYYMMDD")
            return None, 0, errors

        if not prozessart or not prozessart.strip():
            errors.append("Process type (e.g., jv, eqe) is required")

        if errors:
            return None, 0, errors

        # Rename files
        renamed_files = rename_files(files_dict, kuerzel, datum, prozessart)

        # Create ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for filename, content in renamed_files.items():
                zip_file.writestr(filename, content)

        zip_buffer.seek(0)
        num_processed = len(renamed_files)

        return zip_buffer.getvalue(), num_processed, errors

    except Exception as e:
        errors.append(str(e))
        return None, 0, errors


def process_zip_file(zip_content, kuerzel, datum, prozessart, use_auto_date=False):
    """
    Process a ZIP file containing files to rename

    Args:
        zip_content: bytes of ZIP file
        kuerzel: Name abbreviation
        datum: Date string (YYYYMMDD)
        prozessart: Process type
        use_auto_date: If True, use oldest file date

    Returns:
        (output_zip_bytes, num_processed, errors_list)
    """
    try:
        # Extract ZIP
        files_dict = {}
        with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_ref:
            for file_info in zip_ref.filelist:
                if not file_info.is_dir():
                    filename = os.path.basename(file_info.filename)
                    files_dict[filename] = zip_ref.read(file_info)

        # Process files
        return process_files(files_dict, kuerzel, datum, prozessart, use_auto_date)

    except Exception as e:
        return None, 0, [str(e)]
