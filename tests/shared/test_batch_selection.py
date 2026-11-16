"""perotf_utils.batch_selection: the batch list panel every NOMAD app starts with."""

import requests

from perotf_utils import batch_selection


def test_batch_selection_survives_an_unreachable_nomad(monkeypatch):
    """No network or no valid token: the app still starts (demo mode stays reachable), the
    selector stays children[1] and the panel says why the list is empty."""

    def fail(url, token):
        raise requests.ConnectionError("proxy unreachable")

    monkeypatch.setattr(batch_selection, "get_batch_ids", fail)
    box = batch_selection.create_batch_selection("u", "t", lambda w: None)
    assert list(box.children[1].options) == []
    assert "Could not load the batch list" in box.children[-1].value


def test_batch_selection_hides_sub_batches_and_sorts_newest_first(monkeypatch):
    ids = ["KIT_A_20250101_1", "KIT_A_20250101_1_2", "KIT_B_20260301_4", "KIT_C_20240512_9"]
    monkeypatch.setattr(batch_selection, "get_batch_ids", lambda url, token: ids)
    box = batch_selection.create_batch_selection("u", "t", lambda w: None)
    assert list(box.children[1].options) == [
        "KIT_B_20260301_4",
        "KIT_A_20250101_1",
        "KIT_C_20240512_9",
    ]
    assert len(box.children) == 3  # no error notice


def _panel(monkeypatch, find_batches):
    ids = ["KIT_A_20250101_1", "KIT_B_20260301_4", "KIT_C_20240512_9"]
    monkeypatch.setattr(batch_selection, "get_batch_ids", lambda url, token: ids)
    box = batch_selection.create_batch_selection(
        "u", "t", lambda w: None, filter_label="MPPT", filter_function=find_batches
    )
    search, selector, filter_row, load_button = box.children
    return search, selector, filter_row.children[0], filter_row.children[1]


def test_filter_shows_only_batches_with_the_technique_and_back(monkeypatch):
    calls = []

    def find():
        calls.append(1)
        return ["KIT_C_20240512_9", "KIT_A_20250101_1", "KIT_A_20250101_1_2", "KIT_X_20250101"]

    search, selector, button, status = _panel(monkeypatch, find)
    assert button.description == "Show MPPT only"
    button.click()
    # sub-batches and batches the list does not show are left out, newest first
    assert list(selector.options) == ["KIT_A_20250101_1", "KIT_C_20240512_9"]
    assert "2 of 3 batches have MPPT data" in status.value
    search.value = "kit_c"
    assert list(selector.options) == ["KIT_C_20240512_9"]
    search.value = ""
    button.click()
    assert button.description == "Show MPPT only"
    assert len(selector.options) == 3
    button.click()  # remembered: NOMAD is not asked again
    assert list(selector.options) == ["KIT_A_20250101_1", "KIT_C_20240512_9"]
    assert len(calls) == 1


def test_a_failed_filter_keeps_the_full_list_and_says_why(monkeypatch):
    def find():
        raise requests.ConnectionError("down")

    search, selector, button, status = _panel(monkeypatch, find)
    button.click()
    assert len(selector.options) == 3
    assert "ConnectionError" in status.value
    assert button.description == "Show MPPT only" and not button.disabled


def test_filter_entry_type_goes_to_the_batch_lookup(monkeypatch):
    seen = []
    monkeypatch.setattr(batch_selection, "get_batch_ids", lambda url, token: ["KIT_A_20250101"])
    monkeypatch.setattr(
        batch_selection,
        "get_all_batches_wth_data",
        lambda url, token, entry_type: seen.append(entry_type) or ["KIT_A_20250101"],
    )
    box = batch_selection.create_batch_selection(
        "u", "t", lambda w: None, filter_label="EQE", filter_entry_type=["E1", "E2"]
    )
    box.children[2].children[0].click()
    assert seen == [["E1", "E2"]]
    assert list(box.children[1].options) == ["KIT_A_20250101"]
