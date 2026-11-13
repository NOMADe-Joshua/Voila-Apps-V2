"""Login credentials go in the POST body, never in the URL (ported from HZB)."""

import pytest

from perotf_utils import access_token, api_calls, auth_manager


class _Resp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"access_token": "tok"}


@pytest.fixture
def seen(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append(("post", url, kwargs))
        return _Resp()

    def get(url, **kwargs):
        calls.append(("get", url, kwargs))
        return _Resp()

    for module in (auth_manager, access_token, api_calls):
        monkeypatch.setattr(module.requests, "post", post)
        monkeypatch.setattr(module.requests, "get", get)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "secret")
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    return calls


def _assert_body_only(call):
    method, url, kwargs = call
    assert method == "post"
    assert url.endswith("/auth/token")
    assert kwargs["data"] == {"username": "u", "password": "secret"}
    assert "params" not in kwargs


def test_auth_manager_sends_credentials_in_body(seen):
    manager = auth_manager.AuthenticationManager("https://e.test", "/api/v1")
    assert manager.authenticate_with_credentials("u", "secret") == "tok"
    _assert_body_only(seen[0])


def test_access_token_get_token_sends_credentials_in_body(seen):
    assert access_token.get_token("https://e.test/api/v1", name="u") == "tok"
    _assert_body_only(seen[0])


def test_api_calls_get_token_sends_credentials_in_body(seen):
    assert api_calls.get_token("https://e.test/api/v1", name="u") == "tok"
    _assert_body_only(seen[0])
