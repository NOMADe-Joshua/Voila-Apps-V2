"""
Data manager for EQE curve analysis.
"""

import operator
import re

import numpy as np
import pandas as pd
import requests

from perotf_utils.api_calls import get_all_eqe, get_ids_in_batch, get_sample_description
from perotf_utils.config import ENTRY_TYPES

API_SOURCE = "perotf_utils.api_calls"


class DataManagerEQE:
    """Load, normalize, filter, and expose EQE data for plotting."""

    PARAM_COLUMNS = [
        "multijunction_position",
        "light_bias",
        "bandgap_eqe",
        "integrated_jsc",
        "integrated_j0rad",
        "voc_rad",
        "urbach_energy",
        "urbach_energy_fit_std_dev",
    ]

    FILTERABLE_COLUMNS = [
        "bandgap_eqe",
        "integrated_jsc",
        "integrated_j0rad",
        "voc_rad",
        "urbach_energy",
        "light_bias",
    ]

    KEY_COLUMNS = ["sample_id", "entry_idx", "measurement_idx"]

    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.data = {}
        self.unique_vals = []
        self.filtered_params = None
        self.filtered_curves = None
        self.omitted_params = None
        self.filter_parameters = []
        self.last_diagnostics = {}

    def load_batch_data(self, batch_ids, output_widget=None):
        """Load EQE data for selected batches and normalize into DataFrames."""
        self.data = {}
        self.last_diagnostics = {
            "batch_count": len(batch_ids or []),
            "api_source": API_SOURCE,
            "sample_ids_total": 0,
            "sample_ids_unique": 0,
            "sample_ids_preview": [],
            "inferred_sample_ids_outside_batch": [],
            "eqe_samples_found": 0,
            "total_entries": 0,
            "entries_without_eqe_data": 0,
            "entry_names_preview": [],
            "total_measurements_seen": 0,
            "parsed_measurements": 0,
            "dropped_measurements": 0,
            "dropped_reasons": {},
            "entry_types_detected": [],
        }

        if not self.auth_manager.is_authenticated():
            raise RuntimeError("Not authenticated. Please login first.")
        if not batch_ids:
            raise ValueError("No batch IDs selected.")

        sample_ids = get_ids_in_batch(
            self.auth_manager.url, self.auth_manager.current_token, batch_ids
        )
        sample_ids = list(sample_ids)
        self.last_diagnostics["sample_ids_total"] = len(sample_ids)
        self.last_diagnostics["sample_ids_unique"] = len(set(sample_ids))
        self.last_diagnostics["sample_ids_preview"] = sorted(set(sample_ids))[:10]

        if not sample_ids:
            self.data["params"] = pd.DataFrame()
            self.data["curves"] = pd.DataFrame()
            self.data["sample_ids"] = pd.Series(dtype=object)
            self.data["properties"] = pd.DataFrame(columns=["description", "name", "include"])
            return self.data

        all_eqe_default = get_all_eqe(
            self.auth_manager.url, self.auth_manager.current_token, sample_ids
        )
        all_eqe_gamma = get_all_eqe(
            self.auth_manager.url,
            self.auth_manager.current_token,
            sample_ids,
            eqe_type=ENTRY_TYPES["eqe_tfl_gammabox"],
        )
        self.last_diagnostics["strategy1_default_samples"] = len(all_eqe_default or {})
        self.last_diagnostics["strategy1_gamma_samples"] = len(all_eqe_gamma or {})

        all_eqe = {}
        seen_entry_ids = set()
        for src in (all_eqe_default, all_eqe_gamma):
            for sid, entries in (src or {}).items():
                for entry_pack in entries:
                    eid = (
                        entry_pack[1].get("entry_id")
                        if isinstance(entry_pack, (list, tuple)) and len(entry_pack) > 1
                        else None
                    )
                    if eid and eid in seen_entry_ids:
                        continue
                    if eid:
                        seen_entry_ids.add(eid)
                    all_eqe.setdefault(sid, []).append(entry_pack)

        # Fallback 1: direct lookup via results.eln.lab_ids + entry_type.
        strat2_found = 0
        for eqe_type in (ENTRY_TYPES["eqe"], ENTRY_TYPES["eqe_tfl_gammabox"]):
            direct_query = {
                "required": {"data": "*", "metadata": "*"},
                "owner": "visible",
                "query": {
                    "results.eln.lab_ids:any": list(sample_ids),
                    "entry_type": eqe_type,
                },
                "pagination": {"page_size": 10000},
            }
            direct_resp = requests.post(
                f"{self.auth_manager.url}/entries/archive/query",
                headers={"Authorization": f"Bearer {self.auth_manager.current_token}"},
                json=direct_query,
            )
            self.last_diagnostics.setdefault("strategy2_http_status", {})[eqe_type] = (
                direct_resp.status_code
            )
            if direct_resp.status_code != 200:
                continue
            raw = direct_resp.json().get("data", [])
            self.last_diagnostics.setdefault("strategy2_raw_count", {})[eqe_type] = len(raw)
            for ldata in raw:
                try:
                    eid = ldata["archive"]["metadata"].get("entry_id")
                    if eid and eid in seen_entry_ids:
                        continue
                    if eid:
                        seen_entry_ids.add(eid)
                    lab_id = ldata["archive"]["data"]["samples"][0]["lab_id"]
                    all_eqe.setdefault(lab_id, []).append(
                        (ldata["archive"]["data"], ldata["archive"]["metadata"])
                    )
                    strat2_found += 1
                except (KeyError, IndexError, TypeError) as exc:
                    self.last_diagnostics.setdefault("strategy2_parse_errors", []).append(str(exc))
        self.last_diagnostics["strategy2_new_entries"] = strat2_found

        # Fallback 2: search by upload_id of the batch entries.
        strat3_found = 0
        strat3_upload_ids = []
        try:
            upload_query = {
                "required": {"metadata": {"upload_id": "*"}},
                "owner": "visible",
                "query": {
                    "results.eln.lab_ids:any": list(batch_ids),
                    "entry_type": ENTRY_TYPES["batch"],
                },
                "pagination": {"page_size": 100},
            }
            upload_resp = requests.post(
                f"{self.auth_manager.url}/entries/query",
                headers={"Authorization": f"Bearer {self.auth_manager.current_token}"},
                json=upload_query,
            )
            self.last_diagnostics["strategy3_batch_http_status"] = upload_resp.status_code
            if upload_resp.status_code == 200:
                strat3_upload_ids = list(
                    {
                        e["upload_id"]
                        for e in upload_resp.json().get("data", [])
                        if e.get("upload_id")
                    }
                )
                self.last_diagnostics["strategy3_upload_ids"] = strat3_upload_ids
                if strat3_upload_ids:
                    for eqe_type in (ENTRY_TYPES["eqe"], ENTRY_TYPES["eqe_tfl_gammabox"]):
                        upload_eqe_query = {
                            "required": {"data": "*", "metadata": "*"},
                            "owner": "visible",
                            "query": {"upload_id:any": strat3_upload_ids, "entry_type": eqe_type},
                            "pagination": {"page_size": 10000},
                        }
                        ueqe_resp = requests.post(
                            f"{self.auth_manager.url}/entries/archive/query",
                            headers={"Authorization": f"Bearer {self.auth_manager.current_token}"},
                            json=upload_eqe_query,
                        )
                        self.last_diagnostics.setdefault("strategy3_http_status", {})[eqe_type] = (
                            ueqe_resp.status_code
                        )
                        if ueqe_resp.status_code != 200:
                            continue
                        raw3 = ueqe_resp.json().get("data", [])
                        self.last_diagnostics.setdefault("strategy3_raw_count", {})[eqe_type] = len(
                            raw3
                        )
                        for ldata in raw3:
                            try:
                                eid = ldata["archive"]["metadata"].get("entry_id")
                                if eid and eid in seen_entry_ids:
                                    continue
                                if eid:
                                    seen_entry_ids.add(eid)
                                # Try samples key first; fall back to matching entry name against known IDs
                                lab_id = None
                                try:
                                    lab_id = ldata["archive"]["data"]["samples"][0]["lab_id"]
                                except (KeyError, IndexError, TypeError):
                                    entry_name = (
                                        ldata["archive"]["metadata"].get("entry_name", "") or ""
                                    )
                                    mainfile = (
                                        ldata["archive"]["metadata"].get("mainfile", "") or ""
                                    )
                                    for sid in sample_ids:
                                        if (
                                            entry_name.startswith(sid)
                                            or mainfile.startswith(sid)
                                            or (sid + " ") in entry_name
                                        ):
                                            lab_id = sid
                                            break
                                if lab_id is None or lab_id not in sample_ids:
                                    continue
                                all_eqe.setdefault(lab_id, []).append(
                                    (ldata["archive"]["data"], ldata["archive"]["metadata"])
                                )
                                strat3_found += 1
                            except (KeyError, IndexError, TypeError) as exc:
                                self.last_diagnostics.setdefault(
                                    "strategy3_parse_errors", []
                                ).append(str(exc))
        except Exception as exc:
            self.last_diagnostics["strategy3_exception"] = str(exc)
        self.last_diagnostics["strategy3_new_entries"] = strat3_found

        selected_sample_set = set(sample_ids)
        inferred_outside = sorted([sid for sid in all_eqe.keys() if sid not in selected_sample_set])
        self.last_diagnostics["inferred_sample_ids_outside_batch"] = inferred_outside[:20]
        self.last_diagnostics["eqe_samples_found"] = len(all_eqe)

        # Inspect the first few entries to understand data structure
        entry_structure_sample = []
        for sid, entries in list(all_eqe.items())[:3]:
            for entry_pack in entries[:2]:
                edata = (
                    entry_pack[0] if isinstance(entry_pack, (list, tuple)) and entry_pack else {}
                )
                emeta = (
                    entry_pack[1]
                    if isinstance(entry_pack, (list, tuple)) and len(entry_pack) > 1
                    else {}
                )
                top_keys = sorted(edata.keys()) if isinstance(edata, dict) else []
                has_eqe_data = "eqe_data" in edata
                eqe_data_val = edata.get("eqe_data")
                eqe_data_type = type(eqe_data_val).__name__
                eqe_data_len = (
                    len(eqe_data_val)
                    if isinstance(eqe_data_val, (list, tuple, np.ndarray))
                    else "N/A"
                )
                entry_structure_sample.append(
                    {
                        "sample_id": sid,
                        "entry_type": emeta.get("entry_type", "?"),
                        "mainfile": emeta.get("mainfile", "?"),
                        "top_level_keys": top_keys[:15],
                        "has_eqe_data_key": has_eqe_data,
                        "eqe_data_type": eqe_data_type,
                        "eqe_data_len": eqe_data_len,
                    }
                )
        self.last_diagnostics["entry_structure_sample"] = entry_structure_sample

        params_rows = []
        curve_frames = []
        entry_types_detected = set()
        entry_names_preview = []

        for sample_id, eqe_entries in all_eqe.items():
            self.last_diagnostics["total_entries"] += len(eqe_entries)
            for entry_idx, entry_pack in enumerate(eqe_entries):
                entry_data = (
                    entry_pack[0] if isinstance(entry_pack, (list, tuple)) and entry_pack else {}
                )
                metadata = (
                    entry_pack[1]
                    if isinstance(entry_pack, (list, tuple)) and len(entry_pack) > 1
                    else {}
                )
                etype = metadata.get("entry_type") if isinstance(metadata, dict) else None
                if etype:
                    entry_types_detected.add(str(etype))

                entry_name = str(
                    entry_data.get("name")
                    or metadata.get("entry_name")
                    or metadata.get("mainfile")
                    or f"EQE Entry {entry_idx + 1}"
                )
                if len(entry_names_preview) < 15:
                    entry_names_preview.append(entry_name)

                mainfile = str(metadata.get("mainfile", ""))
                pixel, cycle = self._extract_pixel_cycle(entry_name, mainfile)
                entry_position = self._normalize_multijunction_position(
                    entry_data.get("multijunction_position")
                )

                eqe_data = entry_data.get("eqe_data", [])
                if not isinstance(eqe_data, (list, tuple, np.ndarray)):
                    eqe_data = []
                # Flat format: GammaBox entries store curves directly in the entry root
                # (keys like eqe_array, wavelength_array at top level, no eqe_data list)
                if len(eqe_data) == 0 and isinstance(entry_data, dict):
                    if (
                        entry_data.get("eqe_array") is not None
                        or entry_data.get("wavelength_array") is not None
                    ):
                        eqe_data = [entry_data]  # entry itself is the single measurement
                        self.last_diagnostics["entries_as_flat_measurement"] = (
                            self.last_diagnostics.get("entries_as_flat_measurement", 0) + 1
                        )
                if len(eqe_data) == 0:
                    self.last_diagnostics["entries_without_eqe_data"] += 1

                # Store first measurement structure for diagnostics
                if eqe_data and "first_measurement_type" not in self.last_diagnostics:
                    m0 = eqe_data[0]
                    if isinstance(m0, dict):
                        self.last_diagnostics["first_measurement_type"] = "dict"
                        self.last_diagnostics["first_measurement_keys"] = sorted(m0.keys())[:20]
                        # Show types of values
                        self.last_diagnostics["first_measurement_value_types"] = {
                            k: type(v).__name__
                            + (f"[{len(v)}]" if isinstance(v, (list, np.ndarray)) else "")
                            for k, v in list(m0.items())[:10]
                        }
                    else:
                        self.last_diagnostics["first_measurement_type"] = type(m0).__name__

                for measurement_idx, measurement in enumerate(eqe_data):
                    self.last_diagnostics["total_measurements_seen"] += 1
                    param_values = self._extract_param_values(measurement)
                    measurement_position = self._normalize_multijunction_position(
                        param_values.get("multijunction_position")
                    )
                    param_values["multijunction_position"] = (
                        measurement_position or entry_position or ""
                    )
                    curve_df = self._extract_curve_df(measurement)
                    if curve_df is None or curve_df.empty:
                        self.last_diagnostics["dropped_measurements"] += 1
                        reason = self._classify_drop_reason(measurement)
                        dropped_reasons = self.last_diagnostics["dropped_reasons"]
                        dropped_reasons[reason] = dropped_reasons.get(reason, 0) + 1
                        continue

                    params_row = {
                        "sample_id": sample_id,
                        "entry_idx": int(entry_idx),
                        "measurement_idx": int(measurement_idx),
                        "entry_name": entry_name,
                        "curve_name": f"{entry_name} {measurement_idx + 1}",
                        "pixel": pixel,
                        "cycle": cycle,
                        "plot": True,
                    }
                    params_row.update(param_values)
                    params_rows.append(params_row)

                    curve_df = curve_df.copy()
                    curve_df["sample_id"] = sample_id
                    curve_df["entry_idx"] = int(entry_idx)
                    curve_df["measurement_idx"] = int(measurement_idx)
                    curve_frames.append(curve_df)
                    self.last_diagnostics["parsed_measurements"] += 1

        if output_widget is not None:
            with output_widget:
                print(
                    "Diagnostic snapshot: "
                    f"samples={self.last_diagnostics['sample_ids_total']} "
                    f"eqe_samples={self.last_diagnostics['eqe_samples_found']} "
                    f"entries={self.last_diagnostics['total_entries']} "
                    f"measurements={self.last_diagnostics['total_measurements_seen']} "
                    f"parsed={self.last_diagnostics['parsed_measurements']} "
                    f"dropped={self.last_diagnostics['dropped_measurements']}"
                )

        self.last_diagnostics["entry_types_detected"] = sorted(entry_types_detected)
        self.last_diagnostics["entry_names_preview"] = entry_names_preview

        if not params_rows or not curve_frames:
            self.data["params"] = pd.DataFrame()
            self.data["curves"] = pd.DataFrame()
            self.data["sample_ids"] = pd.Series(dtype=object)
            self.data["properties"] = pd.DataFrame(columns=["description", "name", "include"])
            return self.data

        params_df = pd.DataFrame(params_rows)
        _STRING_PARAM_COLUMNS = {"multijunction_position"}
        for col in self.PARAM_COLUMNS:
            if col in params_df.columns and col not in _STRING_PARAM_COLUMNS:
                params_df[col] = pd.to_numeric(params_df[col], errors="coerce")

        curves_df = pd.concat(curve_frames, ignore_index=True)
        # Explode any rows where the arrays were stored as lists (legacy flat format)
        for col in ["wavelength_array", "photon_energy_array", "eqe_array"]:
            if (
                col in curves_df.columns
                and curves_df[col].apply(lambda v: isinstance(v, (list, np.ndarray))).any()
            ):
                curves_df = curves_df.explode(col)
        curves_df["wavelength_array"] = pd.to_numeric(
            curves_df["wavelength_array"], errors="coerce"
        )
        curves_df["photon_energy_array"] = pd.to_numeric(
            curves_df["photon_energy_array"], errors="coerce"
        )
        curves_df["eqe_array"] = pd.to_numeric(curves_df["eqe_array"], errors="coerce")
        curves_df = curves_df.dropna(subset=["eqe_array"])

        ordered_sample_ids = list(dict.fromkeys(params_df["sample_id"].dropna().tolist()))

        sample_description = get_sample_description(
            self.auth_manager.url,
            self.auth_manager.current_token,
            ordered_sample_ids,
        )

        properties_df = pd.DataFrame(
            {
                "description": pd.Series(sample_description),
                "name": pd.Series(sample_description),
            }
        )
        properties_df.index.name = "sample_id"
        properties_df = properties_df.reindex(ordered_sample_ids)
        properties_df["description"] = properties_df["description"].fillna("")
        default_names = pd.Series(properties_df.index, index=properties_df.index)
        properties_df["name"] = properties_df["name"].fillna(default_names)
        properties_df["include"] = True

        self.data["params"] = params_df
        self.data["curves"] = curves_df
        self.data["sample_ids"] = pd.Series(ordered_sample_ids)
        self.data["properties"] = properties_df

        self._find_unique_values()
        return self.data

    def _classify_drop_reason(self, measurement):
        if measurement is None:
            return "measurement_none"
        if isinstance(measurement, dict):
            return "dict_missing_or_empty_curve_arrays"
        if isinstance(measurement, np.ndarray):
            arr = np.asarray(measurement)
            return f"ndarray_unsupported_shape_{arr.shape}"
        if isinstance(measurement, (list, tuple)):
            return "list_tuple_unsupported_curve_structure"
        return f"unsupported_type_{type(measurement).__name__}"

    def _extract_pixel_cycle(self, entry_name, mainfile):
        text = f"{entry_name} {mainfile}".lower()

        pixel_match = re.search(r"px\s*(\d+)", text)
        cycle_match = re.search(r"cycle\s*_?\s*(\d+)", text)

        pixel = int(pixel_match.group(1)) if pixel_match else np.nan
        cycle = int(cycle_match.group(1)) if cycle_match else np.nan
        return pixel, cycle

    def get_last_diagnostics(self):
        return dict(self.last_diagnostics)

    def _extract_param_values(self, measurement):
        values = {}
        if isinstance(measurement, dict):
            for col in self.PARAM_COLUMNS:
                v = measurement.get(col)
                # Skip values that are arrays/lists — those are curve data, not scalars
                if isinstance(v, (list, tuple, np.ndarray)):
                    v = np.nan
                values[col] = v
            return values

        if isinstance(measurement, (list, tuple)):
            # Legacy structure: [photon_energy_array, wavelength_array, eqe_array, light_bias, ...]
            # The first 3 elements are the curve arrays; params start at index 3
            # But PARAM_COLUMNS[0] is multijunction_position, not light_bias — skip index 0
            # Map: light_bias=idx3, bandgap_eqe=idx4, ...
            param_start = 3
            for idx, col in enumerate(self.PARAM_COLUMNS):
                list_idx = param_start + idx
                values[col] = measurement[list_idx] if len(measurement) > list_idx else np.nan
            return values

        for col in self.PARAM_COLUMNS:
            values[col] = np.nan
        return values

    def _normalize_multijunction_position(self, value):
        if value is None:
            return ""
        text = str(value).strip().lower()
        if text in {"", "none", "nan"}:
            return ""
        if text == "middle":
            return "mid"
        if text in {"top", "mid", "bottom"}:
            return text
        return text

    def _extract_curve_df(self, measurement):
        if isinstance(measurement, np.ndarray):
            arr = np.asarray(measurement)

            # Common format: N x 3 columns [photon_energy, wavelength, eqe]
            if arr.ndim == 2 and arr.shape[1] >= 3:
                return pd.DataFrame(
                    {
                        "photon_energy_array": arr[:, 0],
                        "wavelength_array": arr[:, 1],
                        "eqe_array": arr[:, 2],
                    }
                )

            # Transposed: 3 x N
            if arr.ndim == 2 and arr.shape[0] >= 3:
                return pd.DataFrame(
                    {
                        "photon_energy_array": arr[0, :],
                        "wavelength_array": arr[1, :],
                        "eqe_array": arr[2, :],
                    }
                )

            return None

        if isinstance(measurement, dict):
            wl = measurement.get("wavelength_array", [])
            pe = measurement.get("photon_energy_array", [])
            eqe = measurement.get("eqe_array", [])

            # Flatten to list regardless of whether values are lists, numpy arrays, or scalars
            def _to_list(v):
                if isinstance(v, (list, tuple)):
                    return list(v)
                if isinstance(v, np.ndarray):
                    return v.flatten().tolist()
                return []

            wl_list = _to_list(wl)
            pe_list = _to_list(pe)
            eqe_list = _to_list(eqe)

            if not wl_list and not eqe_list:
                return None
            n = max(len(wl_list), len(pe_list), len(eqe_list))
            if n == 0:
                return None
            if not wl_list:
                wl_list = [np.nan] * n
            if not pe_list:
                pe_list = [np.nan] * n
            if not eqe_list:
                eqe_list = [np.nan] * n

            return pd.DataFrame(
                {
                    "wavelength_array": wl_list,
                    "photon_energy_array": pe_list,
                    "eqe_array": eqe_list,
                }
            )

        if isinstance(measurement, (list, tuple)):
            # Format where first 3 elements are the curve arrays
            if len(measurement) >= 3 and isinstance(measurement[0], (list, tuple, np.ndarray)):
                return pd.DataFrame(
                    {
                        "photon_energy_array": list(measurement[0]),
                        "wavelength_array": list(measurement[1]),
                        "eqe_array": list(measurement[2]),
                    }
                )

            # List-of-triplets point structure: [[pe, wl, eqe], ...]
            if (
                measurement
                and isinstance(measurement[0], (list, tuple))
                and len(measurement[0]) >= 3
            ):
                return pd.DataFrame(
                    measurement,
                    columns=["photon_energy_array", "wavelength_array", "eqe_array"],
                )

        return None

    def apply_sample_mapping(self, mapping_dict, include_dict=None):
        """Apply user-defined sample display names and include flags."""
        if "properties" not in self.data:
            return

        props = self.data["properties"].copy()
        for sample_id, new_name in mapping_dict.items():
            if sample_id in props.index:
                props.loc[sample_id, "name"] = str(new_name).strip() or sample_id

        if include_dict:
            for sample_id, include in include_dict.items():
                if sample_id in props.index:
                    props.loc[sample_id, "include"] = bool(include)

        self.data["properties"] = props

    def apply_filters(
        self,
        filter_list=None,
        selected_sample_ids=None,
        wavelength_min=None,
        wavelength_max=None,
        cycle_mode="best",
        selected_cycles=None,
    ):
        """Apply param/sample filters and generate matching filtered curves."""
        if not self.data or "params" not in self.data:
            return pd.DataFrame(), pd.DataFrame(), []

        params = self.data["params"].copy()
        if params.empty:
            return params, pd.DataFrame(), []

        params["filter_reason"] = ""
        reasons = []
        operat = {
            "<": operator.lt,
            ">": operator.gt,
            "==": operator.eq,
            "<=": operator.le,
            ">=": operator.ge,
            "!=": operator.ne,
        }

        if selected_sample_ids:
            selected_set = set(selected_sample_ids)
            sample_mask = params["sample_id"].isin(selected_set)
            filtered_count = int((~sample_mask).sum())
            if filtered_count > 0:
                params.loc[~sample_mask, "filter_reason"] += "sample not selected, "
                reasons.append(f"sample selection ({filtered_count} filtered)")

        if filter_list:
            for col, op, val in filter_list:
                if col not in params.columns or op not in operat:
                    continue
                try:
                    val_num = float(val)
                except (TypeError, ValueError):
                    continue

                series = pd.to_numeric(params[col], errors="coerce")
                valid = series.notna()
                mask = pd.Series(False, index=params.index)
                mask.loc[valid] = operat[op](series.loc[valid], val_num)
                before_count = int((params["filter_reason"] == "").sum())
                params.loc[~mask, "filter_reason"] += f"{col} {op} {val_num}, "
                after_count = int((params["filter_reason"] == "").sum())
                diff = before_count - after_count
                if diff > 0:
                    reasons.append(f"{col} {op} {val_num} ({diff} filtered)")

        # --- Cycle filter (applied only to rows that haven't been filtered out yet) ---
        has_cycles = "cycle" in params.columns
        if has_cycles:
            cycle_vals = params.loc[params["filter_reason"] == "", "cycle"].dropna().unique()
        else:
            cycle_vals = []

        if has_cycles and len(cycle_vals) > 1:
            # We operate only on the currently-passing rows to avoid interfering with other filters.
            passing_mask = params["filter_reason"] == ""
            passing = params[passing_mask].copy()

            if cycle_mode == "best":
                # --- Separate SJ and MJ rows ---
                has_pos = "multijunction_position" in passing.columns
                if has_pos:
                    mj_mask = (
                        passing["multijunction_position"].fillna("").astype(str).str.strip().ne("")
                    )
                else:
                    mj_mask = pd.Series(False, index=passing.index)

                sj_passing = passing[~mj_mask]
                mj_passing = passing[mj_mask]

                removed_idx = []

                # SJ: group by (sample_id, pixel), keep the row with highest integrated_jsc per group
                if not sj_passing.empty:
                    pixel_str_sj = (
                        sj_passing["pixel"].fillna("").astype(str)
                        if "pixel" in sj_passing.columns
                        else pd.Series("", index=sj_passing.index)
                    )
                    sj_passing = sj_passing.copy()
                    sj_passing["_grp"] = sj_passing["sample_id"].astype(str) + "||" + pixel_str_sj
                    if "integrated_jsc" in sj_passing.columns:
                        sj_passing["_metric"] = pd.to_numeric(
                            sj_passing["integrated_jsc"], errors="coerce"
                        ).fillna(-np.inf)
                    else:
                        sj_passing["_metric"] = 0.0
                    best_sj_idx = sj_passing.groupby("_grp")["_metric"].idxmax()
                    removed_idx.extend(sj_passing.index.difference(best_sj_idx).tolist())

                # MJ: for each (sample_id, pixel) group, find the best top sub-cell,
                # then keep ALL sub-cells sharing the same (sample_id, pixel, cycle).
                if not mj_passing.empty:
                    pixel_str_mj = (
                        mj_passing["pixel"].fillna("__nan__").astype(str)
                        if "pixel" in mj_passing.columns
                        else pd.Series("__nan__", index=mj_passing.index)
                    )
                    cycle_str_mj = (
                        mj_passing["cycle"].fillna("__nan__").astype(str)
                        if "cycle" in mj_passing.columns
                        else pd.Series("__nan__", index=mj_passing.index)
                    )
                    mj_passing = mj_passing.copy()
                    mj_passing["_dev_grp"] = (
                        mj_passing["sample_id"].astype(str) + "||" + pixel_str_mj
                    )
                    mj_passing["_dev_cycle"] = mj_passing["_dev_grp"] + "||" + cycle_str_mj

                    if "integrated_jsc" in mj_passing.columns:
                        mj_passing["_metric"] = pd.to_numeric(
                            mj_passing["integrated_jsc"], errors="coerce"
                        ).fillna(-np.inf)
                    else:
                        mj_passing["_metric"] = 0.0

                    # For each (sample_id, pixel) group pick the best top sub-cell;
                    # fall back to any sub-cell if no "top" exists.
                    keep_device_cycles = set()
                    for grp_key, grp in mj_passing.groupby("_dev_grp"):
                        top_rows = grp[
                            grp["multijunction_position"].fillna("").astype(str).str.strip()
                            == "top"
                        ]
                        candidate = top_rows if not top_rows.empty else grp
                        best_row = candidate.loc[candidate["_metric"].idxmax()]
                        keep_device_cycles.add(best_row["_dev_cycle"])

                    removed_mj = mj_passing[
                        ~mj_passing["_dev_cycle"].isin(keep_device_cycles)
                    ].index
                    removed_idx.extend(removed_mj.tolist())

                if removed_idx:
                    params.loc[removed_idx, "filter_reason"] += "cycle: not best EQE, "
                    reasons.append(
                        f"cycle filter: best EQE per pixel kept ({len(removed_idx)} cycles removed)"
                    )

            elif cycle_mode == "manual" and selected_cycles:
                cycle_set = set(selected_cycles)
                removed = passing[~passing["cycle"].isin(cycle_set)].index
                if len(removed) > 0:
                    params.loc[removed, "filter_reason"] += "cycle: not in manual selection, "
                    reasons.append(
                        f"cycle manual selection {sorted(cycle_set)} ({len(removed)} removed)"
                    )
            # mode == "all": no filtering

        omitted = params[params["filter_reason"] != ""].copy()
        filtered = params[params["filter_reason"] == ""].copy()
        omitted["filter_reason"] = omitted["filter_reason"].str.rstrip(", ")

        curves = self.data.get("curves", pd.DataFrame()).copy()
        if not curves.empty and not filtered.empty:
            keys = filtered[self.KEY_COLUMNS].drop_duplicates()
            filtered_curves = curves.merge(keys, on=self.KEY_COLUMNS, how="inner")
        else:
            filtered_curves = pd.DataFrame(columns=curves.columns)

        if not filtered_curves.empty:
            if wavelength_min is not None:
                filtered_curves = filtered_curves[
                    filtered_curves["wavelength_array"] >= float(wavelength_min)
                ]
            if wavelength_max is not None:
                filtered_curves = filtered_curves[
                    filtered_curves["wavelength_array"] <= float(wavelength_max)
                ]

        self.filtered_params = filtered
        self.filtered_curves = filtered_curves
        self.omitted_params = omitted
        self.filter_parameters = reasons

        self.data["filtered_params"] = filtered
        self.data["filtered_curves"] = filtered_curves
        self.data["junk_params"] = omitted

        return filtered, filtered_curves, reasons

    def _find_unique_values(self):
        if "params" not in self.data or self.data["params"].empty:
            self.unique_vals = []
            return self.unique_vals
        self.unique_vals = list(dict.fromkeys(self.data["params"]["sample_id"].dropna().tolist()))
        return self.unique_vals

    def get_data(self):
        return self.data

    def get_unique_values(self):
        return self.unique_vals

    def get_filtered_data(self):
        return self.filtered_params

    def get_filter_parameters(self):
        return self.filter_parameters

    def has_data(self):
        return bool(self.data and "params" in self.data and not self.data["params"].empty)
