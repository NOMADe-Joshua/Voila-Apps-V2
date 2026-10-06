"""
Diagnostic Helper for UVVis Data Analysis
Debug tool to inspect data structure and trace issues.
"""

__author__ = "Joshua Damm"
__institution__ = "KIT"
__created__ = "December 2025"

import json

import numpy as np
import pandas as pd


class UVVisDiagnosticHelper:
    """Helper class for debugging UVVis data loading and processing"""

    @staticmethod
    def inspect_measurement(measurement, verbose=True):
        """
        Deeply inspect a single measurement dictionary

        Args:
            measurement: A measurement dictionary
            verbose: Print detailed output
        """
        if verbose:
            print("=" * 80)
            print("MEASUREMENT INSPECTION")
            print("=" * 80)

        # Basic info
        print("\n1. BASIC INFO:")
        print(f"   Type: {type(measurement)}")
        print(f"   Keys: {list(measurement.keys())}")

        # Check for bandgaps specifically
        print("\n2. BANDGAPS_UVVIS FIELD:")
        if "bandgaps_uvvis" in measurement:
            bg = measurement["bandgaps_uvvis"]
            print("   ✓ EXISTS")
            print(f"   Type: {type(bg)}")
            print(f"   Value: {bg}")
            print(f"   Length: {len(bg) if hasattr(bg, '__len__') else 'N/A'}")

            if isinstance(bg, (list, tuple)):
                print("   Elements:")
                for i, elem in enumerate(bg):
                    print(f"      [{i}] Type: {type(elem)}, Value: {elem}")
        else:
            print("   ✗ NOT FOUND")
            print(f"   Available keys: {', '.join(measurement.keys())}")

        # Check measurement_name
        print("\n3. MEASUREMENT_NAME:")
        if "measurement_name" in measurement:
            name = measurement["measurement_name"]
            name_lower = name.lower()
            print(f"   Value: {name}")
            print(f"   Contains 'absorption': {'absorption' in name_lower}")
            print(f"   Contains 'reflection': {'reflection' in name_lower}")
            print(f"   Contains 'transmission': {'transmission' in name_lower}")
        else:
            print("   ✗ NOT FOUND")

        # Check data arrays
        print("\n4. DATA ARRAYS:")
        for key in ["wavelength", "intensity", "reflection", "transmission"]:
            if key in measurement:
                val = measurement[key]
                if val is None:
                    print(f"   {key}: None")
                elif isinstance(val, np.ndarray):
                    print(f"   {key}: numpy array, shape={val.shape}, dtype={val.dtype}")
                    if len(val) > 0:
                        print(f"           First 3 values: {val[:3]}")
                elif isinstance(val, (list, tuple)):
                    print(f"   {key}: {type(val).__name__}, len={len(val)}")
                    if len(val) > 0:
                        print(f"           First 3 values: {val[:3]}")
                else:
                    print(f"   {key}: {type(val)}")
            else:
                print(f"   {key}: NOT FOUND")

        # Check other fields
        print("\n5. OTHER FIELDS:")
        important_fields = ["sample_name", "sample_id", "variation", "batch_id", "metadata"]
        for field in important_fields:
            if field in measurement:
                val = measurement[field]
                if isinstance(val, dict):
                    print(f"   {field}: dict with keys {list(val.keys())}")
                else:
                    print(f"   {field}: {val}")
            else:
                print(f"   {field}: NOT FOUND")

        print("\n" + "=" * 80)

    @staticmethod
    def inspect_all_measurements(measurements, max_to_show=3):
        """
        Inspect multiple measurements

        Args:
            measurements: List of measurement dictionaries
            max_to_show: Maximum number to show in detail
        """
        print(f"\n{'=' * 80}")
        print(f"INSPECTING {len(measurements)} TOTAL MEASUREMENTS")
        print(f"{'=' * 80}\n")

        # Summary statistics
        has_bandgaps = sum(1 for m in measurements if "bandgaps_uvvis" in m and m["bandgaps_uvvis"])
        has_absorption = sum(
            1 for m in measurements if "absorption" in m.get("measurement_name", "").lower()
        )

        print("SUMMARY:")
        print(f"  Total measurements: {len(measurements)}")
        print(
            f"  With bandgaps_uvvis field: {sum(1 for m in measurements if 'bandgaps_uvvis' in m)}"
        )
        print(f"  With non-empty bandgaps_uvvis: {has_bandgaps}")
        print(f"  With 'absorption' in name: {has_absorption}")

        # Show variations
        variations = set(m.get("variation", "Unknown") for m in measurements)
        print(f"\nVARIATIONS ({len(variations)}):")
        for var in sorted(variations):
            count = sum(1 for m in measurements if m.get("variation") == var)
            print(f"  - {var}: {count} measurements")

        # Show measurement names
        names = set(m.get("measurement_name", "Unknown") for m in measurements)
        print(f"\nMEASUREMENT NAMES ({len(names)}):")
        for name in sorted(names):
            count = sum(1 for m in measurements if m.get("measurement_name") == name)
            print(f"  - {name}: {count} measurements")

        # Detailed inspection of first few
        print(
            f"\nDETAILED INSPECTION OF FIRST {min(max_to_show, len(measurements))} MEASUREMENTS:\n"
        )
        for i, measurement in enumerate(measurements[:max_to_show]):
            print(f"\n--- Measurement {i + 1} ---")
            UVVisDiagnosticHelper.inspect_measurement(measurement, verbose=False)

    @staticmethod
    def check_bandgaps_field_in_json(uvvis_data):
        """
        Check if bandgaps_uvvis field exists in raw API response

        Args:
            uvvis_data: Raw data from API (the 'data' part of the response)
        """
        print("\nCHECKING RAW UVVIS DATA STRUCTURE:")
        print(f"  Type: {type(uvvis_data)}")
        print(f"  Keys: {list(uvvis_data.keys()) if isinstance(uvvis_data, dict) else 'N/A'}")

        if "measurements" in uvvis_data:
            measurements = uvvis_data["measurements"]
            print(f"\n  Found 'measurements' key: {type(measurements)}, length={len(measurements)}")

            if len(measurements) > 0:
                first_meas = measurements[0]
                print(f"\n  First measurement keys: {list(first_meas.keys())}")

                # Check for bandgaps at this level
                if "bandgaps_uvvis" in first_meas:
                    print("  ✓ bandgaps_uvvis found in measurement!")
                    print(f"    Value: {first_meas['bandgaps_uvvis']}")
                    print(f"    Type: {type(first_meas['bandgaps_uvvis'])}")
                else:
                    print("  ✗ bandgaps_uvvis NOT in measurement")
                    print(f"    Available keys: {', '.join(first_meas.keys())}")

    @staticmethod
    def trace_bandgap_loading(sample_id, uvvis_data, metadata):
        """
        Trace how bandgaps are loaded from API response

        Args:
            sample_id: The sample ID being processed
            uvvis_data: The data dictionary from API
            metadata: The metadata from API
        """
        print(f"\n{'=' * 80}")
        print(f"TRACING BANDGAP LOADING FOR: {sample_id}")
        print(f"{'=' * 80}\n")

        print("1. UVVIS DATA STRUCTURE:")
        UVVisDiagnosticHelper.check_bandgaps_field_in_json(uvvis_data)

        print("\n2. PROCESSING MEASUREMENTS:")
        measurements = uvvis_data.get("measurements", [])
        for i, measurement in enumerate(measurements):
            print(f"\n   Measurement {i + 1}:")
            print(f"     Name: {measurement.get('name', 'N/A')}")

            # Check for bandgaps
            if "bandgaps_uvvis" in measurement:
                bandgaps = measurement["bandgaps_uvvis"]
                print(f"     ✓ bandgaps_uvvis: {bandgaps} (type: {type(bandgaps)})")
            else:
                print("     ✗ bandgaps_uvvis: NOT FOUND")
                print(f"       Keys in measurement: {list(measurement.keys())}")


# Function to create an interactive diagnostic cell
def create_diagnostic_output_widget(data_manager):
    """
    Create an ipywidgets output for diagnostics

    Args:
        data_manager: The UVVisDataManager instance
    """
    import ipywidgets as widgets
    from IPython.display import display

    if not data_manager.has_data():
        return widgets.HTML("<h3>No data available. Please load data first.</h3>")

    measurements = data_manager.get_data()["samples"]

    output = widgets.Output()

    with output:
        print("📊 UVVis DATA DIAGNOSTIC REPORT\n")
        UVVisDiagnosticHelper.inspect_all_measurements(measurements, max_to_show=2)

    return output
