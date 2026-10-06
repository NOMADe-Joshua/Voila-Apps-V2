"""
Data manager for AbsPL/PLQY analysis.
"""

import re

import numpy as np
import pandas as pd
from diagnostic_helper import debug_logger_abspl

from perotf_utils.api_calls import get_all_eqe, get_ids_in_batch, get_sample_description
from perotf_utils.config import ENTRY_TYPES


def extract_cycle_info(*texts):
    """Extract cycle identifier from description/filename text.

    Supports: Cycle_M, pxNCycle_M, or standalone cycle number.
    Returns: cycle_number (int or None)
    """
    combined_pattern = re.compile(r"px(?:\d+)?Cycle_(?P<cycle>\d+)", re.IGNORECASE)
    cycle_pattern = re.compile(r"Cycle_(?P<cycle>\d+)", re.IGNORECASE)

    cycle_number = None

    for text in texts:
        if not text:
            continue

        text_str = str(text)

        # Try combined pattern first
        combined_match = combined_pattern.search(text_str)
        if combined_match and cycle_number is None:
            cycle_number = int(combined_match.group("cycle"))
            continue

        # Try standalone cycle pattern
        if cycle_number is None:
            cycle_match = cycle_pattern.search(text_str)
            if cycle_match:
                cycle_number = int(cycle_match.group("cycle"))

    return cycle_number


def extract_description_notes(data_dict, metadata):
    """Extract description notes/comment text from entry payload and metadata."""
    candidates = [
        (metadata or {}).get("description_notes", ""),
        (metadata or {}).get("comment", ""),
        (metadata or {}).get("comments", ""),
        (metadata or {}).get("description", ""),
        (data_dict or {}).get("description_notes", ""),
        (data_dict or {}).get("comment", ""),
        (data_dict or {}).get("comments", ""),
        (data_dict or {}).get("notes", ""),
    ]

    for candidate in candidates:
        if candidate not in (None, ""):
            return str(candidate)
    return ""


class AbsPLDataManager:
    """Load, classify (PL vs sweep), and filter AbsPL data."""

    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.data = {
            "summary": pd.DataFrame(),
            "spectra": pd.DataFrame(),
            "filtered_summary": pd.DataFrame(),
            "filtered_spectra": pd.DataFrame(),
        }

    def _as_list(self, value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return []

    def _safe_float(self, value):
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _detect_measurement_type(self, results):
        # Rule from sweep_vs_PL.md:
        # - len(results) > 1 likely sweep
        # - single result with missing luminescence_flux_density treated as sweep fallback
        if len(results) > 1:
            return "sweep"
        if len(results) == 1:
            first = results[0]
            flux = first.get("luminescence_flux_density")
            raw = first.get("raw_spectrum_counts")
            if flux is None and raw is not None:
                return "sweep"
        return "pl"

    def _extract_spot_size(self, data_dict):
        settings = data_dict.get("settings", {}) if isinstance(data_dict, dict) else {}
        candidates = [
            settings.get("laser_spot_size"),
            data_dict.get("laser_spot_size") if isinstance(data_dict, dict) else None,
            settings.get("spot_size"),
            data_dict.get("spot_size") if isinstance(data_dict, dict) else None,
        ]
        for c in candidates:
            if c not in (None, "", "nan"):
                return str(c)
        return "Unknown"

    def load_batch_data(self, batch_ids):
        self.data = {
            "summary": pd.DataFrame(),
            "spectra": pd.DataFrame(),
            "filtered_summary": pd.DataFrame(),
            "filtered_spectra": pd.DataFrame(),
        }

        if not self.auth_manager.is_authenticated():
            raise RuntimeError("Not authenticated")

        if not batch_ids:
            raise ValueError("No batch selected")

        url = self.auth_manager.url
        token = self.auth_manager.current_token

        debug_logger_abspl.add("LOAD", f"Start loading {len(batch_ids)} batch(es)", level="INFO")

        sample_ids = get_ids_in_batch(url, token, batch_ids)
        if not sample_ids:
            debug_logger_abspl.add(
                "LOAD", "No sample IDs found in selected batches", level="WARNING"
            )
            return False

        descriptions = get_sample_description(url, token, list(sample_ids))
        abspl_entries = get_all_eqe(url, token, sample_ids, eqe_type=ENTRY_TYPES["abspl"])

        summary_rows = []
        spectra_rows = []

        for sample_id, entries in abspl_entries.items():
            sample_desc = descriptions.get(sample_id, "")
            for entry_idx, (data_dict, metadata) in enumerate(entries):
                results = data_dict.get("results", []) if isinstance(data_dict, dict) else []
                if not isinstance(results, list):
                    continue

                measurement_type = self._detect_measurement_type(results)
                entry_name = data_dict.get("name", metadata.get("entry_name", f"entry_{entry_idx}"))
                upload_name = metadata.get("upload_name", "unknown_upload")
                spot_size = self._extract_spot_size(data_dict)
                description_notes = extract_description_notes(data_dict, metadata)
                cycle_from_notes = extract_cycle_info(description_notes)

                settings = data_dict.get("settings", {}) if isinstance(data_dict, dict) else {}
                laser_intensity_default = settings.get("laser_intensity_suns", None)

                for i, result in enumerate(results):
                    # Cycle comes from Description Notes (e.g. "Cycle_N"), not from sweep sub-measurement index.
                    cycle_number = cycle_from_notes

                    wavelength = self._as_list(result.get("wavelength"))
                    lum_flux = self._as_list(result.get("luminescence_flux_density"))
                    raw_spec = self._as_list(result.get("raw_spectrum_counts"))

                    # Sweep data is stored in raw counts by source, but we expose it as flux-density channel
                    # to keep one unified plotting source for sweep traces.
                    if measurement_type == "sweep" and len(lum_flux) == 0 and len(raw_spec) > 0:
                        lum_flux = raw_spec

                    intensity = lum_flux if len(lum_flux) > 0 else raw_spec
                    y_source = (
                        "luminescence_flux_density" if len(lum_flux) > 0 else "raw_spectrum_counts"
                    )

                    if len(wavelength) == 0 or len(intensity) == 0:
                        continue

                    measurement_uid = (
                        f"{sample_id}|{metadata.get('entry_id', entry_idx)}|{entry_idx}|{i}"
                    )
                    cycle_int = int(cycle_number) if str(cycle_number).isdigit() else cycle_number

                    summary_rows.append(
                        {
                            "measurement_uid": measurement_uid,
                            "sample_id": sample_id,
                            "sample_description": sample_desc,
                            "batch": upload_name,
                            "condition": sample_desc if sample_desc else sample_id,
                            "entry_name": entry_name,
                            "description_notes": description_notes,
                            "measurement_type": measurement_type,
                            "cycle_number": cycle_int,
                            "laser_spot_size": spot_size,
                            "laser_intensity_suns": self._safe_float(
                                result.get("laser_intensity_suns", laser_intensity_default)
                            ),
                            "luminescence_quantum_yield": self._safe_float(
                                result.get("luminescence_quantum_yield")
                            ),
                            "quasi_fermi_level_splitting": self._safe_float(
                                result.get("quasi_fermi_level_splitting")
                            ),
                            "quasi_fermi_level_splitting_het": self._safe_float(
                                result.get("quasi_fermi_level_splitting_het")
                            ),
                            "i_voc": self._safe_float(result.get("i_voc")),
                            "bandgap": self._safe_float(result.get("bandgap")),
                            "derived_jsc": self._safe_float(result.get("derived_jsc")),
                            "spectrum_points": min(len(wavelength), len(intensity)),
                            "spectrum_source": y_source,
                        }
                    )

                    spectra_rows.append(
                        {
                            "measurement_uid": measurement_uid,
                            "sample_id": sample_id,
                            "condition": sample_desc if sample_desc else sample_id,
                            "batch": upload_name,
                            "entry_name": entry_name,
                            "description_notes": description_notes,
                            "measurement_type": measurement_type,
                            "cycle_number": cycle_int,
                            "laser_spot_size": spot_size,
                            "laser_intensity_suns": self._safe_float(
                                result.get("laser_intensity_suns", laser_intensity_default)
                            ),
                            "wavelength": wavelength,
                            "luminescence_flux_density": lum_flux,
                            "raw_spectrum_counts": raw_spec,
                            "intensity": intensity,
                            "spectrum_source": y_source,
                        }
                    )

        summary_df = pd.DataFrame(summary_rows)
        spectra_df = pd.DataFrame(spectra_rows)

        if summary_df.empty or spectra_df.empty:
            debug_logger_abspl.add(
                "LOAD", "No AbsPL results found for selected batches", level="WARNING"
            )
            return False

        self.data["summary"] = summary_df
        self.data["spectra"] = spectra_df
        self.data["filtered_summary"] = summary_df.copy()
        self.data["filtered_spectra"] = spectra_df.copy()

        n_pl = int((summary_df["measurement_type"] == "pl").sum())
        n_sweep = int((summary_df["measurement_type"] == "sweep").sum())
        debug_logger_abspl.add(
            "LOAD",
            f"Loaded {len(summary_df)} measurements ({n_pl} PL, {n_sweep} Sweep) from {summary_df['sample_id'].nunique()} samples",
            level="SUCCESS",
        )
        return True

    def apply_filters(self, filter_config):
        summary_df = self.data.get("summary", pd.DataFrame()).copy()
        spectra_df = self.data.get("spectra", pd.DataFrame()).copy()

        if summary_df.empty:
            self.data["filtered_summary"] = pd.DataFrame()
            self.data["filtered_spectra"] = pd.DataFrame()
            return pd.DataFrame(), pd.DataFrame()

        row_filters = filter_config.get("row_filters", [])

        def _is_all(value):
            return value in (None, "", "__all__")

        effective_filters = []
        for row in row_filters:
            sample = row.get("sample")
            mtype = row.get("measurement_type")
            spot = row.get("laser_spot_size")
            cycle = row.get("cycle")
            if _is_all(sample) and _is_all(mtype) and _is_all(spot) and _is_all(cycle):
                continue
            effective_filters.append(row)

        if effective_filters:
            summary_df = summary_df.copy()
            cycle_series = pd.to_numeric(summary_df["cycle_number"], errors="coerce")
            mask = pd.Series(False, index=summary_df.index)

            for row in effective_filters:
                row_mask = pd.Series(True, index=summary_df.index)

                sample = row.get("sample")
                if not _is_all(sample):
                    row_mask &= summary_df["sample_id"].astype(str) == str(sample)

                mtype = row.get("measurement_type")
                if not _is_all(mtype):
                    row_mask &= summary_df["measurement_type"].astype(str) == str(mtype)

                spot = row.get("laser_spot_size")
                if not _is_all(spot):
                    row_mask &= summary_df["laser_spot_size"].astype(str) == str(spot)

                cycle = row.get("cycle")
                if not _is_all(cycle):
                    try:
                        cycle_int = int(cycle)
                        row_mask &= cycle_series == cycle_int
                    except Exception:
                        row_mask &= False

                mask |= row_mask

            summary_df = summary_df[mask]

        allowed = set(summary_df["measurement_uid"].tolist())
        spectra_df = spectra_df[spectra_df["measurement_uid"].isin(allowed)].copy()

        self.data["filtered_summary"] = summary_df
        self.data["filtered_spectra"] = spectra_df

        debug_logger_abspl.add(
            "FILTER",
            f"Filtered to {len(summary_df)} measurements ({summary_df['sample_id'].nunique() if not summary_df.empty else 0} samples)",
            level="SUCCESS" if len(summary_df) else "WARNING",
        )
        return summary_df, spectra_df

    def get_data(self):
        return self.data

    def get_filtered_data(self):
        return self.data.get("filtered_summary", pd.DataFrame()), self.data.get(
            "filtered_spectra", pd.DataFrame()
        )

    def get_filter_options(self):
        summary = self.data.get("summary", pd.DataFrame())
        spectra_all = self.data.get("spectra", pd.DataFrame())
        if summary.empty:
            return {
                "measurement_types": [],
                "samples": [],
                "laser_spot_sizes": [],
                "cycles": [],
                "filter_rows": [],
                "numeric_columns": [],
                "fit_curve_options": [],
            }

        numeric_columns = [
            c
            for c in [
                "luminescence_quantum_yield",
                "quasi_fermi_level_splitting",
                "quasi_fermi_level_splitting_het",
                "i_voc",
                "bandgap",
                "derived_jsc",
                "laser_intensity_suns",
                "cycle_number",
            ]
            if c in summary.columns
        ]

        filter_rows = summary[
            ["sample_id", "measurement_type", "laser_spot_size", "cycle_number"]
        ].copy()
        filter_rows["cycle_number"] = pd.to_numeric(filter_rows["cycle_number"], errors="coerce")
        filter_rows = (
            filter_rows.dropna(
                subset=["sample_id", "measurement_type", "laser_spot_size", "cycle_number"]
            )
            .assign(cycle_number=lambda df: df["cycle_number"].astype(int))
            .drop_duplicates()
        )

        cycles = (
            pd.to_numeric(summary["cycle_number"], errors="coerce")
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )

        n_samples = int(summary["sample_id"].nunique()) if "sample_id" in summary.columns else 0
        sweep_rows = summary[summary["measurement_type"].astype(str) == "sweep"].copy()
        if sweep_rows.empty:
            max_sweep_points_per_file = 0
            n_sweep_measurements = 0
        else:
            key_cols = [
                c
                for c in ["sample_id", "batch", "entry_name", "cycle_number"]
                if c in sweep_rows.columns
            ]
            grouped_sizes = (
                sweep_rows.groupby(key_cols).size() if key_cols else pd.Series([len(sweep_rows)])
            )
            max_sweep_points_per_file = int(grouped_sizes.max()) if len(grouped_sizes) else 0
            n_sweep_measurements = int(len(grouped_sizes)) if len(grouped_sizes) else 0

        max_required_colors = max(2, n_samples, max_sweep_points_per_file, n_sweep_measurements)

        fit_curve_options = []
        spectra_for_options = (
            spectra_all if isinstance(spectra_all, pd.DataFrame) else pd.DataFrame()
        )
        if not spectra_for_options.empty and "measurement_uid" in spectra_for_options.columns:
            cols = [
                c
                for c in [
                    "measurement_uid",
                    "measurement_type",
                    "sample_id",
                    "cycle_number",
                    "laser_intensity_suns",
                ]
                if c in spectra_for_options.columns
            ]
            curves_df = (
                spectra_for_options[cols]
                .dropna(subset=["measurement_uid"])
                .drop_duplicates(subset=["measurement_uid"])
            )
            for _, row in curves_df.iterrows():
                uid = str(row.get("measurement_uid"))
                mtype = str(row.get("measurement_type", "")).strip()
                sample = str(row.get("sample_id", "")).strip()
                cycle_val = pd.to_numeric(row.get("cycle_number"), errors="coerce")
                cycle_text = f"C{int(cycle_val)}" if np.isfinite(cycle_val) else "C?"
                suns_val = pd.to_numeric(row.get("laser_intensity_suns"), errors="coerce")
                suns_text = f"{suns_val:.4g} sun" if np.isfinite(suns_val) else "n/a sun"
                label = f"{mtype} | {sample} | {cycle_text} | {suns_text}"
                fit_curve_options.append({"label": label, "value": uid})

        return {
            "measurement_types": sorted(
                summary["measurement_type"].dropna().astype(str).unique().tolist()
            ),
            "samples": sorted(summary["sample_id"].dropna().astype(str).unique().tolist()),
            "laser_spot_sizes": sorted(
                summary["laser_spot_size"].dropna().astype(str).unique().tolist()
            ),
            "cycles": sorted(cycles),
            "filter_rows": filter_rows.to_dict("records"),
            "numeric_columns": numeric_columns,
            "max_required_colors": max_required_colors,
            "fit_curve_options": fit_curve_options,
        }
