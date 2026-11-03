"""perotf_utils.process_handling: merging the variations of a step without losing parameters."""

import ipywidgets as widgets

from perotf_utils import process_handling as ph

EVAPORATION = "nomad_perotf.schema_packages.perotf_package.Evaporation"


def source(name, thickness, **extra):
    return {
        "chemical_2": {"name": name},
        "thickness": thickness,
        "temparature": [300.0, 310.0],
        **extra,
    }


def evaporation(lab_ids, sources, position=2.0, m_def=EVAPORATION):
    return {
        "m_def": m_def,
        "name": "evaporation MAPbI3",
        "method": "Evaporation",
        "positon_in_experimental_plan": position,
        "samples": [{"lab_id": lab_id} for lab_id in lab_ids],
        "perovskite_evaporation": sources,
    }


def columns(process, sample_lists, **kwargs):
    return dict(ph.make_table(process, sample_lists, **kwargs).items())


def test_variations_with_different_source_counts_merge_into_one_step_type():
    processes = [
        evaporation(["S1"], [source("PbI2", 100.0), source("MAI", 200.0)]),
        evaporation(["S2"], [source("PbI2", 100.0), source("MAI", 250.0), source("CsI", 10.0)]),
    ]
    (merged,) = ph.merge_step_data(processes)
    table = ph.make_table(merged, [["S1"], ["S2"]])
    assert list(merged["indices"]) == [0, 1]
    assert table.loc["['S2']", "['perovskite_evaporation', '2', 'thickness']"] == 10.0
    assert table["['perovskite_evaporation', '2', 'thickness']"].isna().tolist() == [True, False]
    assert table["['perovskite_evaporation', '1', 'thickness']"].tolist() == [200.0, 250.0]


def test_field_filled_in_one_variation_only_keeps_one_value_per_row():
    processes = [
        evaporation(["S1"], [source("PbI2", 100.0)]),
        evaporation(["S2"], [source("PbI2", 120.0, pressure_start=5e-6)]),
        evaporation(["S3"], [source("PbI2", 140.0)]),
    ]
    (merged,) = ph.merge_step_data(processes)
    table = ph.make_table(merged, [["S1"], ["S2"], ["S3"]])
    assert table["['perovskite_evaporation', '0', 'thickness']"].tolist() == [100.0, 120.0, 140.0]
    pressure = table["['perovskite_evaporation', '0', 'pressure_start']"]
    assert pressure.isna().tolist() == [True, False, True]


def test_different_process_classes_stay_separate_step_types():
    processes = [
        evaporation(["S1"], [source("PbI2", 100.0)]),
        evaporation(["S2"], [source("PbI2", 100.0)], m_def="other.SpinCoating"),
    ]
    merged = ph.merge_step_data(processes)
    assert [list(group["indices"]) for group in merged] == [[0], [1]]


def test_samples_and_position_are_not_parameters():
    (merged,) = ph.merge_step_data([evaporation(["S1"], [source("PbI2", 100.0)])])
    assert "samples" not in merged["json"]
    assert "positon_in_experimental_plan" not in merged["json"]


def test_short_labels_are_unique_and_as_short_as_possible():
    keychains = [
        ["name"],
        ["layer", "0", "layer_type"],
        ["perovskite_evaporation", "0", "name"],
        ["perovskite_evaporation", "0", "thickness"],
        ["perovskite_evaporation", "1", "thickness"],
        ["perovskite_evaporation", "1", "chemical_2", "name"],
    ]
    assert ph.short_labels(keychains) == [
        "name",
        "layer_type",
        "0/name",
        "0/thickness",
        "1/thickness",
        "chemical_2/name",
    ]


def test_abbreviated_table_keeps_every_source():
    processes = [evaporation(["S1"], [source("PbI2", 100.0), source("MAI", 200.0)])]
    (merged,) = ph.merge_step_data(processes)
    table = columns(merged, [["S1"]], abbreviate_keys=True)
    assert table["0/thickness"].tolist() == [100.0]
    assert table["1/thickness"].tolist() == [200.0]


def make_batch_process(process_list):
    return ph.batch_process(
        process_list,
        {},
        "batch",
        widgets.Output(),
        widgets.Output(),
        widgets.Checkbox(value=False),
        widgets.Checkbox(value=False),
        widgets.Checkbox(value=False),
    )


def test_steps_group_by_position_even_after_a_missing_position():
    processes = [
        evaporation(["S1", "S2"], [source("PbI2", 100.0)], position=1.0),
        # no stored process at position 2 (e.g. a step type the parser skips)
        evaporation(["S1"], [source("MAI", 200.0)], position=3.0),
        evaporation(["S2"], [source("MAI", 250.0), source("CsI", 10.0)], position=3.0),
    ]
    batch = make_batch_process(processes)
    assert [len(step) for step in batch.steps] == [1, 2]
    assert len(batch.steps_merged[1]) == 1


def test_parameter_buttons_map_values_to_their_samples_and_skip_missing_ones():
    processes = [
        evaporation(["S1", "S2"], [source("MAI", 200.0)]),
        evaporation(["S3"], [source("MAI", 250.0), source("CsI", 10.0)]),
    ]
    batch = make_batch_process(processes)
    buttons = {button.description: button for button in batch.manufacturing_params[0][0]}
    assert buttons["0/thickness"].samples_values_dict == {"S1": 200.0, "S2": 200.0, "S3": 250.0}
    assert buttons["1/thickness"].samples_values_dict == {"S3": 10.0}
