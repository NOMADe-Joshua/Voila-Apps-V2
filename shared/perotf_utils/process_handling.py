# --file contents--
# classes and methods for handling, grouping and visualizing data about manufacturing steps

import itertools
import json

import ipywidgets as widgets
import numpy as np
import pandas as pd
from IPython.display import HTML, display


class NpEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return str(o)
        if isinstance(o, np.bool_):
            return bool(o)
        return super(NpEncoder, self).default(o)


# class to hold data about production steps and samples in a batch and provide visualization
class batch_process(widgets.GridBox):
    # constructur arguments:
    # process_list: list of process entries related to the samples in the relevant batch
    # efficiencies: dict containg key value pairs lab_id:efficiency
    # batch_name: name of the batch unused, was intended to be shown in the gui
    # detail_widget: should be an output widget, will be used to display tables with manufacturing parameters
    # parameter_widget: output widget used for the overview of selected parameters
    # exclude_constants, exclude_strings, abbreviate_keys: objects with a boolean .value attribute, selects which parameters are shown in the table
    def __init__(
        self,
        process_list,
        efficiencies,
        batch_name,
        detail_widget,
        parameter_widget,
        exclude_constants,
        exclude_strings,
        abbreviate_keys,
    ):
        self.name = batch_name
        self.detail_widget = detail_widget
        self.parameter_widget = parameter_widget
        self.efficiencies = efficiencies

        self.exclude_constants = exclude_constants
        self.exclude_strings = exclude_strings
        self.abbreviate_keys = abbreviate_keys

        # procedure relies on steps being ordered by "position_in_experimental_plan"
        # result should be a list where the n-th entry is a list of all processes that were performed n-th in the production.
        # Grouped by equal position, so a position without any stored process (e.g. a step type the
        # experiment parser skips) does not split the variations of the following steps.
        steps = [
            list(group)
            for _position, group in itertools.groupby(
                process_list, key=lambda step: step["positon_in_experimental_plan"]
            )
        ]

        self.steps = steps
        self.steps_merged = list(map(lambda x: merge_step_data(x), steps))

        # create overview widgets
        def create_step_description(i):
            if len(self.steps[i]) == 1:
                label = widgets.Label(
                    value=f"{int(self.steps[i][0]['positon_in_experimental_plan'])} {self.steps[i][0]['name']}"
                )
            elif len(self.steps_merged[i]) == 1:
                label = widgets.Label(
                    value=f"{int(self.steps[i][0]['positon_in_experimental_plan'])} {self.steps[i][0]['name']}, {len(self.steps[i])} variations",
                    style={"text_color": "blue"},
                )
            else:
                label = widgets.Label(
                    value=f"{int(self.steps[i][0]['positon_in_experimental_plan'])} {len(self.steps_merged[i])} different step types",
                    style={"text_color": "red"},
                )

            button = widgets.Button(description="details", layout={"width": "100px"})
            button.on_click(lambda b: self.show_process_details(i))

            return [label, button]

        super().__init__(
            list(
                itertools.chain.from_iterable(map(create_step_description, range(len(self.steps))))
            ),
            layout=widgets.Layout(grid_template_columns="3fr 1fr", border="1px solid black"),
        )

        # create the parameter selection widgets
        def param_selection_buttons(step_index):
            sample_ids_nested = self.samples_for_processes_in_step(step_index)

            def process_buttons(process):
                column_data = flatten_layers(process["json"], [], False, False)
                labels = short_labels([keychain for keychain, _values in column_data])
                return [
                    manufacturing_parameter(
                        keychain,
                        [sample_ids_nested[idx] for idx in process["indices"]],
                        values,
                        self.refresh_selected_parameter_overview,
                        label=label,
                    )
                    for (keychain, values), label in zip(column_data, labels)
                ]

            return [process_buttons(process) for process in self.steps_merged[step_index]]

        self.manufacturing_params = list(
            map(param_selection_buttons, range(len(self.steps_merged)))
        )

    def show_process_details(self, step_index):
        self.detail_widget.clear_output()
        sample_lists = self.samples_for_processes_in_step(step_index)
        with self.detail_widget:
            for process_idx, process in enumerate(self.steps_merged[step_index]):
                display(
                    HTML(
                        make_table(
                            process,
                            sample_lists,
                            remove_constants=self.exclude_constants.value,
                            remove_string=self.exclude_strings.value,
                            abbreviate_keys=self.abbreviate_keys.value,
                        ).to_html(na_rep="")
                    )
                )
                display(
                    widgets.GridBox(
                        self.manufacturing_params[step_index][process_idx],
                        layout=widgets.Layout(grid_template_columns="repeat(10, 1fr)"),
                    )
                )

    def samples_for_processes_in_step(self, step_index):
        return list(
            map(
                lambda process: list(
                    map(lambda sample: sample.get("lab_id", "id not found"), process["samples"])
                ),
                self.steps[step_index],
            )
        )

    def refresh_selected_parameter_overview(self, triggering_button):
        with self.parameter_widget:
            self.parameter_widget.clear_output()
            display(
                widgets.GridBox(
                    list(
                        filter(
                            lambda button: button.value,
                            itertools.chain.from_iterable(
                                itertools.chain.from_iterable(self.manufacturing_params)
                            ),
                        )
                    ),
                    layout=widgets.Layout(
                        grid_template_columns="repeat(10, 1fr)", border="1px solid black"
                    ),
                )
            )

    def get_selected_manufacturing_parameters(
        self, only_samples_with_efficiencies=True, only_samples_with_all_values=True
    ):
        datapoints_dict = {}
        parameter_name_list = []
        for parameter_object in filter(
            lambda x: x.value,
            itertools.chain.from_iterable(itertools.chain.from_iterable(self.manufacturing_params)),
        ):
            parameter_name_list.append(parameter_object.description)
            for sample_id in filter(
                lambda x: bool(x in self.efficiencies or not only_samples_with_efficiencies),
                parameter_object.samples_values_dict,
            ):
                if sample_id not in datapoints_dict:
                    datapoints_dict[sample_id] = {}
                datapoints_dict[sample_id][parameter_object.description] = (
                    parameter_object.samples_values_dict[sample_id]
                )
        if only_samples_with_all_values:
            filtered_dict = {}
            for sample_id in datapoints_dict:
                if list(datapoints_dict[sample_id].keys()) == parameter_name_list:
                    filtered_dict[sample_id] = datapoints_dict[sample_id]
            return filtered_dict
        else:
            return datapoints_dict


class manufacturing_parameter(widgets.ToggleButton):
    # sample_ids should be a list of lists where the ith list contains all sample ids for which the ith value was used
    # label: button text, defaults to the last key; samples without a value (None) are left out
    def __init__(self, keychain, sample_ids_nested, values, update_callback, label=None):
        super().__init__(description=label or str(keychain[-1]))
        self.keychain = keychain
        self.value = False
        self.samples_values_dict = {
            sample_id: values[idx]
            for idx, sample_ids in enumerate(sample_ids_nested)
            if values[idx] is not None
            for sample_id in sample_ids
        }
        self.observe(update_callback)


_MISSING = object()  # marks a process that has no value at a path, unlike a stored value


def process_type(process):
    """Key that decides which processes of one step are variations of the same step type."""
    return process.get("m_def") or process.get("method") or ""


def merge_step_data(initial_process_list, exclude_non_numeric=False, blacklist=()):
    ignored_keys = ["samples", "positon_in_experimental_plan", *blacklist]
    process_list = [
        {key: value for key, value in unfiltered_process.items() if key not in ignored_keys}
        for unfiltered_process in initial_process_list
    ]
    groups = {}
    for index, process in enumerate(process_list):
        groups.setdefault(process_type(process), []).append(index)
    merged = []
    for indices in groups.values():
        json_data = _merge_values([process_list[i] for i in indices], exclude_non_numeric)
        merged.append(
            {"indices": np.array(indices), "json": {} if json_data is None else json_data}
        )
    return merged


# takes a list of json objects (the processes of one step type).
# they are "merged" into a single object where the endpoints are arrays with one value per process:
# the union of all keys and list entries is kept, a process without a value at a path gets None there,
# so variations that leave different fields empty or have a different number of list entries (e.g.
# evaporation sources) still show every parameter. Returns None when there is no data at all.
def _merge_values(values, exclude_non_numeric):
    present = [value for value in values if value is not _MISSING and value is not None]
    if not present:
        return None

    if all(isinstance(value, dict) for value in present):
        merged = {}
        for key in dict.fromkeys(key for value in present for key in value):
            child = _merge_values(
                [
                    value.get(key, _MISSING) if isinstance(value, dict) else _MISSING
                    for value in values
                ],
                exclude_non_numeric,
            )
            if child is not None:
                merged[key] = child
        return merged or None

    if all(isinstance(value, list) for value in present):
        # list entries keep their index (None where no process has data), so "1" stays the second source
        merged = [
            _merge_values(
                [
                    value[index] if isinstance(value, list) and index < len(value) else _MISSING
                    for value in values
                ],
                exclude_non_numeric,
            )
            for index in range(max(len(value) for value in present))
        ]
        return merged if any(child is not None for child in merged) else None

    leaf = [None if value is _MISSING else value for value in values]
    if exclude_non_numeric and any(isinstance(value, str) for value in leaf):
        return None
    if None not in leaf and len({type(value) for value in leaf}) == 1:
        return np.array(leaf)
    # mixed types or missing values; nested data next to plain values is shown as text
    array = np.empty(len(leaf), dtype=object)
    for index, value in enumerate(leaf):
        array[index] = (
            json.dumps(value, cls=NpEncoder) if isinstance(value, (dict, list)) else value
        )
    return array


def make_table(
    process, index_map, remove_constants=False, remove_string=False, abbreviate_keys=False
):
    def normalize_column_values(values, row_count):
        """Return a list with exactly row_count elements for DataFrame construction."""
        if row_count <= 0:
            return []

        # Regular case: one value per row.
        if isinstance(values, np.ndarray) and values.ndim == 1 and len(values) == row_count:
            return values.tolist()
        if isinstance(values, list) and len(values) == row_count:
            return values

        # Fallback: treat complex/mismatched arrays as a single cell value.
        if isinstance(values, np.ndarray):
            cell_value = values.tolist()
        else:
            cell_value = values
        return [cell_value] * row_count

    column_data = flatten_layers(process["json"], [], remove_constants, remove_string)
    row_index = list(map(lambda idx: str(index_map[idx]), process["indices"]))
    row_count = len(row_index)

    if abbreviate_keys:
        # labels from all parameters, so they match the parameter buttons whatever is hidden
        all_keychains = [
            keychain for keychain, _values in flatten_layers(process["json"], [], False, False)
        ]
        label_of = dict(zip(map(tuple, all_keychains), short_labels(all_keychains)))
        column_dict = {
            label_of[tuple(keychain)]: normalize_column_values(values, row_count)
            for keychain, values in column_data
        }
    else:
        column_dict = dict(
            map(lambda x: (str(x[0]), normalize_column_values(x[1], row_count)), column_data)
        )

    return pd.DataFrame(column_dict, index=row_index)


# abbreviated parameter names: the last key of each keychain, extended by its parent keys only as far as
# needed to stay unique, e.g. "thickness" or "0/thickness" and "1/thickness" for two evaporation sources
def short_labels(keychains):
    labels = []
    for index, keychain in enumerate(keychains):
        depth = 1
        while depth < len(keychain) and any(
            other[-depth:] == keychain[-depth:]
            for other_index, other in enumerate(keychains)
            if other_index != index
        ):
            depth += 1
        labels.append("/".join(map(str, keychain[-depth:])))
    return labels


# expects an object of nested dicts or list with numpy arrays as endpoints. returns a list of tuples, each tuple contains a list of keys used to adress the data in the orginal array and the corresponding array.
def flatten_layers(data, keychain, remove_constants, remove_string):
    if isinstance(data, np.ndarray):
        if remove_string and any(map(lambda x: isinstance(x, str), data)):
            return []
        elif remove_constants and all(data == data[0]):
            return []
        else:
            return [(keychain, data)]
    elif isinstance(data, list):
        return list(
            itertools.chain.from_iterable(
                map(
                    lambda idx_entry: flatten_layers(
                        idx_entry[1],
                        keychain + [str(idx_entry[0])],
                        remove_constants,
                        remove_string,
                    ),
                    enumerate(data),
                )
            )
        )
    elif isinstance(data, dict):
        return list(
            itertools.chain.from_iterable(
                map(
                    lambda key: flatten_layers(
                        data[key], keychain + [key], remove_constants, remove_string
                    ),
                    data,
                )
            )
        )
    return []
