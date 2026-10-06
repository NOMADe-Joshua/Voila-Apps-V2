import re

import ipywidgets as widgets

from perotf_utils.api_calls import get_batch_ids


def extract_date(s):
    # Suche nach jedem 8-stelligen Datum, das mit "20" beginnt
    match = re.search(r"20\d{6}", s)
    return int(match.group()) if match else None


def sort_by_date_desc(data_list):
    return sorted(data_list, key=lambda x: extract_date(x) if extract_date(x) else 0, reverse=True)


def create_batch_selection(url, token, load_data_function):
    # Get batch IDs
    batch_ids_list_tmp = list(get_batch_ids(url, token))
    batch_ids_list = []
    for b in batch_ids_list_tmp:
        if "_".join(b.split("_")[:-1]) in batch_ids_list_tmp:
            continue
        batch_ids_list.append(b)
    batch_ids_list = sort_by_date_desc(batch_ids_list)

    # Create widgets
    batch_ids_selector = widgets.SelectMultiple(
        options=batch_ids_list,
        description="Batches",
        layout=widgets.Layout(width="400px", height="300px"),
    )

    search_field = widgets.Text(description="Search Batch")

    load_batch_button = widgets.Button(description="Load Data", button_style="primary")

    # Define search function
    def on_search_enter(change):
        batch_ids_selector.options = [
            d for d in batch_ids_list if search_field.value.strip().lower() in d.lower()
        ]

    # Bind events
    search_field.observe(on_search_enter, names="value")
    load_batch_button.on_click(lambda b: load_data_function(batch_ids_selector))

    # Return the widget container
    return widgets.VBox([search_field, batch_ids_selector, load_batch_button])
