import html
import logging
import re

import ipywidgets as widgets
import requests

from perotf_utils.api_calls import get_all_batches_wth_data, get_batch_ids

logger = logging.getLogger(__name__)

# The batch list and the filter button share one width, so the button label is never cut off.
PANEL_WIDTH = "400px"


def extract_date(s):
    # Suche nach jedem 8-stelligen Datum, das mit "20" beginnt
    match = re.search(r"20\d{6}", s)
    return int(match.group()) if match else None


def sort_by_date_desc(data_list):
    return sorted(data_list, key=lambda x: extract_date(x) if extract_date(x) else 0, reverse=True)


def _top_level_batches(batch_ids):
    """Batch ids without the sub-batches whose parent is listed too (KIT_A_1 is hidden when
    KIT_A exists), newest date first."""
    batch_ids = list(batch_ids)
    # A set, not the list: the sub-batch check runs once per batch
    all_batch_ids = set(batch_ids)
    return sort_by_date_desc(
        b for b in batch_ids if "_".join(b.split("_")[:-1]) not in all_batch_ids
    )


def create_batch_selection(
    url,
    token,
    load_data_function,
    filter_label=None,
    filter_entry_type=None,
    filter_function=None,
    multiple=True,
):
    """Batch search field, batch list and Load Data button, as one VBox.

    children[0] is the search field and children[1] the batch list (apps rely on both).

    filter_label: the app's technique as users know it ("MPPT"). With it, a "Show MPPT only"
    button sits directly under the list, above Load Data, the same in every app. It narrows
    the list to the batches that have that measurement; clicked again it shows all batches.
    The search field always searches the list that is shown.
    filter_entry_type: the NOMAD entry type (or list of types) those batches must contain.
    filter_function: optional () -> batch ids, for an app that finds them another way.
    multiple: False gives a single-choice list (widgets.Select, whose value is one batch id or
    None) for an app that works on one batch at a time.
    """
    # Get batch IDs. Without network or a valid token the app must still start, so its
    # demo mode stays reachable: the panel shows the error and an empty list instead.
    load_error = None
    try:
        batch_ids_list_tmp = list(get_batch_ids(url, token))
    except requests.RequestException as error:
        logger.warning("Could not load the batch list: %s", error)
        load_error = error
        batch_ids_list_tmp = []
    batch_ids_list = _top_level_batches(batch_ids_list_tmp)
    # The list the search works on: every batch, or only those the filter found.
    shown = {"ids": batch_ids_list, "filtered": False}

    # Create widgets
    selector_kwargs = {} if multiple else {"value": None}  # Select would preselect the first
    batch_ids_selector = (widgets.SelectMultiple if multiple else widgets.Select)(
        options=batch_ids_list,
        description="Batches",
        layout=widgets.Layout(width=PANEL_WIDTH, height="300px"),
        **selector_kwargs,
    )

    search_field = widgets.Text(description="Search Batch")

    load_batch_button = widgets.Button(description="Load Data", button_style="primary")

    def show_search_matches():
        term = search_field.value.strip().lower()
        batch_ids_selector.options = [d for d in shown["ids"] if term in d.lower()]

    # Define search function
    def on_search_enter(change):
        show_search_matches()

    # Bind events
    search_field.observe(on_search_enter, names="value")
    load_batch_button.on_click(lambda b: load_data_function(batch_ids_selector))

    # Return the widget container. children[1] stays the batch list (apps rely on it).
    children = [search_field, batch_ids_selector]
    if filter_label:
        children.append(
            _filter_row(
                filter_label,
                filter_function
                or (lambda: get_all_batches_wth_data(url, token, filter_entry_type)),
                batch_ids_list,
                shown,
                show_search_matches,
            )
        )
    children.append(load_batch_button)
    if load_error is not None:
        children.append(
            widgets.HTML(
                "<p style='color:#b33'>Could not load the batch list from NOMAD "
                f"({html.escape(type(load_error).__name__)}). Check the connection or your "
                "token; demo data still works.</p>"
            )
        )
    return widgets.VBox(children)


def _error_text(error):
    """Short reason for the panel: the HTTP status when NOMAD answered with one."""
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    return f"HTTP {status}" if status is not None else type(error).__name__


def _filter_row(label, find_batches, all_batches, shown, show_search_matches):
    """The "Show <label> only" toggle and its one-line status, as wide as the batch list
    (ported from HZB).

    The batches found are remembered, so showing them again (after "Show all batches") is
    immediate; a failed lookup is not remembered and is asked again on the next click."""
    only_text = f"Show {label} only"
    button = widgets.Button(
        description=only_text,
        button_style="info",
        tooltip=f"Ask NOMAD which batches have {label} data",
        layout=widgets.Layout(width=PANEL_WIDTH),
    )
    status = widgets.HTML()
    remembered = {}

    def show_found(found):
        shown.update(ids=found, filtered=True)
        button.description = "Show all batches"
        status.value = html.escape(f"{len(found)} of {len(all_batches)} batches have {label} data.")
        show_search_matches()

    def on_click(_b):
        if shown["filtered"]:
            shown.update(ids=all_batches, filtered=False)
            button.description = only_text
            status.value = ""
            show_search_matches()
            return
        if "found" in remembered:
            show_found(remembered["found"])
            return
        button.disabled = True
        button.description = f"Searching NOMAD for {label} batches..."
        status.value = ""
        try:
            # Only batches of the full list: the lookup also knows sub-batches and batches
            # the list hides
            listed = set(all_batches)
            found = [b for b in _top_level_batches(find_batches()) if b in listed]
        except Exception as error:  # noqa: BLE001 - shown in the panel; the full list stays
            logger.warning("Could not filter the batches for %s: %r", label, error)
            status.value = (
                "<span style='color:#b33'>Could not ask NOMAD which batches have "
                f"{html.escape(label)} data ({html.escape(_error_text(error))}).</span>"
            )
            button.description = only_text
        else:
            remembered["found"] = found
            show_found(found)
        finally:
            button.disabled = False

    button.on_click(on_click)
    return widgets.VBox([button, status])
