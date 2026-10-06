"""
UV-Vis Merger Module
Merges transmission and reflection UV-Vis spectroscopy data files
"""

__author__ = "Joshua Damm"
__institution__ = "KIT"
__created__ = "January 2026"

import io
import os
import re
import zipfile
from typing import Dict, List, Optional, Tuple

import pandas as pd


def find_matching_pairs(files_dict: Dict[str, bytes]) -> List[Tuple[str, str, str]]:
    """
    Find matching transmission and reflection file pairs based on filename patterns.

    Files are considered pairs if they differ only by a single letter (t, T, r, R).

    Args:
        files_dict: Dictionary mapping filenames to file content (bytes)

    Returns:
        List of tuples: (transmission_filename, reflection_filename, base_name)
    """
    pairs = []
    processed = set()

    for filename in files_dict.keys():
        if filename in processed:
            continue

        # Generate potential matching filenames by replacing T/t with R/r
        base_no_ext = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1]

        # Create all possible matching patterns
        candidates = []

        # If it ends with _T or _t, look for _R or _r variant
        if base_no_ext.endswith("_T"):
            candidates.append(f"{base_no_ext[:-1]}R{ext}")
            candidates.append(f"{base_no_ext[:-1]}r{ext}")
        elif base_no_ext.endswith("_t"):
            candidates.append(f"{base_no_ext[:-1]}R{ext}")
            candidates.append(f"{base_no_ext[:-1]}r{ext}")
        elif base_no_ext.endswith("_R"):
            candidates.append(f"{base_no_ext[:-1]}T{ext}")
            candidates.append(f"{base_no_ext[:-1]}t{ext}")
        elif base_no_ext.endswith("_r"):
            candidates.append(f"{base_no_ext[:-1]}T{ext}")
            candidates.append(f"{base_no_ext[:-1]}t{ext}")

        # Also try patterns without underscore
        if base_no_ext.endswith("T"):
            candidates.append(f"{base_no_ext[:-1]}R{ext}")
            candidates.append(f"{base_no_ext[:-1]}r{ext}")
        elif base_no_ext.endswith("t"):
            candidates.append(f"{base_no_ext[:-1]}R{ext}")
            candidates.append(f"{base_no_ext[:-1]}r{ext}")
        elif base_no_ext.endswith("R"):
            candidates.append(f"{base_no_ext[:-1]}T{ext}")
            candidates.append(f"{base_no_ext[:-1]}t{ext}")
        elif base_no_ext.endswith("r"):
            candidates.append(f"{base_no_ext[:-1]}T{ext}")
            candidates.append(f"{base_no_ext[:-1]}t{ext}")

        # Find which candidate exists in our files
        for candidate in candidates:
            if candidate in files_dict and candidate not in processed:
                # Determine which is transmission and which is reflection
                if base_no_ext[-1] in ["T", "t"]:
                    transmission_file = filename
                    reflection_file = candidate
                else:
                    transmission_file = candidate
                    reflection_file = filename

                # Extract base name for output (remove T/R designation)
                base_name = base_no_ext[:-1]  # Remove the last character (T/t/R/r)

                pairs.append((transmission_file, reflection_file, base_name))
                processed.add(filename)
                processed.add(candidate)
                break

    return pairs


def merge_uvvis_files(
    transmission_content: str, reflection_content: str, filename_trans: str, filename_refl: str
) -> str:
    """
    Merge transmission and reflection UV-Vis data files.

    Args:
        transmission_content: Content of transmission file
        reflection_content: Content of reflection file
        filename_trans: Transmission filename (to detect format)
        filename_refl: Reflection filename (to detect format)

    Returns:
        Merged CSV content as string, or None if error
    """
    try:
        # Detect file format from extension
        if filename_trans.endswith(".csv"):
            df_T = pd.read_csv(
                io.StringIO(transmission_content),
                sep=",",
                header=0,
                names=["Wellenlaenge_T", "Transmission"],
            )
        elif filename_trans.endswith(".dat"):
            df_T = pd.read_csv(
                io.StringIO(transmission_content),
                sep=r"\s+",
                header=None,
                names=["Wellenlaenge_T", "Transmission"],
            )
        else:
            df_T = pd.read_csv(
                io.StringIO(transmission_content),
                sep=None,
                engine="python",
                header=0,
                names=["Wellenlaenge_T", "Transmission"],
            )

        if filename_refl.endswith(".csv"):
            df_R = pd.read_csv(
                io.StringIO(reflection_content),
                sep=",",
                header=0,
                names=["Wellenlaenge_R", "Reflection"],
            )
        elif filename_refl.endswith(".dat"):
            df_R = pd.read_csv(
                io.StringIO(reflection_content),
                sep=r"\s+",
                header=None,
                names=["Wellenlaenge_R", "Reflection"],
            )
        else:
            df_R = pd.read_csv(
                io.StringIO(reflection_content),
                sep=None,
                engine="python",
                header=0,
                names=["Wellenlaenge_R", "Reflection"],
            )

        # Find overlapping wavelength range
        min_wavelength = max(df_R["Wellenlaenge_R"].min(), df_T["Wellenlaenge_T"].min())
        max_wavelength = min(df_R["Wellenlaenge_R"].max(), df_T["Wellenlaenge_T"].max())

        # Filter to overlapping range
        df_R = df_R[
            (df_R["Wellenlaenge_R"] >= min_wavelength) & (df_R["Wellenlaenge_R"] <= max_wavelength)
        ]
        df_T = df_T[
            (df_T["Wellenlaenge_T"] >= min_wavelength) & (df_T["Wellenlaenge_T"] <= max_wavelength)
        ]

        # Extract data
        common_x = df_R["Wellenlaenge_R"].tolist()
        y_reflection = df_R["Reflection"].tolist()
        y_transmission = df_T["Transmission"].tolist()

        # If .dat file, ensure wavelengths are ascending
        if filename_refl.endswith(".dat"):
            common_x.reverse()
            y_reflection.reverse()
            y_transmission.reverse()

        # Create merged dataframe
        df_merged = pd.DataFrame(
            {"wavelength": common_x, "Reflection": y_reflection, "Transmission": y_transmission}
        )

        # Return as CSV string with semicolon separator
        return df_merged.to_csv(index=False, sep=";")

    except Exception as e:
        raise RuntimeError(f"Error merging files: {str(e)}") from e


def process_uvvis_files(
    transmission_files: Dict[str, bytes],
    reflection_files: Dict[str, bytes],
    pairs: Optional[Dict[str, str]] = None,
    output_names: Optional[Dict[str, str]] = None,
) -> Tuple[bytes, int, List[str]]:
    """
    Process UV-Vis transmission and reflection files and create merged output.

    Args:
        transmission_files: Dict of transmission files {filename: content}
        reflection_files: Dict of reflection files {filename: content}
        pairs: Optional pre-computed mapping {trans_filename: refl_filename}.
               When provided, used directly instead of filename-based matching.

    Returns:
        Tuple of (zip_content, number_processed, error_list)
    """
    # Create in-memory zip file
    zip_buffer = io.BytesIO()
    errors = []
    processed = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Find matching pairs
        for trans_file, trans_content in transmission_files.items():
            # Use pre-computed pairs if provided, otherwise fall back to filename matching
            if pairs is not None:
                refl_file = pairs.get(trans_file)
            else:
                # Find matching reflection file by filename pattern
                base_no_ext = os.path.splitext(trans_file)[0]
                ext = os.path.splitext(trans_file)[1]

                # Generate reflection filename candidates
                candidates = []
                if base_no_ext.endswith("_T"):
                    candidates = [f"{base_no_ext[:-1]}R{ext}", f"{base_no_ext[:-1]}r{ext}"]
                elif base_no_ext.endswith("_t"):
                    candidates = [f"{base_no_ext[:-1]}R{ext}", f"{base_no_ext[:-1]}r{ext}"]
                elif base_no_ext.endswith("T"):
                    candidates = [f"{base_no_ext[:-1]}R{ext}", f"{base_no_ext[:-1]}r{ext}"]
                elif base_no_ext.endswith("t"):
                    candidates = [f"{base_no_ext[:-1]}R{ext}", f"{base_no_ext[:-1]}r{ext}"]

                refl_file = None
                for candidate in candidates:
                    if candidate in reflection_files:
                        refl_file = candidate
                        break

            if refl_file is None:
                errors.append(f"No matching reflection file for {trans_file}")
                continue

            # Merge the files
            try:
                trans_str = trans_content.decode("utf-8")
            except UnicodeDecodeError:
                trans_str = trans_content.decode("latin-1")

            try:
                refl_str = reflection_files[refl_file].decode("utf-8")
            except UnicodeDecodeError:
                refl_str = reflection_files[refl_file].decode("latin-1")

            try:
                merged_content = merge_uvvis_files(trans_str, refl_str, trans_file, refl_file)

                # Generate output filename
                base_name = os.path.splitext(trans_file)[0]
                if base_name.endswith("_T") or base_name.endswith("_t"):
                    base_name = base_name[:-2]
                elif base_name.endswith("T") or base_name.endswith("t"):
                    base_name = base_name[:-1]

                output_filename = f"{base_name}.uvvis.csv"
                if output_names and trans_file in output_names:
                    output_filename = output_names[trans_file]
                zip_file.writestr(output_filename, merged_content)
                processed += 1

            except Exception as e:
                errors.append(f"Error processing {trans_file}: {str(e)}")

    zip_buffer.seek(0)
    return zip_buffer.read(), processed, errors
