"""Tests for SEM_crystal_counter (ported from HZB's four SEM test files): the grain pipeline,
cross-sections, the data manager and the GUI. Images are synthetic; never touches the network.
Clicks are simulated the way Plotly delivers them (points.xs / points.ys in pixels)."""

import io
import json
from pathlib import Path
from types import SimpleNamespace

import ipywidgets as widgets
import numpy as np
import openpyxl
import pandas as pd
import plotly.graph_objects as go
import pytest

from perotf_utils import access_token
from perotf_utils.config import ENTRY_TYPES
from perotf_utils.widget_cleanup import live_widgets

FIXTURES = Path(__file__).parent / "fixtures"

# App modules, bound from the app_loader fixture (tests/SEM_crystal_counter/conftest.py)
gc = cs = dm = pm = gui = app_module = evaluate = run_batch = training_log = None


@pytest.fixture(scope="module", autouse=True)
def _bind_app_modules(mods):
    global gc, cs, dm, pm, gui, app_module, evaluate, run_batch, training_log
    gc, cs, dm = mods["grain_core"], mods["cross_section"], mods["data_manager"]
    pm, gui, app_module = mods["plot_manager"], mods["gui_components"], mods["app"]
    evaluate, run_batch = mods["evaluate"], mods["run_batch"]
    training_log = mods["training_log"]


# ==========================================================================================
# grain_core: loading, measurement, segmentation, scoring
# ==========================================================================================
def _with_banner(height=100, width=120, banner_start=60):
    image = np.full((height, width), 128, dtype=np.uint8)
    image[banner_start : banner_start + 2] = 0  # black frame line
    image[banner_start + 2 :] = 255
    return image


def test_load_reads_pixel_size_and_crops_banner(make_tiff):
    data = make_tiff(_with_banner(), b"\x00Image Pixel Size = 2.233 nm\r\n")
    sem = gc.load_sem_tiff(data, name="VP317_01.tif")
    assert sem.pixel_size_nm == pytest.approx(2.233)
    assert sem.image.shape == (60, 120)
    assert sem.banner_rows == 40


@pytest.mark.parametrize(
    ("text", "expected"), [(b"5.583 nm", 5.583), (b"1.2 \xb5m", 1200.0), (b"800 pm", 0.8)]
)
def test_load_converts_units(make_tiff, text, expected):
    sem = gc.load_sem_tiff(make_tiff(_with_banner(), b"Image Pixel Size = " + text))
    assert sem.pixel_size_nm == pytest.approx(expected)


def test_load_without_metadata_or_banner(make_tiff):
    sem = gc.load_sem_tiff(make_tiff(np.full((50, 60), 100, dtype=np.uint8)))
    assert sem.pixel_size_nm is None
    assert sem.image.shape == (50, 60)


def test_analyze_refuses_unknown_pixel_size(make_tiff):
    sem = gc.load_sem_tiff(make_tiff(np.full((50, 60), 100, dtype=np.uint8)))
    with pytest.raises(ValueError, match="pixel size"):
        gc.analyze(sem, gc.Params())


def test_measure_grains_in_nm_and_edge_flags():
    labels = np.zeros((100, 100), dtype=np.int32)
    labels[20:40, 20:40] = 1  # interior 20x20 px
    labels[0:10, 50:60] = 2  # touches the top edge
    grains = gc.measure_grains(labels, pixel_size_nm=2.0).set_index("grain_id")
    assert grains.loc[1, "area_nm2"] == pytest.approx(400 * 4.0)
    assert not grains.loc[1, "touches_edge"]
    assert grains.loc[1, "ml_weight"] > 1
    assert grains.loc[2, "touches_edge"]
    assert np.isnan(grains.loc[2, "ml_weight"])


def test_pipeline_recovers_synthetic_grains(make_tiff, voronoi_film):
    image, truth = voronoi_film
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"), name="synthetic_01.tif")
    result = gc.analyze(sem, gc.PRESETS["smooth"])
    n_true = truth.max()
    assert abs(result.summary["n_grains"] - n_true) <= 0.2 * n_true

    centroids = pd.DataFrame(
        [(np.argwhere(truth == lab).mean(axis=0)) for lab in range(1, n_true + 1)],
        columns=["y", "x"],
    )
    centroids["unsure"] = False
    metrics = evaluate.score(result.labels, centroids, 5.0)
    assert metrics["correct_rate"] >= 0.8
    assert abs(metrics["area_error"]) <= 0.2


def test_score_counts_splits_and_merges():
    labels = np.array([[1, 1, 2, 2], [3, 3, 4, 4]], dtype=np.int32)
    points = pd.DataFrame({"x": [0, 1, 2], "y": [0, 0, 1], "unsure": [False, False, False]})
    metrics = evaluate.score(labels, points, 1.0)
    assert metrics["n_pred"] == 4
    assert metrics["merge_rate"] == pytest.approx(1 / 4)  # region 1 holds two clicks
    assert metrics["split_rate"] == pytest.approx(2 / 4)  # regions 2 and 3 hold none
    assert metrics["correct_rate"] == pytest.approx(1 / 3)


def test_sample_name_groups_replicates():
    assert gc.sample_name("VP317_01.tif") == "VP317"
    assert gc.sample_name("cs_VP352_07.tif") == "cs_VP352"
    assert gc.sample_name("single.tif") == "single"


def test_sample_name_of_files_named_for_nomad():
    """NOMAD's SEM parser links '<sample>[.<notes>].sem.tif' to the sample before the first dot."""
    assert gc.sample_name("KIT_P1_20260101_1_0_3.sem.tif") == "KIT_P1_20260101_1_0_3"
    assert gc.sample_name("KIT_P1_20260101_1_0_3.top.sem.tif") == "KIT_P1_20260101_1_0_3"
    assert gc.sample_name("KIT_P1_20260101_1_0_3.cs.SEM.TIF") == "KIT_P1_20260101_1_0_3"
    # a dot elsewhere is part of an ordinary file name
    assert gc.sample_name("S12_2.5kV_01.tif") == "S12_2.5kV"


def test_summarize_samples_uses_images_as_replicates():
    images = pd.DataFrame(
        {
            "sample": ["A", "A", "B"],
            "n_grains": [10, 20, 5],
            "grains_per_um2": [1.0, 3.0, 2.0],
            "mean_area_planimetric_nm2": [1.0, 3.0, 2.0],
            "mean_area_ml_nm2": [1.0, 3.0, 2.0],
            "median_area_nm2": [1.0, 3.0, 2.0],
            "mean_eq_diameter_nm": [1.0, 3.0, 2.0],
            "mean_intercept_nm": [1.0, 3.0, 2.0],
            "boundary_length_per_um2": [1.0, 3.0, 2.0],
        }
    )
    out = run_batch.summarize_samples(images).set_index("sample")
    assert out.loc["A", "n_images"] == 2
    assert out.loc["A", "n_grains_total"] == 30
    assert out.loc["A", "grains_per_um2_mean"] == pytest.approx(2.0)


def test_read_points_parses_fiji_results(tmp_path):

    csv = tmp_path / "img_points.csv"
    csv.write_text(" ,X,Y,Counter,Count\n1,10,20,0,1\n2,30,40,1,1\n3,50,700,0,2\n")
    points = evaluate.read_points(csv, (689, 1024), 1024)
    assert list(points["x"]) == [10, 30]  # the banner click (y=700) is dropped
    assert list(points["unsure"]) == [False, True]


def test_read_points_rejects_calibrated_units(tmp_path):

    csv = tmp_path / "img_points.csv"
    csv.write_text(" ,X,Y\n1,1500.5,20\n")
    with pytest.raises(ValueError, match="Remove Scale"):
        evaluate.read_points(csv, (689, 1024), 1024)


def test_merging_everything_into_one_region_does_not_crash(make_tiff, voronoi_film):
    image, _ = voronoi_film
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    result = gc.analyze(sem, gc.Params(merge_threshold=100.0))  # every boundary counts as weak
    assert result.summary["n_grains"] == 1


def test_featureless_image_does_not_crash(make_tiff):
    rng = np.random.default_rng(0)
    image = rng.normal(128, 3, size=(120, 160)).clip(0, 255).astype(np.uint8)
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    result = gc.analyze(sem, gc.Params(min_grain_diameter_nm=400.0))
    assert result.summary["n_grains"] <= 1


def test_auto_preset_picks_smooth_for_plain_grains(make_tiff, voronoi_film):

    image, truth = voronoi_film
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    result = gc.analyze_auto(sem)
    assert result.summary["preset"] == "smooth"
    assert result.summary["preset_ratio"] <= gc.AUTO_RATIO_THRESHOLD
    assert abs(result.summary["n_grains"] - truth.max()) <= 0.2 * truth.max()


def test_summarize_samples_drops_flagged_images_when_others_exist():
    cols = [
        "grains_per_um2",
        "mean_area_planimetric_nm2",
        "mean_area_ml_nm2",
        "median_area_nm2",
        "mean_eq_diameter_nm",
        "mean_intercept_nm",
        "boundary_length_per_um2",
    ]
    images = pd.DataFrame(
        {
            "sample": ["A", "A", "B"],
            "n_grains": [50, 4, 3],
            "reliable": [True, False, False],
            **{c: [1.0, 100.0, 7.0] for c in cols},
        }
    )
    out = run_batch.summarize_samples(images).set_index("sample")
    assert out.loc["A", "mean_area_planimetric_nm2_mean"] == pytest.approx(1.0)
    assert out.loc["A", "n_images_flagged"] == 1
    assert out.loc["B", "n_images"] == 1  # nothing reliable: keep what there is


def test_overlay_toggles_outlines_and_seeds(make_tiff, voronoi_film):

    image, _ = voronoi_film
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    result = gc.analyze(sem, gc.PRESETS["smooth"])
    plain = gc.overlay(result, show_outlines=False)
    assert np.array_equal(plain[..., 0], image)  # nothing drawn
    assert not np.array_equal(gc.overlay(result), plain)
    seeded = gc.overlay(result, show_seeds=True, show_outlines=False)
    assert (seeded == (255, 40, 40)).all(axis=-1).any()


def _two_grain_result(make_tiff):
    """A 60x80 film with a dark vertical groove at x=40: two grains, split correctly."""

    image = np.full((60, 80), 150, dtype=np.uint8)
    image[:, 39:42] = 60
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    labels = np.where(np.arange(80) < 40, 1, 2)[None, :].repeat(60, axis=0).astype(np.int32)
    bmap = (image < 100).astype(float)
    seeds = np.zeros_like(labels)
    seeds[30, 20], seeds[30, 60] = 1, 2
    grains = gc.measure_grains(labels, 5.0)
    return gc.Result(sem, gc.Params(), image / 255.0, bmap, seeds, labels, labels, grains, {})


def test_apply_edits_merges_two_clicked_grains(make_tiff):

    result = _two_grain_result(make_tiff)
    edited, warnings = gc.apply_edits(result, [{"op": "merge", "points": [[10, 10], [10, 70]]}])
    assert warnings == []
    assert edited.summary["n_grains"] == 1
    assert edited.summary["n_edits"] == 1


def test_apply_edits_split_follows_the_groove(make_tiff):

    result = _two_grain_result(make_tiff)
    merged, _ = gc.apply_edits(result, [{"op": "merge", "points": [[10, 10], [10, 70]]}])
    resplit, warnings = gc.apply_edits(merged, [{"op": "split", "point": [30, 70]}])
    assert warnings == []
    assert resplit.summary["n_grains"] == 2
    left, right = resplit.labels[30, 10], resplit.labels[30, 70]
    assert left != right
    assert (resplit.labels[:, :38] == left).all() and (resplit.labels[:, 43:] == right).all()


def test_apply_edits_reports_edits_that_no_longer_apply(make_tiff):

    result = _two_grain_result(make_tiff)
    edited, warnings = gc.apply_edits(result, [{"op": "merge", "points": [[10, 10], [20, 20]]}])
    assert len(warnings) == 1 and "same grain" in warnings[0]
    assert edited.summary["n_grains"] == 2
    assert edited.summary["n_edits_skipped"] == 1


def test_training_log_round_trip(make_tiff, tmp_path):

    result = _two_grain_result(make_tiff)
    edits = [{"op": "merge", "points": [[10, 10], [10, 70]]}]
    edited, warnings = gc.apply_edits(result, edits)
    folder = training_log.save_review(
        tmp_path, edited, edits, warnings, raw_n_grains=2, note="test"
    )
    reviews = training_log.load_reviews(tmp_path)
    assert len(reviews) == 1 and reviews[0].folder == folder
    assert reviews[0].meta["edits"] == edits
    assert reviews[0].meta["n_grains_before_edits"] == 2
    assert reviews[0].meta["n_grains_after_edits"] == 1
    assert np.array_equal(reviews[0].labels, edited.labels)
    assert training_log.find_review(tmp_path, result.sem) is not None
    training_log.save_review(tmp_path, edited, edits)  # saving again replaces, not duplicates
    assert len(training_log.load_reviews(tmp_path)) == 1


def test_params_files_with_removed_keys_still_load():
    old = '{"denoise": "gaussian", "seed_method": "hminima", "hminima_h": 0.1, "compactness": 0.01,'
    old += ' "min_grain_diameter_nm": 250.0}'
    params = gc.Params.model_validate_json(old)
    assert params.min_grain_diameter_nm == 250.0
    assert not hasattr(params, "seed_method")


def test_magnification_spread_compares_zoom_levels():

    images = pd.DataFrame(
        {
            "sample": ["A", "A", "A", "B", "B"],
            "pixel_size_nm": [2.233, 5.582, 5.583, 3.722, 3.722],
            "mean_area_planimetric_nm2": [100.0, 80.0, 120.0, 50.0, 70.0],
        }
    )
    out = run_batch.magnification_spread(images)
    # A: 2.2 -> 100, 5.6 -> mean(80, 120) = 100: the two zooms agree
    assert out.loc["A", "n_magnifications"] == 2
    assert out.loc["A", "magnification_spread"] == pytest.approx(0.0)
    assert out.loc["B", "n_magnifications"] == 1
    assert np.isnan(out.loc["B", "magnification_spread"])


def test_clicked_centres_reproduce_the_true_grains(make_tiff, voronoi_film):

    image, truth = voronoi_film
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    auto = gc.analyze(sem, gc.PRESETS["smooth"])
    centres = [tuple(np.argwhere(truth == lab).mean(axis=0)) for lab in range(1, truth.max() + 1)]
    clicked = gc.result_from_points(auto, centres)
    assert clicked.summary["n_grains"] == truth.max()
    assert clicked.summary["grain_source"] == "clicks"
    # each true grain is (almost) exactly one clicked grain: grooves are 3 px wide
    agree = (
        sum(
            np.bincount(clicked.labels[truth == lab]).max() / (truth == lab).sum()
            for lab in range(1, truth.max() + 1)
        )
        / truth.max()
    )
    assert agree > 0.95


def test_segment_from_points_handles_duplicates_and_no_clicks():

    bmap = np.zeros((20, 30))
    bmap[:, 15] = 1.0  # one vertical boundary
    seeds, labels = gc.segment_from_points(bmap, [(10, 5), (10, 5), (10, 25)])
    assert seeds.max() == 2  # the duplicate click gives one seed
    assert labels[10, 2] != labels[10, 28]
    seeds, labels = gc.segment_from_points(bmap, [])
    assert seeds.max() == 0 and (labels == 1).all()


def test_grain_centres_lie_inside_their_grains(make_tiff, voronoi_film):

    image, _ = voronoi_film
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    result = gc.analyze(sem, gc.PRESETS["smooth"])
    centres = gc.grain_centres(result)
    assert len(centres) == result.summary["n_grains"]
    hit = {int(result.labels[int(y), int(x)]) for y, x in centres}
    assert hit == set(range(1, result.summary["n_grains"] + 1))


def test_training_log_stores_clicks_as_imagej_table(make_tiff, tmp_path):

    result = _two_grain_result(make_tiff)
    clicks = [(30.0, 20.0), (30.0, 60.0)]
    clicked = gc.result_from_points(result, clicks)
    folder = training_log.save_review(tmp_path, clicked, [], points=clicks)
    points = evaluate.read_points(folder / "points.csv", (60, 80), 80)
    assert list(zip(points["y"], points["x"])) == clicks
    meta = training_log.load_reviews(tmp_path)[0].meta
    assert meta["grain_source"] == "clicks" and meta["n_clicks"] == 2
    training_log.save_review(tmp_path, result, [])  # re-saved without clicks: no stale points file
    assert not (folder / "points.csv").exists()


def test_counter_two_is_a_hole_not_a_grain(tmp_path):

    csv = tmp_path / "img_Results.csv"
    csv.write_text(" ,X,Y,Counter\n1,10,10,0\n2,30,10,1\n3,50,10,2\n")
    points = evaluate.read_points(csv, (60, 80), 80)
    assert list(points["unsure"]) == [False, True, False]
    assert list(points["hole"]) == [False, False, True]


def test_score_ignores_hole_clicks_and_hole_regions():
    labels = np.array([[1, 1, 2, 2, 3, 3]], dtype=np.int32)
    points = pd.DataFrame(
        {"x": [0, 2, 4], "y": [0, 0, 0], "unsure": [False] * 3, "hole": [False, False, True]}
    )
    metrics = evaluate.score(labels, points, 1.0)
    assert metrics["n_true"] == 2 and metrics["n_holes"] == 1
    assert metrics["n_pred"] == 2  # region 3 holds only the hole click: not a grain
    assert metrics["split_rate"] == 0.0
    assert metrics["f1"] == pytest.approx(1.0)


def test_hole_clicks_are_left_out_of_the_grains(make_tiff, voronoi_film):

    image, truth = voronoi_film
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    auto = gc.analyze(sem, gc.PRESETS["smooth"])
    centres = [tuple(np.argwhere(truth == lab).mean(axis=0)) for lab in range(1, truth.max() + 1)]
    with_hole = gc.result_from_points(auto, centres[1:], holes=[centres[0]])
    assert with_hole.summary["n_grains"] == truth.max() - 1
    assert with_hole.summary["n_holes"] == 1
    hole_fraction = (truth == 1).mean()
    assert with_hole.summary["hole_area_fraction"] == pytest.approx(hole_fraction, abs=0.01)
    assert (with_hole.labels[truth == 1] == 0).mean() > 0.95


def test_training_log_writes_holes_with_imagej_counter(make_tiff, tmp_path):

    result = _two_grain_result(make_tiff)
    clicked = gc.result_from_points(result, [(30.0, 20.0)], holes=[(30.0, 60.0)])
    folder = training_log.save_review(
        tmp_path, clicked, [], points=[(30.0, 20.0)], holes=[(30.0, 60.0)]
    )
    points = evaluate.read_points(folder / "points.csv", (60, 80), 80)
    assert list(points["hole"]) == [False, True]
    assert training_log.load_reviews(tmp_path)[0].meta["n_hole_clicks"] == 1


def test_cut_along_a_line_splits_the_crossed_grain(make_tiff):

    result = _two_grain_result(make_tiff)
    merge = {"op": "merge", "points": [[10, 10], [10, 70]]}
    cut = {"op": "cut", "points": [[0, 40], [59, 40]]}  # top border to bottom border
    edited, warnings = gc.apply_edits(result, [merge, cut])
    assert warnings == []
    assert edited.summary["n_grains"] == 2
    left, right = edited.labels[30, 10], edited.labels[30, 70]
    assert left != right
    assert (edited.labels[:, :39] == left).all() and (edited.labels[:, 42:] == right).all()


def test_cut_that_does_not_cross_a_grain_is_reported(make_tiff):

    result = _two_grain_result(make_tiff)
    inside = {"op": "cut", "points": [[20, 10], [40, 20]]}  # starts and ends inside one grain
    corner = {"op": "cut", "points": [[0, 2], [2, 0]]}  # only grazes a corner: crumbs only
    edited, warnings = gc.apply_edits(result, [inside, corner])
    assert edited.summary["n_grains"] == 2
    assert len(warnings) == 2 and all("must cross a grain" in w for w in warnings)


# ==========================================================================================
# cross_section: recognition and thickness
# ==========================================================================================
def test_cross_sections_are_recognised(cross_section, make_tiff, voronoi_film):
    image, px = cross_section(), 5.0
    side = gc.load_sem_tiff(make_tiff(image, f"Image Pixel Size = {px} nm".encode()))
    top_view = gc.load_sem_tiff(make_tiff(voronoi_film[0], b"Image Pixel Size = 5.0 nm"))
    assert cs.is_cross_section(side)
    assert not cs.is_cross_section(top_view)


def test_thickness_of_a_synthetic_film(cross_section, make_tiff):
    image = cross_section(top_row=100, film_rows=200)
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    result = cs.measure_thickness(sem)
    assert np.median(result.top) == pytest.approx(100, abs=3)
    assert np.median(result.bottom) == pytest.approx(300, abs=3)
    assert result.summary["thickness_median_nm"] == pytest.approx(1000, rel=0.03)
    assert result.summary["top_roughness_rms_nm"] < 20


def test_overlay_marks_top_and_bottom(cross_section, make_tiff):
    image = cross_section()
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    rgb = cs.overlay(cs.measure_thickness(sem))
    assert rgb.shape == (*image.shape, 3)
    assert (rgb == (255, 60, 60)).all(axis=-1).any() and (rgb == (40, 210, 255)).all(axis=-1).any()


def test_thickness_needs_a_pixel_size(cross_section, make_tiff):
    image = cross_section()
    with pytest.raises(ValueError, match="pixel size"):
        cs.measure_thickness(gc.load_sem_tiff(make_tiff(image)))


def test_measurement_overlay_is_detected():

    rng = np.random.default_rng(1)
    image = rng.normal(130, 10, (300, 400)).clip(1, 254).astype(np.uint8)
    assert not gc.has_measurement_overlay(image)
    image[50:70, 100:180] = 0  # a black label box ...
    image[56:64, 110:170:3] = 255  # ... with white text in it
    assert gc.has_measurement_overlay(image)
    dark_void = rng.normal(130, 10, (300, 400)).clip(1, 254).astype(np.uint8)
    dark_void[100:140, 100:160] = 0  # a saturated void: black, but no text
    assert not gc.has_measurement_overlay(dark_void)


def test_drawn_bottom_line_replaces_the_automatic_one(cross_section, make_tiff):
    image = cross_section(top_row=100, film_rows=200)
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    drawn = [(250, 0), (250, 499)]  # a line 50 rows above the real interface
    result = cs.measure_thickness(sem, bottom_line=drawn)
    assert (result.bottom == 250).all() and result.summary["bottom_drawn"]
    assert result.summary["thickness_median_nm"] == pytest.approx(750, rel=0.03)
    assert cs.line_from_points([(10, 5)], 20) is None  # one point is not a line


def test_cross_section_grains_stay_inside_the_film(cross_section, make_tiff):
    image = cross_section(top_row=100, film_rows=200)
    sem = gc.load_sem_tiff(make_tiff(image, b"Image Pixel Size = 5.0 nm"))
    result, thick = cs.analyze_cross_section(sem)
    film = cs.film_mask(thick)
    assert result.summary["n_grains"] > 0
    assert (result.labels[~film] == 0).all()
    assert result.summary["kind"] == "cross-section"
    assert {"width_nm", "height_nm"} <= set(result.grains.columns)


# ==========================================================================================
# data_manager: loading, analysis, corrections, tables, log
# ==========================================================================================
@pytest.fixture(scope="module")
def demo():
    manager = dm.SemDataManager()
    assert manager.load_offline(FIXTURES / "demo_images.json")
    manager.analyse_all()
    return manager


def test_demo_images_load_and_analyse(demo):
    table = demo.image_table().set_index("image")
    assert list(table.index) == ["DEMO_A_01.tif", "DEMO_A_02.tif", "DEMO_B_01.tif"]
    assert (table["status"] == "analysed").all()
    # the synthetic films have 30 grains each (DEMO_A); allow a little slack
    assert table.loc["DEMO_A_01.tif", "n_grains"] == pytest.approx(30, abs=3)
    assert table.loc["DEMO_A_01.tif", "pixel_size_nm"] == pytest.approx(3.722)


def test_sample_table_groups_images_by_sample(demo):
    samples = demo.sample_table().set_index("sample")
    assert samples.loc["DEMO_A", "n_images"] == 2
    assert samples.loc["DEMO_B", "n_images"] == 1
    assert "magnification_spread" in samples.columns


def test_results_workbook_holds_every_table(demo):

    import pandas as pd

    sheets = pd.read_excel(io.BytesIO(demo.results_workbook()), sheet_name=None)
    assert list(sheets) == list(dm.SHEETS)
    assert sheets["Cross-sections"].empty  # the demo has top views only
    grains = sheets["Grains"]
    assert {"image", "sample", "area_nm2", "eq_diameter_nm"} <= set(grains.columns)
    assert set(grains["sample"]) == {"DEMO_A", "DEMO_B"}
    assert len(grains) == len(demo.grains_table())
    assert set(sheets["Samples"]["sample"]) == {"DEMO_A", "DEMO_B"}
    assert set(sheets["Images"]["preset"]) <= {"smooth", "striped"}
    settings = sheets["Settings"].set_index("setting")
    assert settings.loc["striped.min_grain_diameter_nm", "value"] == 250.0
    assert "auto_ratio_threshold" in settings.index
    about = sheets["About"].set_index("item")
    assert about.loc["App", "value"].startswith("SEM Crystal Counter ")


def test_uploads_take_the_sample_from_the_file_name(make_tiff, voronoi_film):
    image, _ = voronoi_film
    manager = dm.SemDataManager()
    content = make_tiff(image, b"Image Pixel Size = 5.0 nm")
    manager.add_uploads([("VP999_01.tif", content), ("VP999_01.tif", content), ("bad.tif", b"x")])
    assert manager.names == ["VP999_01.tif", "VP999_01 (2).tif", "bad.tif"]
    assert manager.entries["VP999_01.tif"].sample_id == "VP999"
    assert manager.entries["bad.tif"].error.startswith("could not read")
    manager.analyse_all()
    table = manager.image_table().set_index("image")
    assert table.loc["VP999_01.tif", "status"] == "analysed"
    assert table.loc["bad.tif", "status"].startswith("could not read")


def test_nomad_load_downloads_detector_files(monkeypatch, make_tiff, voronoi_film):
    image, _ = voronoi_film
    tiff = make_tiff(image, b"Image Pixel Size = 5.0 nm")
    monkeypatch.setattr(dm, "get_ids_in_batch", lambda url, token, batches: ["S1", "S2"])
    monkeypatch.setattr(dm, "get_sample_description", lambda url, token, ids: {"S1": "dry"})
    raw = {
        "S1": [({"detector_data": ["sem/S1_a.tif", "sem/S1_b.tif"]}, {"upload_id": "U1"})],
        "S2": [({"detector_data": ["sem/S2_a.tif"]}, {"upload_id": "U2"})],
    }
    monkeypatch.setattr(dm, "get_all_eqe", lambda url, token, ids, eqe_type: raw)
    fetched = []

    def fake_download(url, token, upload_id, path):
        fetched.append((upload_id, path))
        if path.endswith("S1_b.tif"):
            raise OSError("404 not found")
        return tiff

    monkeypatch.setattr(dm, "download_raw_file", fake_download)
    manager = dm.SemDataManager("https://e.test/api", "tok")
    assert manager.load(["B1"]) == 3
    assert fetched == [("U1", "sem/S1_a.tif"), ("U1", "sem/S1_b.tif"), ("U2", "sem/S2_a.tif")]
    entry = manager.entries["S1_a.tif"]
    assert (entry.sample_id, entry.variation, entry.source) == ("S1", "dry", "nomad")
    assert manager.entries["S1_b.tif"].error.startswith("could not load")  # others still load
    assert manager.entries["S2_a.tif"].sem is not None


def test_click_mode_and_edits_are_kept_per_image(demo):
    name = "DEMO_A_01.tif"
    auto = demo.final_result(name)[0].summary["n_grains"]
    demo.set_click_mode(name, True)
    demo.start_clicks_from_automatic(name)
    assert demo.final_result(name)[0].summary["n_grains"] == auto
    entry = demo.entries[name]
    y, x, _ = entry.clicks[0]
    assert demo.toggle_click(name, y + 2, x + 2) == "removed"  # click near a dot removes it
    assert demo.final_result(name)[0].summary["n_grains"] == auto - 1
    assert demo.toggle_click(name, y, x, kind=dm.HOLE) == "added"
    assert demo.final_result(name)[0].summary["n_holes"] == 1
    demo.undo(name)
    assert len(entry.clicks) == auto - 1
    demo.set_click_mode(name, False)  # back to automatic: clicks stay stored but unused
    assert demo.final_result(name)[0].summary["n_grains"] == auto
    assert demo.image_table().set_index("image").loc[name, "corrected"] == ""


def test_merge_edit_reduces_grains_and_shows_as_corrected(demo):
    name = "DEMO_A_02.tif"
    result, _ = demo.final_result(name)
    labels = result.labels
    a = np.argwhere(labels == 1)[len(np.argwhere(labels == 1)) // 2]
    neighbour = next(
        lab
        for lab in range(2, labels.max() + 1)
        if (np.abs(np.argwhere(labels == lab)[:, None] - a).sum(-1).min()) < 60
    )
    b = np.argwhere(labels == neighbour)[0]
    demo.add_edit(name, {"op": "merge", "points": [a.tolist(), b.tolist()]})
    assert demo.final_result(name)[0].summary["n_grains"] == result.summary["n_grains"] - 1
    assert demo.image_table().set_index("image").loc[name, "corrected"] == "edits"
    demo.clear_corrections(name)
    assert demo.final_result(name)[0].summary["n_grains"] == result.summary["n_grains"]


def test_save_review_writes_to_the_shared_training_log(demo, monkeypatch, tmp_path):
    monkeypatch.setattr(dm, "training_log_dir", lambda: tmp_path)
    name = "DEMO_B_01.tif"
    demo.set_click_mode(name, True)
    demo.start_clicks_from_automatic(name)
    folder = demo.save_review(name, note="demo")
    review = json.loads((folder / "review.json").read_text(encoding="utf-8"))
    assert review["grain_source"] == "clicks" and review["note"] == "demo"
    assert (folder / "points.csv").exists()
    demo.set_click_mode(name, False)


def test_training_log_dir_sits_next_to_the_usage_logs(monkeypatch, tmp_path):
    assert dm.training_log_dir() == access_token.usage_log_dir() / "sem_training_log"
    monkeypatch.setattr(dm, "usage_log_dir", lambda: tmp_path)
    assert dm.training_log_dir() == tmp_path / "sem_training_log"


def test_workbook_with_chosen_sheets_only(demo):

    import pandas as pd

    sheets = pd.read_excel(
        io.BytesIO(demo.results_workbook(["Samples", "Grains"])), sheet_name=None
    )
    assert list(sheets) == ["Samples", "Grains"]
    with pytest.raises(ValueError):
        demo.results_workbook([])


@pytest.fixture
def mixed(make_tiff, voronoi_film, cross_section):
    """A top view and a synthetic cross-section (film rows 100-300, 5 nm/px), analysed."""
    manager = dm.SemDataManager()
    meta = b"Image Pixel Size = 5.0 nm"
    manager.add_uploads(
        [
            ("VP1_01.tif", make_tiff(voronoi_film[0], meta)),
            ("VP1_cs.tif", make_tiff(cross_section(top_row=100, film_rows=200), meta)),
        ]
    )
    manager.analyse_all()
    return manager


def test_cross_sections_are_recognised_and_kept_apart(mixed):
    assert mixed.entries["VP1_01.tif"].kind == dm.TOP
    assert mixed.entries["VP1_cs.tif"].kind == dm.CROSS
    images = mixed.image_table().set_index("image")
    assert images.loc["VP1_cs.tif", "kind"] == "cross-section"
    assert images.loc["VP1_cs.tif", "thickness_median_nm"] == pytest.approx(1000, rel=0.05)
    # top-view statistics leave the cross-section out
    assert mixed.sample_table()["n_images"].tolist() == [1]
    assert set(mixed.grains_table(dm.TOP)["image"]) == {"VP1_01.tif"}
    cross = mixed.cross_section_table().set_index("image")
    assert list(cross.index) == ["VP1_cs.tif"]
    assert cross.loc["VP1_cs.tif", "film_bottom"] == "automatic"
    assert cross.loc["VP1_cs.tif", "n_grains"] > 0
    profiles = mixed.thickness_profiles()
    assert len(profiles) == 500 and profiles["thickness_nm"].median() == pytest.approx(
        1000, rel=0.05
    )
    samples = mixed.cross_sample_table().set_index("sample")
    assert samples.loc["VP1", "thickness_p10_nm"] <= samples.loc["VP1", "thickness_p90_nm"]


def test_cross_section_corrections_stay_inside_the_film(mixed):
    name = "VP1_cs.tif"
    film = mixed.film(name)
    mixed.set_click_mode(name, True)
    mixed.start_clicks_from_automatic(name)
    mixed.add_click(name, 20, 250)  # a click in the vacuum above the film
    result, _ = mixed.final_result(name)
    assert (result.labels[~film] == 0).all()
    assert result.summary["kind"] == "cross-section"
    mixed.set_click_mode(name, False)


def test_drawn_bottom_and_image_type_change(mixed):
    name = "VP1_cs.tif"
    mixed.set_bottom_line(name, [(250, 0), (250, 499)])  # 50 rows above the real interface
    summary = mixed.final_result(name)[0].summary
    assert summary["bottom_drawn"] and summary["thickness_median_nm"] == pytest.approx(
        750, rel=0.05
    )
    settings = mixed.settings_table().set_index("setting")
    assert f"{name}: film bottom" in settings.index
    assert "cross-section.min_grain_diameter_nm" in settings.index
    mixed.set_bottom_line(name, [])
    assert mixed.final_result(name)[0].summary["thickness_median_nm"] == pytest.approx(
        1000, rel=0.05
    )
    mixed.set_kind(name, dm.TOP)
    entry = mixed.entries[name]
    assert entry.kind == dm.TOP and entry.thickness is None and entry.analysed
    assert mixed.cross_section_table().empty


def test_images_with_drawn_measurements_start_ignored(make_tiff, voronoi_film):
    image = voronoi_film[0].copy()
    image[50:70, 100:180] = 0  # a black label box of the SEM software ...
    image[56:64, 110:170:3] = 255  # ... with white text
    manager = dm.SemDataManager()
    manager.add_uploads([("VP2_01.tif", make_tiff(image, b"Image Pixel Size = 5.0 nm"))])
    entry = manager.entries["VP2_01.tif"]
    assert entry.has_overlay and entry.ignored
    row = manager.image_table().iloc[0]
    assert row["status"] == "ignored" and row["note"] == dm.OVERLAY_NOTE


def test_results_workbook_keeps_formula_like_text_as_text(demo, monkeypatch):

    import pandas as pd

    monkeypatch.setattr(demo, "settings_table", lambda: pd.DataFrame({"item": ["=1+1"]}))
    sheet = openpyxl.load_workbook(io.BytesIO(demo.results_workbook()))["Settings"]
    assert (sheet["A2"].value, sheet["A2"].data_type) == ("=1+1", "s")


# ==========================================================================================
# plots, GUI panels and app assembly
# ==========================================================================================


@pytest.fixture(scope="module")
def app_demo():
    manager = dm.SemDataManager()
    manager.load_offline(FIXTURES / "demo_images.json")
    manager.analyse_all()
    return manager


def _click(panel, y, x, ctrl=False):
    """A Plotly click at pixel (y, x), as delivered to the trace's on_click callback."""
    panel._on_figure_click(None, SimpleNamespace(xs=[x], ys=[y]), SimpleNamespace(ctrl=ctrl))


def test_overlay_figure_keeps_pixel_coordinates():
    rgb = np.zeros((100, 200, 3), dtype=np.uint8)
    fig = pm.overlay_figure(rgb)
    assert fig.data[0].source.startswith("data:image/png;base64,")
    # autorange (not fixed ranges), so a double-click returns to this image's full extent
    assert fig.layout.xaxis.autorange is True
    assert fig.layout.yaxis.autorange == "reversed"  # rows grow downwards, like the image


def test_result_plots_and_empty_states(app_demo):
    assert pm.size_histogram(app_demo.grains_table()).data
    assert pm.sample_bars(app_demo.sample_table()).data
    assert pm.size_histogram(app_demo.grains_table().iloc[:0]).layout.annotations
    assert pm.sample_bars(app_demo.sample_table().iloc[:0]).layout.annotations


def test_review_panel_click_mode_adds_holes_and_removes_dots(app_demo):
    panel = gui.ReviewPanel(app_demo, on_changed=lambda: None)
    panel.refresh()
    name = "DEMO_A_01.tif"
    panel._image.value = name
    panel._source.value = gui.CLICKS  # switching starts from the automatic grains
    entry = app_demo.entries[name]
    n_auto = len(entry.clicks)
    assert entry.use_clicks and n_auto > 0
    panel._action.value = "adds a hole"
    _click(panel, 5, 5)
    assert entry.clicks[-1][2] == dm.HOLE
    _click(panel, 5, 5)  # a second click on the dot adds nothing (no duplicate dots)
    assert len(entry.clicks) == n_auto + 1
    _click(panel, 6, 6, ctrl=True)  # ctrl+click removes the nearest dot
    assert len(entry.clicks) == n_auto
    panel._action.value = "removes a dot"
    y, x, _ = entry.clicks[0]
    _click(panel, int(y), int(x))
    assert len(entry.clicks) == n_auto - 1
    assert "grain clicks" in panel._info.value
    panel._source.value = gui.AUTO
    assert not entry.use_clicks


def test_review_panel_merge_needs_two_clicks(app_demo):
    panel = gui.ReviewPanel(app_demo, on_changed=lambda: None)
    panel.refresh()
    name = "DEMO_A_02.tif"
    panel._image.value = name
    panel._action.value = "merges two grains"
    labels = app_demo.final_result(name)[0].labels
    first = np.argwhere(labels == 1)[0]
    other = next(lab for lab in range(2, labels.max() + 1) if (labels == lab).any())
    second = np.argwhere(labels == other)[0]
    _click(panel, *first)
    assert panel._pending is not None and not app_demo.entries[name].edits
    _click(panel, *second)
    assert app_demo.entries[name].edits[-1]["op"] == "merge"
    panel._undo(None)
    assert not app_demo.entries[name].edits


def test_analysis_panel_refresh_and_download(app_demo, monkeypatch):
    shown = []
    monkeypatch.setattr(gui, "ipydisplay", shown.append)  # Output() captures nothing here
    panel = gui.AnalysisPanel(app_demo)
    panel.refresh()
    assert any(getattr(x, "value", None) == "<h4>Samples</h4>" for x in shown)
    tables = [x.data for x in shown if "<table" in str(getattr(x, "data", ""))]
    assert len(tables) == 2 and "Mean diameter (nm)" in tables[0]  # plain HTML, no Styler
    downloads = []
    monkeypatch.setattr(gui, "start_download", lambda *args: downloads.append(args))
    panel._download_results()
    ((output, content, filename, mime),) = downloads
    assert output is panel._downloads  # an Output in the displayed tree (Voila)
    assert filename.startswith("sem_results_") and filename.endswith(".xlsx")
    assert mime.endswith("spreadsheetml.sheet") and content[:2] == b"PK"


def _thermo_tiff(height=110, image_rows=100, pixel_width="4.13411e-09"):
    """A TIFF laid out like a Thermo Fisher Apreo file: INI text metadata, a data bar below
    ResolutionY without a black frame line."""
    from PIL import Image

    pixels = np.full((height, 80), 120, dtype=np.uint8)
    pixels[image_rows:] = 60  # data bar
    text = (
        "[User]\r\nUserText=Apreo\r\n\r\n[Image]\r\nResolutionX=80\r\n"
        f"ResolutionY={image_rows}\r\n\r\n[Scan]\r\nPixelWidth={pixel_width}\r\n"
        f"PixelHeight={pixel_width}\r\n"
    )
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="TIFF", tiffinfo={270: text})
    return buffer.getvalue()


def test_thermo_fisher_tiffs_give_pixel_size_and_lose_the_data_bar():
    sem = gc.load_sem_tiff(_thermo_tiff(), "apreo.tif")
    assert sem.pixel_size_nm == pytest.approx(4.13411)
    assert sem.image.shape == (100, 80)
    assert sem.banner_rows == 10
    assert sem.meta["pixel_size_raw"] == "PixelWidth=4.13411e-09"


def test_a_white_zeiss_banner_behind_an_almost_black_line_is_cut_off():
    """Seen on KIT Zeiss files: a white banner with black text boxes below a frame line that
    holds one stray grey pixel. It stayed in the image and its text boxes made the image count
    as one with drawn-in measurements, so it was ignored."""
    from PIL import Image

    rng = np.random.default_rng(0)
    pixels = rng.integers(60, 200, size=(200, 300), dtype=np.uint8)
    pixels[150] = 0
    pixels[150, 299] = 91  # the stray pixel
    pixels[151:] = 255  # white banner
    pixels[160:185, 20:80] = 0  # black text box ...
    pixels[165:180, 30:70:4] = 255  # ... with white text
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(
        buffer, format="TIFF", tiffinfo={270: "CZ_SEM\r\nImage Pixel Size = 3.4 nm\r\n"}
    )
    sem = gc.load_sem_tiff(buffer.getvalue(), "zeiss.tif")
    assert sem.image.shape == (150, 300)
    assert sem.banner_rows == 50
    assert not gc.has_measurement_overlay(sem.image)


def test_a_thermo_tiff_without_pixel_width_has_no_pixel_size():
    sem = gc.load_sem_tiff(_thermo_tiff(pixel_width=""), "apreo.tif")
    assert sem.pixel_size_nm is None


def test_analysis_panel_refresh_without_a_reliable_column(app_demo, monkeypatch):
    """Images loaded but not analysed yet have no "reliable" column; refresh crashed on it
    with KeyError: False (seen in NORTH, 2026-11-18)."""
    shown = []
    monkeypatch.setattr(gui, "ipydisplay", shown.append)
    images = app_demo.image_table().drop(columns="reliable", errors="ignore")
    monkeypatch.setattr(app_demo, "image_table", lambda: images)
    gui.AnalysisPanel(app_demo).refresh()
    assert any(getattr(x, "value", None) == "<h4>Images</h4>" for x in shown)
    assert not any("fewer than" in str(getattr(x, "value", "")) for x in shown)


def test_app_demo_load_end_to_end(monkeypatch):
    class FakeAuth:
        def __init__(self, url_base, api_endpoint):
            self.api_client = SimpleNamespace(get_api_url=lambda: "https://e.test/api")
            self.current_token = "tok"

        def authenticate_with_token(self, token):
            return token

    monkeypatch.setattr(app_module, "AuthenticationManager", FakeAuth)
    monkeypatch.setattr(
        gui,
        "create_batch_selection",
        lambda url, token, on_load, **kw: widgets.VBox([widgets.SelectMultiple(options=["B1"])]),
    )
    sem_app = app_module.SEMApp("https://e.test", "/api", "tok")
    sem_app._on_demo_load(None)
    assert len(sem_app._dm.entries) == 3
    assert all(e.analysed for e in sem_app._dm.entries.values())
    assert list(sem_app._review._image.options) == sem_app._dm.names


def test_app_still_works_when_nomad_is_unreachable(monkeypatch):
    class FakeAuth:
        def __init__(self, url_base, api_endpoint):
            self.api_client = SimpleNamespace(get_api_url=lambda: "https://e.test/api")
            self.current_token = "expired"

        def authenticate_with_token(self, token):
            return token

    def refuse(url, token, on_load, **kw):
        raise PermissionError("401 Unauthorized")

    monkeypatch.setattr(app_module, "AuthenticationManager", FakeAuth)
    monkeypatch.setattr(gui, "create_batch_selection", refuse)
    sem_app = app_module.SEMApp("https://e.test", "/api", "expired")
    assert "Could not get the batch list" in sem_app._sources.children[0].value
    sem_app._on_demo_load(None)  # demo (and upload) still work
    assert len(sem_app._dm.entries) == 3


def test_app_without_a_nomad_login_still_offers_upload_and_demo(monkeypatch):
    """Outside NORTH under Voila there is no token and no login prompt: the app must still
    start, say why the NOMAD tab is empty and never query NOMAD with no token."""

    class NoLogin:
        def __init__(self, url_base, api_endpoint):
            self.api_client = SimpleNamespace(get_api_url=lambda: "https://e.test/api")

        def authenticate_with_token(self, token):
            raise ValueError("Token not found")

    def must_not_query(*args, **kwargs):
        raise AssertionError("queried NOMAD without a token")

    monkeypatch.setattr(app_module, "AuthenticationManager", NoLogin)
    monkeypatch.setattr(gui, "create_batch_selection", must_not_query)
    sem_app = app_module.SEMApp()
    assert "Not logged in to NOMAD" in sem_app._sources.children[0].value
    sem_app._on_demo_load(None)
    assert len(sem_app._dm.entries) == 3


def test_the_batch_list_offers_the_sem_only_filter(monkeypatch):
    seen = {}

    def batch_selection(url, token, on_load, **kwargs):
        seen.update(kwargs, url=url, token=token)
        return widgets.VBox()

    monkeypatch.setattr(gui, "create_batch_selection", batch_selection)
    gui.BatchFilterPanel("https://e.test/api", "tok", lambda selector: None)
    assert seen["filter_label"] == "SEM"
    assert seen["filter_entry_type"] == dm.MEASUREMENT_TYPE == ENTRY_TYPES["sem"]


def test_whole_image_button_resets_the_zoom(app_demo):
    panel = gui.ReviewPanel(app_demo, on_changed=lambda: None)
    panel.refresh()
    panel._figure.layout.xaxis.range = [10, 50]  # as after zooming in
    panel._whole_btn.click()
    x0, x1 = panel._figure.layout.xaxis.range
    assert x0 == pytest.approx(-0.5, abs=1e-3) and x1 == 640 - 0.5  # the demo images are 640 wide
    first = tuple(panel._figure.layout.xaxis.range)
    panel._whole_btn.click()  # a second reset is still a change, so the browser gets it
    assert tuple(panel._figure.layout.xaxis.range) != first


def test_navigation_counter_and_ignore(app_demo):
    panel = gui.ReviewPanel(app_demo, on_changed=lambda: None)
    panel.refresh()
    panel._image.value = app_demo.names[0]
    assert panel._counter.value == "1 / 3"
    panel._step(1)
    assert panel._image.value == app_demo.names[1] and panel._counter.value == "2 / 3"
    panel._step(-2)  # wraps around to the last image
    assert panel._counter.value == "3 / 3"
    name = panel._image.value
    panel._ignore.value = True
    assert app_demo.entries[name].ignored
    assert name not in set(app_demo.grains_table()["image"])
    assert "ignored" in panel._info.value
    panel._ignore.value = False
    assert name in set(app_demo.grains_table()["image"])


def test_cut_needs_two_clicks_across_a_grain(app_demo):
    panel = gui.ReviewPanel(app_demo, on_changed=lambda: None)
    panel.refresh()
    name = "DEMO_A_02.tif"
    panel._image.value = name
    panel._source.value = gui.AUTO
    panel._action.value = "cuts along a line"
    before = app_demo.final_result(name)[0].summary["n_grains"]
    labels = app_demo.final_result(name)[0].labels
    ys, xs = np.nonzero(labels == np.argmax(np.bincount(labels.ravel())))  # largest grain
    row = int(np.median(ys))
    cols = xs[ys == row]
    _click(panel, row, int(cols.min()) - 3)  # just outside its left border ...
    assert panel._pending is not None and not app_demo.entries[name].edits
    _click(panel, row, int(cols.max()) + 3)  # ... to just outside its right border
    assert app_demo.entries[name].edits[-1]["op"] == "cut"
    assert app_demo.final_result(name)[0].summary["n_grains"] == before + 1
    app_demo.clear_corrections(name)


def test_detection_settings_re_analyse_one_image(app_demo):
    panel = gui.ReviewPanel(app_demo, on_changed=lambda: None)
    panel.refresh()
    name = "DEMO_A_01.tif"
    panel._image.value = name
    before = app_demo.final_result(name)[0].summary["n_grains"]
    panel._sliders["min_grain_diameter_nm"].value = 400.0
    panel._apply_settings(all_images=False)
    entry = app_demo.entries[name]
    assert entry.overrides == {"min_grain_diameter_nm": 400.0}
    assert app_demo.final_result(name)[0].summary["n_grains"] < before
    assert "own settings" in app_demo.image_table().set_index("image").loc[name, "preset"]
    panel._reset_settings()
    assert entry.overrides == {}
    assert app_demo.final_result(name)[0].summary["n_grains"] == before


def test_ruler_measures_in_nm(app_demo):
    panel = gui.ReviewPanel(app_demo, on_changed=lambda: None)
    panel.refresh()
    panel._image.value = "DEMO_A_01.tif"  # 3.722 nm/px
    panel._action.value = gui.RULER
    edits = list(app_demo.entries["DEMO_A_01.tif"].edits)
    _click(panel, 10, 10)
    assert "second point" in panel._ruler_info.value
    _click(panel, 10, 110)
    assert "Ruler: 372 nm" in panel._ruler_info.value
    assert app_demo.entries["DEMO_A_01.tif"].edits == edits  # the grains are not touched
    _click(panel, 50, 50)  # a third click starts a new measurement
    assert panel._ruler == [(50, 50)]
    panel._undo(None)
    assert panel._ruler == [] and panel._ruler_info.value == ""


def test_review_of_a_cross_section_draws_the_film_bottom(make_tiff, cross_section, monkeypatch):
    manager = dm.SemDataManager()
    content = make_tiff(cross_section(top_row=100, film_rows=200), b"Image Pixel Size = 5.0 nm")
    manager.add_uploads([("VP3_cs.tif", content)])
    manager.analyse_all()
    panel = gui.ReviewPanel(manager, on_changed=lambda: None)
    panel.refresh()
    assert panel._kind.value == dm.CROSS and gui.BOTTOM in panel._action.options
    assert "Thickness 1" in panel._info.value  # about 1000 nm
    panel._action.value = gui.BOTTOM
    panel._bottom_apply_btn.click()  # no points yet: nothing happens
    assert manager.entries["VP3_cs.tif"].bottom_points == []
    _click(panel, 250, 0)
    _click(panel, 250, 499)
    panel._bottom_apply_btn.click()
    summary = manager.final_result("VP3_cs.tif")[0].summary
    assert summary["bottom_drawn"] and "film bottom drawn" in panel._info.value
    panel._bottom_auto_btn.click()
    assert not manager.final_result("VP3_cs.tif")[0].summary["bottom_drawn"]

    shown = []
    monkeypatch.setattr(gui, "ipydisplay", shown.append)
    gui.CrossSectionPanel(manager).refresh()
    tables = [x.data for x in shown if "<table" in str(getattr(x, "data", ""))]
    assert len(tables) == 2 and "Thickness, median (nm)" in tables[0]
    assert any(isinstance(x, go.FigureWidget) for x in shown)  # histogram and profile plots

    panel._kind.value = dm.TOP  # the user says it is a top view
    assert manager.entries["VP3_cs.tif"].kind == dm.TOP
    assert gui.BOTTOM not in panel._action.options


def test_thickness_profile_does_not_need_webgl():
    import pandas as pd

    profiles = pd.DataFrame(
        {"image": "a.tif", "x_nm": np.arange(2048.0), "thickness_nm": np.full(2048, 500.0)}
    )
    # above 1000 points plotly express would pick scattergl, which fails without WebGL
    assert {t.type for t in pm.thickness_profile(profiles).data} == {"scatter"}


def test_detection_settings_start_open(app_demo):
    assert gui.ReviewPanel(app_demo, on_changed=lambda: None)._settings.selected_index == 0


@pytest.mark.parametrize("panel_class", ["AnalysisPanel", "CrossSectionPanel"])
def test_refresh_closes_the_tables_and_figures_it_replaces(app_demo, panel_class):
    """clear_output only hides widgets; each refresh would keep every old figure alive."""
    panel = getattr(gui, panel_class)(app_demo)
    panel.refresh()
    first = {model_id for ids in panel._shown.values() for model_id in ids}
    assert first
    panel.refresh()
    assert not first & set(live_widgets())  # closed
    assert all(set(ids) <= set(live_widgets()) for ids in panel._shown.values())
