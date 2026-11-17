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
    try:
        monkeypatch.delenv("PEROTF_ADMIN_USERS", raising=False)
        # No names in the repo: without oasis_local_config.py nobody is an admin.
        assert importlib.reload(config).ADMIN_USERS == ()
        monkeypatch.setenv("PEROTF_ADMIN_USERS", " alice , bob ,")
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


def test_entry_type_families_are_lists_holding_the_single_types():
    families = config.ENTRY_TYPE_FAMILIES
    for kind, types in families.items():
        assert isinstance(types, list) and all(isinstance(t, str) for t in types), kind
        assert len(set(types)) == len(types), kind
    for kind, key in [
        ("jv", "jv"),
        ("eqe", "eqe"),
        ("eqe", "eqe_tfl_gammabox"),
        ("mppt", "mppt"),
        ("sem", "sem"),
        ("xrd", "xrd"),
        ("abspl", "abspl"),
        ("uvvis", "uvvis"),
        ("substrate", "substrate"),
        ("spin_coating", "spin_coating"),
        ("evaporation", "evaporation"),
        ("inkjet_printing", "inkjet_printing"),
        ("annealing", "thermal_annealing"),
    ]:
        assert config.ENTRY_TYPES[key] in families[kind], (kind, key)


def test_get_all_eqe_asks_for_a_whole_family_with_entry_type_any(monkeypatch):
    from perotf_utils import api_calls

    queries = []

    def fake_query_all(url, token, endpoint, query):
        queries.append(query["query"])
        return [{"entry_id": "S"}] if endpoint == "entries/query" else []

    monkeypatch.setattr(api_calls, "query_all", fake_query_all)
    api_calls.get_all_eqe("u", "t", ["S1"], eqe_type=config.ENTRY_TYPE_FAMILIES["jv"])
    assert queries[1]["entry_type:any"] == sorted(config.ENTRY_TYPE_FAMILIES["jv"])
    api_calls.get_all_eqe("u", "t", ["S1"])
    assert queries[3]["entry_type"] == config.ENTRY_TYPES["eqe"]
