"""Tests for MPPT_Analysis (ported from HZB's MPPT test files). The app modules come from the
app_loader fixture (tests/MPPT_Analysis/conftest.py); never touches the network. The write-back
tests check the guards of the peroTF version: MPPT entries only, fit results only, a backup in
the entry's own upload before every write, a hash re-check and a read-back."""

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import ipywidgets as widgets
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest
from pydantic import ValidationError

from perotf_utils.config import ENTRY_TYPE_FAMILIES

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "api_responses.json"

_st = _dm = _ft = _pm = _gui = _ctrl = None


@pytest.fixture(scope="module", autouse=True)
def _bind_app_modules(mods):
    global _st, _dm, _ft, _pm, _gui, _ctrl
    _st, _dm, _ft = mods["app_state"], mods["data_manager"], mods["fitting_tools"]
    _pm, _gui, _ctrl = mods["plot_manager"], mods["gui_components"], mods["app_controller"]


# ==========================================================================================
# data, fitting, figures of merit, plots
# ==========================================================================================
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "api_responses.json"

# Mirror of conftest.FIXTURE_ROWS: kept local to avoid cross-conftest import
_TIME = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
_POWER = np.array([15.2, 14.8, 14.4, 14.1, 13.9])


def _make_curve(sample_id="batch1&sample1", curve_id=0):
    return {
        "sample_id": sample_id,
        "curve_id": curve_id,
        "time": _TIME.copy(),
        "data": _POWER.copy(),
    }


# ===========================================================================
# _dm.MPPTRow model
# ===========================================================================


class TestMPPTRow:
    def test_valid_row_accepted(self):
        row = _dm.MPPTRow(time=0.0, power_density=15.2, voltage=0.92, current_density=-16.5)
        assert row.time == 0.0
        assert row.power_density == 15.2

    def test_model_dump_returns_all_fields(self):
        row = _dm.MPPTRow(time=0.0, power_density=15.2, voltage=0.92, current_density=-16.5)
        assert set(row.model_dump().keys()) == {
            "time",
            "power_density",
            "voltage",
            "current_density",
        }

    def test_none_coerced_to_nan(self):
        row = _dm.MPPTRow(time=0.0, power_density=None, voltage=0.9, current_density=-16.0)
        assert np.isnan(row.power_density)

    def test_invalid_time_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _dm.MPPTRow(time="bad", power_density=15.0, voltage=0.9, current_density=-16.0)

    def test_string_numeric_coerced(self):
        row = _dm.MPPTRow(time="1.5", power_density="14.1", voltage="0.89", current_density="-15.8")
        assert row.time == 1.5


# ===========================================================================
# _dm.DataManager.load_offline
# ===========================================================================


def test_load_offline_populates_curves_and_ids(loaded_manager):
    assert loaded_manager.curves is not None
    assert loaded_manager.sample_ids is not None


def test_load_offline_returns_false_for_empty_fixture(tmp_path):
    fp = tmp_path / "empty.json"
    fp.write_text(json.dumps({"descriptions": {}, "measurements": {}}))
    assert _dm.DataManager(url="http://mock", token="tok").load_offline(fp) is False


def test_load_offline_skips_entirely_invalid_rows(tmp_path):
    bad = {
        "descriptions": {"s1": "bad"},
        "measurements": {
            "s1": [
                [
                    [
                        {
                            "time": "not-a-number",
                            "power_density": "x",
                            "voltage": "y",
                            "current_density": "z",
                        }
                    ],
                    {},
                ]  # noqa: E501
            ]
        },
    }
    fp = tmp_path / "bad.json"
    fp.write_text(json.dumps(bad))
    assert _dm.DataManager(url="http://mock", token="tok").load_offline(fp) is False


def test_curves_has_three_level_multiindex(loaded_manager):
    assert loaded_manager.curves.index.nlevels == 3


def test_sample_ids_populated(loaded_manager):
    sids = list(loaded_manager.sample_ids)
    assert "batch1&sample1" in sids
    assert "batch1&sample2" in sids


def test_sign_and_scale_transformations_applied(loaded_manager):
    row = loaded_manager.curves.loc["batch1&sample1"].iloc[0]
    # NOMAD stores power as -15.2 (generation is negative); the app works with a positive
    # power so every figure of merit has the same orientation.
    assert abs(row["power_density"] - 15.2) < 1e-9
    # Original: current_density=-16.5 -> inverted together with the power to 16.5
    assert abs(row["current_density"] - 16.5) < 1e-9
    # Original: time=0.0 -> scaled by 1/3600 -> still 0.0
    assert row["time"] == pytest.approx(0.0)


def test_properties_contains_descriptions(loaded_manager):
    props = loaded_manager.properties
    assert "batch1&sample1" in props.index
    assert props.loc["batch1&sample1", "description"] == "Sample 1"


def test_entries_dataframe_present(loaded_manager):
    assert loaded_manager.entries is not None
    assert "entry_names" in loaded_manager.entries.columns


# ===========================================================================
# PlotManager: individual curves
# ===========================================================================


class TestPlotIndividualCurves:
    def test_returns_list_of_figures(self, plot_manager):
        figs = plot_manager.plot_individual_curves(
            [_make_curve(), _make_curve(curve_id=1)], "power_density"
        )
        assert isinstance(figs, list)
        assert len(figs) == 2
        assert all(isinstance(f, go.Figure) for f in figs)

    def test_scatter_trace_present(self, plot_manager):
        figs = plot_manager.plot_individual_curves([_make_curve()], "power_density")
        assert any(isinstance(t, go.Scatter) for t in figs[0].data)

    def test_fixture_power_values_reach_figure(self, plot_manager):
        figs = plot_manager.plot_individual_curves([_make_curve()], "power_density")
        y_vals = list(figs[0].data[0].y)
        assert 15.2 in y_vals
        assert 13.9 in y_vals

    def test_fixture_time_values_reach_figure(self, plot_manager):
        figs = plot_manager.plot_individual_curves([_make_curve()], "power_density")
        x_vals = list(figs[0].data[0].x)
        assert 0.0 in x_vals
        assert 2.0 in x_vals


# ===========================================================================
# PlotManager: all together
# ===========================================================================


class TestPlotAllTogether:
    def test_returns_single_figure(self, plot_manager):
        curves = [_make_curve(), _make_curve(sample_id="batch1&sample2")]
        assert isinstance(plot_manager.plot_all_together(curves, "power_density"), go.Figure)

    def test_one_trace_per_curve(self, plot_manager):
        curves = [_make_curve(), _make_curve(sample_id="batch1&sample2")]
        assert len(plot_manager.plot_all_together(curves, "power_density").data) == 2

    def test_fixture_time_values_in_first_trace(self, plot_manager):
        fig = plot_manager.plot_all_together([_make_curve()], "power_density")
        x_vals = list(fig.data[0].x)
        assert 0.0 in x_vals
        assert 2.0 in x_vals


# ===========================================================================
# PlotManager: by sample
# ===========================================================================


class TestPlotBySample:
    def test_one_figure_per_sample(self, plot_manager):
        curves = [
            _make_curve(sample_id="s1", curve_id=0),
            _make_curve(sample_id="s1", curve_id=1),
            _make_curve(sample_id="s2", curve_id=0),
        ]
        figs = plot_manager.plot_by_sample(curves, "power_density")
        assert isinstance(figs, list)
        assert len(figs) == 2

    def test_each_figure_is_go_figure(self, plot_manager):
        figs = plot_manager.plot_by_sample([_make_curve()], "power_density")
        assert all(isinstance(f, go.Figure) for f in figs)


# ===========================================================================
# PlotManager: area quartiles
# ===========================================================================


class TestPlotAreaQuartiles:
    def test_returns_list_of_figures(self, plot_manager):
        curves = [_make_curve(curve_id=i) for i in range(3)]
        figs = plot_manager.plot_area_quartiles(curves, "power_density")
        assert isinstance(figs, list)
        assert all(isinstance(f, go.Figure) for f in figs)

    def test_skips_single_curve_samples(self, plot_manager):
        assert plot_manager.plot_area_quartiles([_make_curve()], "power_density") == []

    def test_fill_trace_present(self, plot_manager):
        curves = [_make_curve(curve_id=i) for i in range(3)]
        figs = plot_manager.plot_area_quartiles(curves, "power_density")
        if figs:
            fill_traces = [t for t in figs[0].data if getattr(t, "fill", None) == "toself"]
            assert len(fill_traces) > 0


# ===========================================================================
# PlotManager: area std
# ===========================================================================


class TestPlotAreaStd:
    def test_returns_list_of_figures(self, plot_manager):
        curves = [_make_curve(curve_id=i) for i in range(3)]
        figs = plot_manager.plot_area_std(curves, "power_density")
        assert isinstance(figs, list)
        assert all(isinstance(f, go.Figure) for f in figs)

    def test_skips_single_curve_samples(self, plot_manager):
        assert plot_manager.plot_area_std([_make_curve()], "power_density") == []


# ===========================================================================
# PlotManager: histograms
# ===========================================================================


class TestPlotHistograms:
    def test_returns_none_when_no_fit_results(self, plot_manager):
        assert plot_manager.plot_histograms() is None

    def test_returns_figure_when_T80_column_present(self, plot_manager):
        import pandas as pd

        plot_manager.app_state.fit_results = pd.DataFrame(
            {"sample_id": ["s1", "s2", "s3"], "T80": [100.0, 120.0, 90.0]}
        )
        fig = plot_manager.plot_histograms()
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_histogram_trace_type_and_values(self, plot_manager):
        import pandas as pd

        plot_manager.app_state.fit_results = pd.DataFrame(
            {"sample_id": ["s1", "s2"], "t80": [80.0, 95.0]}
        )
        fig = plot_manager.plot_histograms()
        hist_traces = [t for t in fig.data if isinstance(t, go.Histogram)]
        assert len(hist_traces) > 0
        # The 80.0 and 95.0 values should appear in the histogram x data
        x_vals = list(hist_traces[0].x)
        assert 80.0 in x_vals
        assert 95.0 in x_vals


# ===========================================================================
# fitting_tools: unified ISOS figures of merit (issue #26)
# ===========================================================================


class TestCrossingTimePolicy:
    """crossing_time(): real-if-reached, else-extrapolated (bounded to
    EXTRAPOLATION_HORIZON_FACTOR), else-NaN - see the policy documented
    above find_tS in _ft.py."""

    def test_returns_real_time_when_raw_data_reaches_threshold(self):
        times = np.linspace(0, 20, 500)
        power = 18 * np.exp(-times / 3.0)
        reference = _ft.initial_reference(power)
        result = _ft.crossing_time(times, power, reference, 0.8, lambda t: 18 * np.exp(-t / 3.0))
        expected = times[np.argmax(power <= 0.8 * reference)]
        assert result == pytest.approx(expected)

    def test_extrapolates_when_not_reached_within_measurement(self):
        # True crossing is at t=-3*ln(0.8)=0.669 - measure only up to t=0.3,
        # well before it, so real data never reaches 80% and this must
        # extrapolate from the model instead.
        times = np.linspace(0, 0.3, 50)
        power = 18 * np.exp(-times / 3.0)
        result = _ft.crossing_time(times, power, 18.0, 0.8, lambda t: 18 * np.exp(-t / 3.0))
        expected = -3.0 * np.log(0.8)  # closed-form crossing for this exact curve
        assert result == pytest.approx(expected, rel=1e-3)
        assert result > times[-1]  # genuinely extrapolated, not clamped to measurement end

    def test_returns_nan_for_flat_trend(self):
        times = np.linspace(0, 20, 50)
        power = np.full_like(times, 18.0)
        result = _ft.crossing_time(times, power, 18.0, 0.8, lambda t: 18.0)
        assert np.isnan(result)

    def test_returns_nan_for_improving_trend(self):
        times = np.linspace(0, 20, 50)
        power = 18.0 + 0.1 * times
        result = _ft.crossing_time(times, power, 18.0, 0.8, lambda t: 18.0 + 0.1 * t)
        assert np.isnan(result)

    def test_closed_form_used_when_provided(self):
        times = np.linspace(0, 0.3, 50)  # before the true crossing at t=0.669 - see above
        power = 18 * np.exp(-times / 3.0)

        def closed_form(threshold):
            return -3.0 * np.log(threshold / 18.0)

        result = _ft.crossing_time(
            times, power, 18.0, 0.8, lambda t: 18 * np.exp(-t / 3.0), closed_form
        )
        assert result == pytest.approx(-3.0 * np.log(0.8), rel=1e-6)


class TestPceAfter1000h:
    def test_reads_real_value_when_measurement_covers_1000h(self):
        times = np.linspace(0, 1500, 500)
        power = 18 * np.exp(-times / 2000.0)
        result = _ft.pce_after_1000h(times, power, lambda t: 18 * np.exp(-t / 2000.0))
        assert result == pytest.approx(np.interp(1000.0, times, power))

    def test_extrapolates_within_ten_x_horizon(self):
        times = np.linspace(0, 150, 50)  # 10x horizon = 1500h, covers 1000h
        power = 18 * np.exp(-times / 2000.0)
        result = _ft.pce_after_1000h(times, power, lambda t: 18 * np.exp(-t / 2000.0))
        assert result == pytest.approx(18 * np.exp(-1000.0 / 2000.0), rel=1e-6)

    def test_nan_beyond_ten_x_horizon(self):
        times = np.linspace(0, 20, 50)  # 10x horizon = 200h, doesn't reach 1000h
        power = 18 * np.exp(-times / 2000.0)
        result = _ft.pce_after_1000h(times, power, lambda t: 18 * np.exp(-t / 2000.0))
        assert np.isnan(result)


class TestModelListProducesFullMetricSet:
    """Every model (direct product feedback on issue #26) computes the same
    full set of figures of merit, not a hand-picked subset per model."""

    _REQUIRED_COLUMNS = {"R2", "T80", "T95", "Ts80", "Ts95", "tS", "PCE_after_1000_h", "LEY"}

    # A loop, not parametrize: the app modules only exist once app_loader has run.
    def test_columns_include_full_metric_set(self):
        for model in _ft.available_fit_model_list:
            assert self._REQUIRED_COLUMNS.issubset(set(model.columns)), model.name

    def test_fit_produces_a_value_for_every_declared_column(self):
        times = np.linspace(0.01, 20, 200)
        power = 18 * np.exp(-((times / 5.0) ** 0.8))
        for model in _ft.available_fit_model_list:
            values, fitted_curve, result = model.parfunc(power, times)
            assert len(values) == len(model.columns), model.name
            assert len(fitted_curve) == len(power), model.name


# ===========================================================================
# Per-measurement (pixel) selection
# ===========================================================================


class TestPerCurveSelection:
    """batch1&sample1 in the fixture holds two measurements (curves 0 and 1)."""

    SAMPLE = "batch1&sample1"

    def test_fit_sample_fits_every_curve_by_default(self, loaded_manager):
        model = _ft.available_fit_model_list[0]
        fits = loaded_manager.fit_sample(
            loaded_manager.curves, loaded_manager.sample_ids, self.SAMPLE, model
        )
        assert set(fits) <= {0, 1}

    def test_fit_sample_restricted_to_one_curve(self, loaded_manager, mocker):
        mocker.patch.object(_dm, "fit_curve", return_value={"x": 1})
        model = _ft.available_fit_model_list[0]
        fits = loaded_manager.fit_sample(
            loaded_manager.curves,
            loaded_manager.sample_ids,
            self.SAMPLE,
            model,
            curve_ids=[1],
        )
        assert list(fits) == [1]

    def test_selected_curve_data_filters_to_chosen_curves(self, loaded_manager):
        data = loaded_manager.get_selected_curve_data(
            loaded_manager.curves,
            loaded_manager.sample_ids,
            [self.SAMPLE],
            "power_density",
            selected_curves=[(self.SAMPLE, 1)],
        )
        assert [(d["sample_id"], d["curve_id"]) for d in data] == [(self.SAMPLE, 1)]

    def test_selected_curve_data_without_filter_returns_all(self, loaded_manager):
        data = loaded_manager.get_selected_curve_data(
            loaded_manager.curves,
            loaded_manager.sample_ids,
            [self.SAMPLE],
            "power_density",
        )
        assert len(data) == 2

    def test_curve_label_strips_sample_prefix(self, loaded_manager):
        entries = pd.DataFrame(
            {"entry_names": ["S1 Front_PixelA", ""]},
            index=pd.MultiIndex.from_tuples([("S1", 0), ("S1", 1)]),
        )
        assert loaded_manager.get_curve_label(entries, "S1", 0) == "Front_PixelA"
        assert loaded_manager.get_curve_label(entries, "S1", 1) == "Curve 1"
        assert loaded_manager.get_curve_label(None, "S1", 2) == "Curve 2"


class TestAppStateCurveSelection:
    def test_default_selection_means_all_curves(self):
        state = _st.AppState()
        state.set_selected_samples(["s1"])
        assert state.data["selected_curves"] is None
        assert state.selected_curve_ids("s1") is None

    def test_selected_curves_are_stored_per_sample(self):
        state = _st.AppState()
        state.set_selected_samples(["s1", "s2"], selected_curves=[("s1", 0), ("s1", 2), ("s2", 1)])
        assert state.selected_curve_ids("s1") == [0, 2]
        assert state.selected_curve_ids("s2") == [1]
        assert state.get_selected_curves_count() == 3

    def test_update_curve_fit_results_keeps_other_curves(self):
        model = _ft.available_fit_model_list[0]
        fit = {"model": model, "time": np.array([0.0, 1.0]), "params": {}}
        state = _st.AppState()
        state.set_fit_results({("s1", 0): fit, ("s1", 1): fit})
        state.update_curve_fit_results({("s1", 1): fit})
        assert set(state.fitted_curves_data) == {("s1", 0), ("s1", 1)}


# ---------------------------------------------------------------------------
# 5.2 fitting correctness: sustained T80 (C1), one LEY unit (C2), bounded tS (C3),
# overflow guard (H1), robust write-back (H2), selection-only fits (H3), aligned
# curves (H4), one sign convention (H6)
# ---------------------------------------------------------------------------

_T = np.linspace(0, 100, 400)
_TRUE = 20 * np.exp(-_T / 300)  # a decay whose exact T80 is 300*ln(1/0.8) = 66.9 h


def _crossing(power, fraction=0.8):
    reference = _ft.initial_reference(power)
    return _ft.crossing_time(
        _T,
        power,
        reference,
        fraction,
        lambda t: 20 * np.exp(-t / 300),
        lambda threshold: 300 * np.log(20 / threshold),
    )


def test_t80_ignores_a_ramp_up_start_and_a_single_dropout():
    clean = _crossing(_TRUE)
    ramp = _TRUE.copy()
    ramp[:10] = np.linspace(2, _TRUE[10], 10)  # tracker still settling
    dropout = _TRUE.copy()
    dropout[5] = 0.0  # one bad point
    assert 60 < clean < 80
    assert _crossing(ramp) == pytest.approx(clean, abs=4)  # was 0.0 h
    assert _crossing(dropout) == pytest.approx(clean, abs=4)  # was 1.25 h


def test_t80_needs_a_sustained_crossing_and_noise_does_not_trigger_it_early():
    rng = np.random.default_rng(1)
    noisy = _TRUE + rng.normal(0, 0.3, _T.size)
    assert _crossing(noisy) == pytest.approx(_crossing(_TRUE), abs=6)


def test_every_model_reports_the_same_lifetime_energy_in_kwh_per_m2():
    """C2: two models multiplied by 10, four did not, and the logistic one gave -inf."""
    rng = np.random.default_rng(0)
    y = _TRUE + rng.normal(0, 0.05, _T.size)
    values = {}
    for model in _ft.available_fit_model_list:
        result, _, _ = model.parfunc(y, _T)
        row = dict(zip(model.columns, [float(getattr(v, "n", v)) for v in result]))
        assert np.isfinite(row["LEY"]), model.name
        values[model.name] = row["LEY"]
    reference = np.mean(list(values.values()))
    for name, value in values.items():
        assert value == pytest.approx(reference, rel=0.02), name
    # exact: integral of 20 mW/cm^2 * exp(-t/300) from 0 to the T80, at 0.01 kWh/m^2 per mWh/cm^2
    t80 = 300 * np.log(1 / 0.8)
    exact = 20 * 300 * (1 - np.exp(-t80 / 300)) * 0.01
    assert reference == pytest.approx(exact, rel=0.1)


def test_a_constant_20_mw_cm2_curve_over_1000_h_is_200_kwh_per_m2():
    times = np.linspace(0, 1000, 500)
    power = np.full_like(times, 20.0)
    value = _ft.ley_after_1000h(times, power, lambda t: 20.0)
    assert value == pytest.approx(200.0)


def test_ley_after_1000h_follows_the_real_else_model_else_nan_policy():
    short = np.linspace(0, 50, 100)
    flat = np.full_like(short, 20.0)
    # 1000 h is 20x the measurement: beyond the 10x horizon
    assert np.isnan(_ft.ley_after_1000h(short, flat, lambda t: 20.0))
    mid = np.linspace(0, 200, 100)
    assert _ft.ley_after_1000h(mid, np.full_like(mid, 20.0), lambda t: 20.0) == (
        pytest.approx(200.0)
    )
    # a model that decays below zero never gives back negative energy: 5 - t is positive for
    # 5 h only, 0.5 * 5 * 5 = 12.5 mWh/cm^2 = 0.125 kWh/m^2
    assert _ft.ley_after_1000h(mid, np.full_like(mid, 1.0), lambda t: 5 - t) == (
        pytest.approx(0.125, rel=1e-3)
    )


def test_every_model_offers_ley_1000h_and_it_is_written_as_a_fit_parameter():

    for model in _ft.available_fit_model_list:
        assert "LEY_1000h" in model.columns, model.name
    assert all(
        units["LEY_1000h"] == ("kWh/m^2", 1.0) for units in _dm._LEFTOVER_PARAM_UNITS.values()
    )


def test_logistic_ley_survives_a_huge_rate_constant():
    """log(1+exp(k(t-x0))) overflowed to inf for a large k and aborted the write-back."""
    k = 5000.0
    value = 0.5 / k * (np.logaddexp(0, k * (80 - 50)) - np.logaddexp(0, -k * 50))
    assert np.isfinite(value)


def test_stabilization_time_is_never_beyond_the_measurement():
    biexp = next(m for m in _ft.available_fit_model_list if m.name == "Biexponential")
    result, _, _ = biexp.parfunc(_TRUE.copy(), _T)
    row = dict(zip(biexp.columns, [float(getattr(v, "n", v)) for v in result]))
    assert np.isnan(row["tS"]) or row["tS"] <= _T[-1]  # was 1350 h on 100 h of data
    logistic = next(m for m in _ft.available_fit_model_list if "Logistic" in m.name)
    result, _, _ = logistic.parfunc(_TRUE.copy(), _T)
    row = dict(zip(logistic.columns, [float(getattr(v, "n", v)) for v in result]))
    assert row["tS"] <= _T[-1]  # was 10x the measurement length (1000 h)


def test_find_ts_has_nothing_to_stabilize_from_for_a_monotonic_decay():
    class _Result:
        params = None

        @staticmethod
        def eval(params, t):
            return 20 * np.exp(-t / 300)

    t_s, pce_ts = _ft.find_tS(_T, _Result)
    assert t_s == 0.0 and pce_ts == pytest.approx(20.0)


def test_find_ts_finds_the_recovery_after_a_dip_inside_the_measured_window():
    class _Result:
        params = None

        @staticmethod
        def eval(params, t):
            return 10 + 0.5 * np.sin(t / 10)  # dips, then recovers inside 0..100

    t_s, pce_ts = _ft.find_tS(_T, _Result)
    assert 0 < t_s <= _T[-1]
    assert pce_ts == pytest.approx(10 + 0.5 * np.sin(t_s / 10), abs=1e-3)


def test_has_value_rejects_none_nan_and_infinity():

    assert _dm._has_value(1.5) and _dm._has_value(0.0) and _dm._has_value(3)
    for bad in (None, float("nan"), float("inf"), float("-inf"), "abc"):
        assert not _dm._has_value(bad)


def _fit_for(model):
    return {
        "model": model,
        "time": np.array([0.0, 1.0, 2.0]),
        "params": {"R2": 0.99, "LEY": float("-inf"), "slope": float("nan"), "intercept": 1.0},
    }


def _two_point_rows(power, current=-20.0):
    return [
        {"time": 0.0, "power_density": power, "voltage": 0.9, "current_density": current},
        {"time": 3600.0, "power_density": power, "voltage": 0.9, "current_density": current},
    ]


def test_an_entry_without_rows_does_not_shift_the_entry_ids_of_the_others():
    """H4: curve k was labelled with entry k's id while holding entry k+1's data."""
    raw = {
        "s1": [
            ({"name": "empty", "time": [], "power_density": []}, {"entry_id": "E-empty"}),
            (_two_point_rows(-10.0), {"entry_id": "E-first", "upload_id": "u"}),
            (_two_point_rows(-30.0), {"entry_id": "E-second", "upload_id": "u"}),
        ],
        "s2": [({"time": []}, {"entry_id": "E-none"})],  # a sample with no usable row at all
        "s3": [(_two_point_rows(-50.0), {"entry_id": "E-s3", "upload_id": "u"})],
    }
    manager = _dm.DataManager(url="http://mock", token="t")
    assert manager._build_from_raw(raw, {})
    assert list(manager.sample_ids) == ["s1", "s3"]  # s2 is not in, s3 is not relabelled s2
    assert manager.get_entry_id(manager.entries, "s1", 0) == "E-first"
    assert manager.get_entry_id(manager.entries, "s1", 1) == "E-second"
    assert manager.get_entry_id(manager.entries, "s3", 0) == "E-s3"
    _, power = manager.get_raw_curve(manager.curves, manager.sample_ids, "s1", 0)
    assert power[0] == pytest.approx(10.0)  # curve 0 really is the entry labelled E-first
    _, power = manager.get_raw_curve(manager.curves, manager.sample_ids, "s3", 0)
    assert power[0] == pytest.approx(50.0)


def test_power_sign_is_detected_per_entry_not_flipped_blindly():
    """H6: negative stored power is made positive; an entry already positive is left alone."""
    manager = _dm.DataManager(url="http://mock", token="t")
    raw = {
        "neg": [(_two_point_rows(-15.0, -16.0), {"entry_id": "a"})],
        "pos": [(_two_point_rows(15.0, 16.0), {"entry_id": "b"})],
    }
    assert manager._build_from_raw(raw, {})
    for sample in ("neg", "pos"):
        _, power = manager.get_raw_curve(manager.curves, manager.sample_ids, sample, 0)
        assert power[0] == pytest.approx(15.0)
        assert manager.curves.loc[sample].iloc[0]["current_density"] == pytest.approx(16.0)


def test_demo_data_is_in_the_real_nomad_convention(loaded_manager):
    """The demo file used to be positive power next to negative current, then got flipped."""
    raw = json.loads(FIXTURE_PATH.read_text())
    power = raw["measurements"]["batch1&sample1"][0][0][0]["power_density"]
    assert power < 0  # stored like NOMAD stores generation
    _, shown = loaded_manager.get_raw_curve(
        loaded_manager.curves, loaded_manager.sample_ids, "batch1&sample1", 0
    )
    assert shown[0] > 0


def test_fits_of_deselected_samples_are_dropped_and_a_new_batch_starts_clean():
    """H3: a sample no longer selected kept its fit and was written to NOMAD."""
    state = _st.AppState()
    model = _ft.available_fit_model_list[0]
    state.update_curve_fit_results(
        {
            ("A", 0): _fit_for(model),
            ("B", 0): _fit_for(model),
            ("B", 1): _fit_for(model),
            ("C", 0): _fit_for(model),
        }
    )
    state.set_selected_samples(["A", "B"])
    assert set(state.fitted_curves_data) == {("A", 0), ("B", 0), ("B", 1)}
    state.set_selected_samples(["A", "B"], selected_curves=[("A", 0), ("B", 1)])
    assert set(state.fitted_curves_data) == {("A", 0), ("B", 1)}
    assert set(state.fit_results["sample_id"]) == {"A", "B"}

    state.load_curves_data(None, None, None, None)
    assert state.fitted_curves_data == {} and state.cleaned_power == {}
    assert not state.has_fit_results()


_STORED = {
    "fit_method": "Biexponential",
    "fit_computed_by": "MPPT_Analysis v0.3.0 (edgar)",
    "fit_computed_at": "2026-09-09T14:53:01.297348",
    "fit_range_start": 68283.0,
    "fit_range_end": 3629877.0,
    "T80": 1708239.0,
    "T95": 68283.0,
    "initial_stabilization_time": 2226113.0,
    "fit_r_squared": 0.9978,
    "lifetime_energy_yield": 4484.7,
    "fit_parameters": [
        {"name": "A1", "value": 12.9, "unit": "mW/cm^2", "error": 0.01},
        {"name": "tau1", "value": 3897821.0, "unit": "s", "error": 4698.0},
    ],
}


def test_stored_fit_is_found_only_when_the_entry_has_a_fit_method():

    assert _dm.stored_fit_from_archive({"results": [_STORED]}) == _STORED
    assert _dm.stored_fit_from_archive({"results": [{"T80": 5.0}]}) == {"T80": 5.0}
    assert _dm.stored_fit_from_archive({"results": [{"power_density_at_t0": 5.0}]}) is None
    assert _dm.stored_fit_from_archive({"results": []}) is None
    assert _dm.stored_fit_from_archive({"name": "x"}) is None


def test_stored_fit_row_converts_seconds_back_to_the_hours_the_app_shows():

    row = _dm.stored_fit_row(_STORED)
    assert row["model"] == "Biexponential"
    assert row["T80"] == pytest.approx(1708239.0 / 3600)
    assert row["tS"] == pytest.approx(2226113.0 / 3600)
    assert row["tau1"] == pytest.approx(3897821.0 / 3600)  # seconds in NOMAD, hours here
    assert row["tau1_error"] == pytest.approx(4698.0 / 3600)
    assert row["A1"] == pytest.approx(12.9)
    assert row["R2"] == pytest.approx(0.9978)
    assert "Stored in NOMAD" in row["note"] and "edgar" in row["note"]


def test_entries_carry_the_stored_fit_per_curve():
    manager = _dm.DataManager("http://x", "t")
    data = {
        "time": [0.0, 3600.0],
        "power_density": [10.0, 9.0],
        "voltage": [1.0, 1.0],
        "current_density": [10.0, 9.0],
    }
    raw = {
        "S1": [
            ({**data, "results": [_STORED]}, {"entry_id": "e1", "upload_id": "u"}),
            (dict(data), {"entry_id": "e2", "upload_id": "u"}),
        ]
    }
    assert manager._build_from_raw(raw, {"S1": ""})
    assert manager.get_stored_fit(manager.entries, "S1", 0)["fit_method"] == "Biexponential"
    assert manager.get_stored_fit(manager.entries, "S1", 1) is None


# ==========================================================================================
# outlier cleaning
# ==========================================================================================
def _decay(n=300):
    """Burn-in style decay with a little measurement noise."""
    rng = np.random.default_rng(0)
    t = np.arange(n)
    return 2.0 + 1.0 * np.exp(-t / 15.0) + rng.normal(0, 0.003, n)


class TestFindOutliers:
    def test_flags_isolated_spikes_and_dips(self):
        y = _decay()
        y[100] = 200.0
        y[200] = 0.1
        assert list(np.flatnonzero(_dm.find_outliers(y))) == [100, 200]

    def test_keeps_the_burn_in_decay(self):
        assert not _dm.find_outliers(_decay()).any()

    def test_edges_are_never_flagged(self):
        y = _decay()
        y[0] = 50.0
        y[-1] = 50.0
        assert not _dm.find_outliers(y).any()

    def test_lower_threshold_removes_more(self):
        y = _decay()
        assert _dm.find_outliers(y, threshold=1.5).sum() > _dm.find_outliers(y, threshold=6.0).sum()

    def test_short_or_flat_curves_are_untouched(self):
        assert not _dm.find_outliers(np.array([1.0, 50.0, 1.0])).any()
        assert not _dm.find_outliers(np.full(200, 3.0)).any()


class TestRemoveOutliers:
    def test_returns_nan_copy_with_same_length_and_leaves_input(self):
        y = _decay()
        y[100] = 200.0
        original = y.copy()
        cleaned, n = _dm.remove_outliers(y)
        assert n == 1
        assert len(cleaned) == len(y)
        assert np.isnan(cleaned[100])
        assert np.array_equal(y, original)

    def test_cleaned_curve_still_fits(self, loaded_manager):

        sample_id = loaded_manager.sample_ids[0]
        curve_id = loaded_manager.get_curve_ids_for_sample(
            loaded_manager.curves, loaded_manager.sample_ids, sample_id
        )[0]
        _, y = loaded_manager.get_raw_curve(
            loaded_manager.curves, loaded_manager.sample_ids, sample_id, curve_id
        )
        cleaned = {(sample_id, curve_id): y.copy()}
        cleaned[(sample_id, curve_id)][1] = np.nan
        fits = loaded_manager.fit_sample(
            loaded_manager.curves,
            loaded_manager.sample_ids,
            sample_id,
            next(m for m in _ft.available_fit_model_list if m.abbreviated_name == "Linear"),
            curve_ids=[curve_id],
            cleaned=cleaned,
        )
        assert len(fits[curve_id]["original_power"]) == len(y) - 1


class TestCleanedLayer:
    def test_get_curve_prefers_cleaned_and_raw_stays_unchanged(self, loaded_manager):
        dm = loaded_manager
        sample_id = dm.sample_ids[0]
        curve_id = dm.get_curve_ids_for_sample(dm.curves, dm.sample_ids, sample_id)[0]
        t_raw, y_raw = dm.get_raw_curve(dm.curves, dm.sample_ids, sample_id, curve_id)
        marker = np.full(len(y_raw), 7.0)
        cleaned = {(sample_id, curve_id): marker}

        t, y = dm.get_curve(dm.curves, dm.sample_ids, sample_id, curve_id, cleaned)
        assert np.array_equal(y, marker)
        assert np.array_equal(t, t_raw)
        _, y_after = dm.get_raw_curve(dm.curves, dm.sample_ids, sample_id, curve_id)
        assert not np.array_equal(y_after, marker)
        _, y_none = dm.get_curve(dm.curves, dm.sample_ids, sample_id, curve_id, None)
        assert np.array_equal(y_none, y_raw)

    def test_cleaning_blanks_the_same_points_in_voltage_and_current(self, loaded_manager):
        """Clean all plots must give clean Voltage and Current Density too, not only power."""
        dm = loaded_manager
        sample_id = dm.sample_ids[0]
        curve_id = dm.get_curve_ids_for_sample(dm.curves, dm.sample_ids, sample_id)[0]
        _, raw_power = dm.get_raw_curve(dm.curves, dm.sample_ids, sample_id, curve_id)
        cleaned_power = np.array(raw_power, dtype=float)
        cleaned_power[1] = np.nan
        cleaned = {(sample_id, curve_id): cleaned_power}

        def item(variable):
            items = dm.get_selected_curve_data(
                dm.curves, dm.sample_ids, [sample_id], variable, cleaned=cleaned
            )
            return next(i for i in items if i["curve_id"] == curve_id)["data"]

        for variable in ("power_density", "voltage", "current_density"):
            data = item(variable)
            assert np.isnan(data[1]), variable
            assert np.isfinite(np.delete(data, 1)).all(), variable

    def test_other_curves_and_raw_voltage_are_untouched(self, loaded_manager):
        dm = loaded_manager
        sample_id = dm.sample_ids[0]
        curve_id = dm.get_curve_ids_for_sample(dm.curves, dm.sample_ids, sample_id)[0]
        _, raw_power = dm.get_raw_curve(dm.curves, dm.sample_ids, sample_id, curve_id)
        cleaned_power = np.array(raw_power, dtype=float)
        cleaned_power[0] = np.nan
        before = dm.get_selected_curve_data(dm.curves, dm.sample_ids, [sample_id], "voltage")
        dm.get_selected_curve_data(
            dm.curves,
            dm.sample_ids,
            [sample_id],
            "voltage",
            cleaned={(sample_id, curve_id): cleaned_power},
        )
        after = dm.get_selected_curve_data(dm.curves, dm.sample_ids, [sample_id], "voltage")
        assert all(np.array_equal(b["data"], a["data"]) for b, a in zip(before, after))

    def test_mask_removed_points_keeps_points_that_were_already_nan(self):

        raw = np.array([1.0, np.nan, 3.0, 4.0])
        cleaned = np.array([1.0, np.nan, np.nan, 4.0])
        out = _dm.mask_removed_points([10.0, 20.0, 30.0, 40.0], raw, cleaned)
        assert out[0] == 10.0 and out[1] == 20.0 and np.isnan(out[2]) and out[3] == 40.0

    def test_cleaning_drops_stale_fits_and_restore_clears_layer(self):
        state = _st.AppState()
        model = type("M", (), {"abbreviated_name": "M"})()
        fit = {"model": model, "time": np.array([0.0, 1.0]), "params": {}}
        state.set_fit_results({("s", 0): fit, ("s", 1): fit})

        state.set_cleaned_power({("s", 0): np.array([1.0, np.nan])})
        assert ("s", 0) not in state.fitted_curves_data
        assert ("s", 1) in state.fitted_curves_data

        state.clear_cleaned_power()
        assert state.cleaned_power == {}

    def test_reset_data_clears_cleaned_layer(self):
        state = _st.AppState()
        state.cleaned_power[("s", 0)] = np.array([1.0])
        state.reset_data()
        assert state.cleaned_power == {}


class TestNaNSeeds:
    """A guess made on NaN-containing data is NaN for some models (Linear,
    Exponential); it must not abort the fit."""

    def test_nan_initial_values_are_ignored(self):

        t = np.linspace(0, 50, 400)
        y = 2.0 + np.exp(-t / 10.0)
        y[100] = np.nan
        for model in _ft.available_fit_model_list:
            if model.abbreviated_name not in ("Linear", "Exponential"):
                continue
            seeds = dict.fromkeys(model.columns[: model.n_params], np.nan)
            fit = _dm.fit_curve(t, y, model, (0, None), seeds)
            assert fit is not None, model.abbreviated_name


class TestFitResultsTablePixelColumn:
    """The Detailed Fit Results table names the pixel, not only the numeric curve_id."""

    def _gui(self, loaded_manager):
        module = _gui
        state = _st.AppState()
        dm = loaded_manager
        state.data.update(
            curves=dm.curves,
            sample_ids=dm.sample_ids,
            entries=dm.entries,
            selected_samples=list(dm.sample_ids)[:1],
        )
        return module.GUIComponents(state, dm, None), dm

    def test_not_fitted_rows_show_the_pixel_next_to_the_sample(self, loaded_manager):
        gui, dm = self._gui(loaded_manager)
        df = gui._build_full_fit_results_df()
        assert list(df.columns[:3]) == ["sample_id", "pixel", "curve_id"]
        for _, row in df.iterrows():
            assert row["pixel"] == dm.get_curve_label(dm.entries, row["sample_id"], row["curve_id"])


# ==========================================================================================
# download package
# ==========================================================================================
def test_package_is_started_as_a_download_with_a_summary(monkeypatch):
    gui = _gui
    started = []

    def fake_start(output, *args, **kwargs):
        started.append((output, args, kwargs))

    monkeypatch.setattr(gui, "start_download", fake_start)
    app_state = SimpleNamespace(
        has_curves_data=lambda: False,
        fitted_curves_data=None,
        has_selected_samples=lambda: False,
        has_fit_results=lambda: True,
        get_fit_results_count=lambda: 3,
    )
    fake = SimpleNamespace(
        app_state=app_state,
        _DOWNLOAD_STAGES=gui.GUIComponents._DOWNLOAD_STAGES,
        _add_statistical_summary_sheet=lambda writer: pd.DataFrame({"a": [1]}).to_excel(
            writer, sheet_name="Statistical_Summary"
        ),
        _add_plots_to_zip=lambda zip_file, plots_format: 0,
        _add_histograms_to_zip=lambda zip_file, plots_format: None,
        _add_readme_to_zip=lambda zip_file, counter, plots_format: None,
    )
    link = widgets.Output()
    gui.GUIComponents._create_download_package(
        fake, "html", True, True, link, widgets.Output(), widgets.IntProgress()
    )
    ((output, (content, filename, mime_type), kwargs),) = started
    assert output is link and mime_type == "application/zip"
    assert filename.startswith("MPPT_Analysis_Results_") and filename.endswith(".zip")
    assert zipfile.ZipFile(io.BytesIO(content)).namelist() == ["MPPT_Analysis_Results.xlsx"]
    assert "3 fitted curves" in kwargs["note"] and "base64" not in kwargs["note"]


# ===========================================================================
# Write-back to NOMAD, guarded (peroTF): a simulated NOMAD at the level of api_calls
# ===========================================================================


class FakeMpptNomad:
    """Uploads, entry hashes, backups, logs, edits and the processed entries."""

    def __init__(self, published=()):
        self.published = set(published)
        self.changing = set()  # entries someone edits while the app backs them up
        self.fail_backup = False
        self.readback = {}  # entry id -> processed data NOMAD serves instead
        self.reads, self.written = {}, {}
        self.events, self.backups, self.logs, self.edits = [], [], [], []

    def install(self, monkeypatch):
        monkeypatch.setattr(
            _dm,
            "get_upload",
            lambda url, token, upload_id: {"published": upload_id in self.published},
        )
        monkeypatch.setattr(_dm, "get_entry_hashes", self.get_hashes)
        monkeypatch.setattr(_dm, "download_raw_file", lambda *a: b'{"data": {"name": "x"}}')
        monkeypatch.setattr(_dm.upload_backups, "save_backup", self.save_backup)
        monkeypatch.setattr(_dm.upload_backups, "write_change_log", self.write_log)
        monkeypatch.setattr(_dm, "edit_entry", self.edit)
        monkeypatch.setattr(_dm, "get_entry_data", self.entry_data)
        return self

    def get_hashes(self, url, token, ids):
        hashes = {}
        for entry_id in ids:
            n = self.reads[entry_id] = self.reads.get(entry_id, 0) + 1
            hashes[entry_id] = f"h-{entry_id}-{n}" if entry_id in self.changing else f"h-{entry_id}"
        return hashes

    def save_backup(self, url, token, upload_id, folder, mainfile, text, stamp):
        self.events.append(("backup", mainfile))
        if self.fail_backup:
            raise RuntimeError("backup refused")
        path = f"{folder}/.{mainfile}.{stamp}.bak"
        self.backups.append((upload_id, path, text))
        return path

    def write_log(self, url, token, upload_id, folder, stamp, record, kind):
        self.logs.append((upload_id, folder, kind, record))

    def edit(self, url, token, entry_id, changes):
        self.events.append(("edit", entry_id))
        self.edits.append((entry_id, changes))
        self.written[entry_id] = {
            c["path"].removeprefix("data/results/0/"): c.get("new_value")
            for c in changes
            if c.get("action") != "remove"
        }

    def entry_data(self, url, token, entry_id):
        if entry_id in self.readback:
            return self.readback[entry_id]
        return {"results": [self.written.get(entry_id, {})]}


def _linear():
    return next(m for m in _ft.available_fit_model_list if m.name == "Linear")


def _entries_with_ids(manager, same_id=None, entry_type=None, mainfile=None):
    """The loaded entries with the metadata the write path needs (as from NOMAD)."""
    entries = manager.entries.copy()
    n = len(entries)
    entries["entry_id"] = same_id or [f"entry-{i}" for i in range(n)]
    entries["upload_id"] = "U1"
    entries["mainfile"] = mainfile or [f"mppt/m{i}.archive.json" for i in range(n)]
    entries["entry_type"] = entry_type or ENTRY_TYPE_FAMILIES["mppt"][-1]
    return entries


def _write(manager, entries, keys=None):
    keys = keys or [(sid, 0) for sid in manager.sample_ids]
    return manager.write_fit_results_to_nomad(
        entries, {key: _fit_for(_linear()) for key in keys}, "MPPT_Analysis test (me)"
    )


def test_nan_metrics_are_removed_not_written(loaded_manager, monkeypatch):
    nomad = FakeMpptNomad().install(monkeypatch)
    fit = {
        "model": _linear(),
        "time": np.array([0.0, 1.0, 2.0]),
        "params": {
            "slope": 0.1,
            "intercept": 18.0,
            "R2": 0.9,
            "T80": float("nan"),
            "T95": float("nan"),
            "Ts80": float("nan"),
            "Ts95": float("nan"),
            "tS": 0.0,
            "PCE_after_1000_h": float("nan"),
            "LEY": 12.3,
        },
        "lmfit_result": None,
    }
    entries = _entries_with_ids(loaded_manager)
    sample = loaded_manager.sample_ids.iloc[0]
    outcomes = loaded_manager.write_fit_results_to_nomad(entries, {(sample, 0): fit}, "t")
    assert outcomes[0]["success"] is True
    by_path = {c["path"]: c for c in nomad.edits[0][1]}
    assert by_path["data/results/0/T80"]["action"] == "remove"
    assert by_path["data/results/0/PCE_after_1000_h"]["action"] == "remove"
    assert by_path["data/results/0/fit_r_squared"]["new_value"] == pytest.approx(0.9)
    assert by_path["data/results/0/lifetime_energy_yield"]["new_value"] == pytest.approx(12.3)


def test_write_back_reports_a_bad_entry_and_carries_on(loaded_manager, monkeypatch):
    """A network error on one entry must not abort the loop with earlier entries written."""
    import requests

    nomad = FakeMpptNomad().install(monkeypatch)
    calls = []

    def flaky(url, token, entry_id, changes):
        calls.append(entry_id)
        if len(calls) == 1:
            raise requests.ConnectionError("network down")
        nomad.edit(url, token, entry_id, changes)

    monkeypatch.setattr(_dm, "edit_entry", flaky)
    outcomes = _write(loaded_manager, _entries_with_ids(loaded_manager))
    assert outcomes[0]["success"] is False and "network down" in outcomes[0]["message"]
    assert all(o["success"] for o in outcomes[1:])
    for _, changes in nomad.edits:  # nothing non-finite was ever sent
        for change in changes:
            value = change.get("new_value")
            assert not (isinstance(value, float) and not np.isfinite(value)), change


def test_write_back_writes_a_shared_entry_only_once(loaded_manager, monkeypatch):
    nomad = FakeMpptNomad().install(monkeypatch)
    entries = _entries_with_ids(loaded_manager, same_id="one-entry-for-every-sample")
    outcomes = _write(loaded_manager, entries)
    assert [entry_id for entry_id, _ in nomad.edits] == ["one-entry-for-every-sample"]
    assert len(nomad.backups) == 1 and all(o["success"] for o in outcomes)


def test_every_write_is_backed_up_first_in_the_entrys_own_upload_and_logged(
    loaded_manager, monkeypatch
):
    nomad = FakeMpptNomad().install(monkeypatch)
    monkeypatch.setenv("NOMAD_CLIENT_USER", "tester")
    outcomes = _write(loaded_manager, _entries_with_ids(loaded_manager))
    assert all(o["success"] and o["message"] == "OK" for o in outcomes)
    # backup then edit, entry by entry
    kinds = [kind for kind, _ in nomad.events]
    assert kinds == ["backup", "edit"] * len(outcomes)
    upload, path, text = nomad.backups[0]
    assert upload == "U1" and path.startswith("mppt_fit_backups/.mppt/m0.archive.json.")
    assert path.endswith(".bak") and text == '{"data": {"name": "x"}}'
    # only the fit results are ever written
    for _, changes in nomad.edits:
        assert all(c["path"].startswith("data/results/0/") for c in changes)
    # one log for the upload, listing every entry with its backup
    ((upload, folder, kind, record),) = nomad.logs
    assert (upload, folder, kind) == ("U1", "mppt_fit_backups", "mppt_fits")
    assert record["user"] == "tester" and len(record["entries"]) == len(outcomes)
    assert all(e["outcome"] == "verified" and e["backup"] for e in record["entries"])
    assert outcomes[0]["nomad_url"].endswith("/data/data/results/0")


def test_no_backup_means_no_write(loaded_manager, monkeypatch):
    nomad = FakeMpptNomad().install(monkeypatch)
    nomad.fail_backup = True
    outcomes = _write(loaded_manager, _entries_with_ids(loaded_manager))
    assert not any(o["success"] for o in outcomes)
    assert nomad.edits == [] and nomad.logs == []


def test_an_entry_changed_while_it_was_backed_up_is_not_written(loaded_manager, monkeypatch):
    nomad = FakeMpptNomad().install(monkeypatch)
    nomad.changing.add("entry-0")
    outcomes = _write(loaded_manager, _entries_with_ids(loaded_manager))
    assert (
        outcomes[0]["success"] is False
        and "changed while it was backed up" in outcomes[0]["message"]
    )
    assert "entry-0" not in [entry_id for entry_id, _ in nomad.edits]
    assert all(o["success"] for o in outcomes[1:])


def test_a_published_upload_is_neither_backed_up_nor_written(loaded_manager, monkeypatch):
    nomad = FakeMpptNomad(published={"U1"}).install(monkeypatch)
    outcomes = _write(loaded_manager, _entries_with_ids(loaded_manager))
    assert not any(o["success"] for o in outcomes) and "published" in outcomes[0]["message"]
    assert nomad.backups == [] and nomad.edits == []


@pytest.mark.parametrize(
    ("entry_type", "mainfile", "reason"),
    [
        ("Some_Other_Measurement", None, "not an MPPT entry"),
        (None, "run.mpp.txt", "not a NOMAD archive file"),
    ],
)
def test_only_mppt_entries_with_an_archive_file_are_written(
    loaded_manager, monkeypatch, entry_type, mainfile, reason
):
    nomad = FakeMpptNomad().install(monkeypatch)
    entries = _entries_with_ids(loaded_manager, entry_type=entry_type, mainfile=mainfile)
    outcomes = _write(loaded_manager, entries)
    assert not any(o["success"] for o in outcomes) and reason in outcomes[0]["message"]
    assert nomad.backups == [] and nomad.edits == []


def test_a_change_outside_the_fit_results_is_refused(loaded_manager, monkeypatch):
    nomad = FakeMpptNomad().install(monkeypatch)
    build = _dm.DataManager._build_fit_changes

    def sneaky(self, fit, computed_by, computed_at):
        return [
            *build(self, fit, computed_by, computed_at),
            {"path": "data/lab_id", "new_value": "x"},
        ]

    monkeypatch.setattr(_dm.DataManager, "_build_fit_changes", sneaky)
    outcomes = _write(loaded_manager, _entries_with_ids(loaded_manager))
    assert not any(o["success"] for o in outcomes) and "data/lab_id" in outcomes[0]["message"]
    assert nomad.backups == [] and nomad.edits == []


def test_the_processed_entry_is_read_back(loaded_manager, monkeypatch):
    nomad = FakeMpptNomad().install(monkeypatch)

    entries = _entries_with_ids(loaded_manager)
    second = entries.loc[(loaded_manager.sample_ids.iloc[1], 0), "entry_id"]
    nomad.readback[entries.loc[(loaded_manager.sample_ids.iloc[0], 0), "entry_id"]] = {
        "results": [{"fit_method": "Stretched Exp"}]
    }

    def unreadable(url, token, entry_id):
        if entry_id == second:
            raise RuntimeError("search index not updated yet")
        return nomad.entry_data(url, token, entry_id)

    monkeypatch.setattr(_dm, "get_entry_data", unreadable)
    outcomes = _write(loaded_manager, entries)
    assert outcomes[0]["success"] is False and "NOMAD shows" in outcomes[0]["message"]
    assert outcomes[1]["success"] is True and "could not be read back" in outcomes[1]["message"]
    record = nomad.logs[0][3]
    assert [e["outcome"] for e in record["entries"][:2]] == ["failed", "unverified"]


# ===========================================================================
# peroTF: entry types, batch list, login, version
# ===========================================================================


def test_loading_asks_for_every_mppt_class_of_this_oasis(monkeypatch):
    asked = {}

    def fake_get_all_mppt(url, token, sample_ids, mppt_type):
        asked["type"] = mppt_type
        return {}

    monkeypatch.setattr(_dm, "get_all_mppt", fake_get_all_mppt)
    _dm.DataManager("u", "t").get_mppt_data_working(["S1"])
    assert asked["type"] == ENTRY_TYPE_FAMILIES["mppt"]


def test_the_batch_list_filters_by_every_mppt_class(monkeypatch, loaded_app_state):
    seen = {}

    def batch_selection(url, token, on_load, **kwargs):
        seen.update(kwargs)
        return widgets.VBox()

    monkeypatch.setattr(_gui, "create_batch_selection", batch_selection)
    manager = _dm.DataManager("https://e.test/api", "tok")
    _gui.GUIComponents(loaded_app_state, manager, None).create_batch_tab()
    assert seen == {"filter_label": "MPPT", "filter_entry_type": ENTRY_TYPE_FAMILIES["mppt"]}


def test_without_a_login_the_batch_list_is_never_asked_for(monkeypatch, loaded_app_state):
    def must_not_query(*args, **kwargs):
        raise AssertionError("queried NOMAD without a token")

    monkeypatch.setattr(_gui, "create_batch_selection", must_not_query)
    _gui.GUIComponents(loaded_app_state, _dm.DataManager("u", None), None).create_batch_tab()


def test_the_app_starts_without_a_nomad_login(monkeypatch):
    class NoLogin:
        def __init__(self, url_base, api_endpoint):
            self.api_client = SimpleNamespace(get_api_url=lambda: "https://e.test/api")

        def authenticate_with_token(self, token):
            raise ValueError("Token not found")

    monkeypatch.setattr(_ctrl, "AuthenticationManager", NoLogin)
    monkeypatch.setattr(_ctrl, "display", lambda *a, **k: None)
    monkeypatch.setattr(_gui, "create_batch_selection", lambda *a, **k: 1 / 0)
    app = _ctrl.create_mppt_app()
    assert app.data_manager.token is None


def test_app_version_follows_the_pyproject():
    text = (Path(_gui.__file__).parent / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{_gui.APP_VERSION}"' in text


def test_entry_links_point_at_this_oasis_gui():
    from perotf_utils.config import GUI_ENDPOINT, URL_BASE

    url = _dm.DataManager("u", "t")._entry_gui_url("U1", "E1")
    assert (
        url == f"{URL_BASE}{GUI_ENDPOINT}/user/uploads/upload/id/U1/entry/id/E1/data/data/results/0"
    )
