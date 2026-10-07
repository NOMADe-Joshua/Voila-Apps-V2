"""perotf_utils.config: the single source of server and entry type information."""

import importlib

import pytest

from perotf_utils import config

# Keys shared with HZB's hysprint_utils.config, so exchanged apps resolve them here.
HZB_COMPATIBLE_KEYS = {
    "batch",
    "jv",
    "eqe",
    "mppt",
    "abspl",
    "xrd",
    "base_measurement",
    "base_process",
}


def test_url_base_is_https_or_http_without_trailing_slash():
    assert config.URL_BASE.startswith(("http://", "https://"))
    assert not config.URL_BASE.endswith("/")


@pytest.mark.parametrize("name", ["API_ENDPOINT", "GUI_ENDPOINT", "NORTH_ENDPOINT"])
def test_endpoints_are_absolute_paths_without_trailing_slash(name):
    value = getattr(config, name)
    assert value.startswith("/")
    assert not value.endswith("/")


def test_entry_types_cover_the_hzb_compatible_keys():
    assert HZB_COMPATIBLE_KEYS <= set(config.ENTRY_TYPES)


def test_entry_types_are_non_empty_strings():
    for key, value in config.ENTRY_TYPES.items():
        assert isinstance(value, str) and value, key


def test_environment_overrides_the_server(monkeypatch):
    monkeypatch.setenv("PEROTF_URL_BASE", "https://nomad.example.org")
    monkeypatch.setenv("PEROTF_API_ENDPOINT", "/custom/api/v1")
    try:
        reloaded = importlib.reload(config)
        assert reloaded.URL_BASE == "https://nomad.example.org"
        assert reloaded.API_ENDPOINT == "/custom/api/v1"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_admin_users_default_and_override(monkeypatch):
    assert "nomade" in config.ADMIN_USERS
    monkeypatch.setenv("PEROTF_ADMIN_USERS", " alice , bob ,")
    try:
        assert importlib.reload(config).ADMIN_USERS == ("alice", "bob")
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_api_calls_defaults_come_from_entry_types():
    import inspect

    from perotf_utils import api_calls

    defaults = {
        "get_batch_ids": ("batch_type", "batch"),
        "get_all_JV": ("jv_type", "jv"),
        "get_all_eqe": ("eqe_type", "eqe"),
        "get_all_mppt": ("mppt_type", "mppt"),
        "get_all_xrd": ("xrd_type", "xrd"),
        "get_processing_steps": ("process_type", "base_process"),
    }
    for func_name, (param, key) in defaults.items():
        sig = inspect.signature(getattr(api_calls, func_name))
        assert sig.parameters[param].default == config.ENTRY_TYPES[key], func_name
