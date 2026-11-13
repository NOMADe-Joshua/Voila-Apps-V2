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
