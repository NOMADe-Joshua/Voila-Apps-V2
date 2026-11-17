"""Group_Management against a simulated NOMAD groups API (no network).

The fake follows NOMAD 2.0.1's groups router: members_info with exactly one owner that must
stay the group's owner, 403 for users who neither own nor maintain the group (unless admin),
201 on create, 204 on delete, and /users answering by user_id or email without the email.
"""

import copy
import json

import pytest
import requests

URL = "https://oasis.test/api/v1"
TOKEN = "tok"
ADMIN = "u-admin"
ALICE, BOB, CAROL, DAVE = "u-alice", "u-bob", "u-carol", "u-dave"


class FakeResponse:
    def __init__(self, body=None, status=200):
        self._body = body
        self.status_code = status
        self.ok = status < 400
        self.content = b"" if body is None else json.dumps(body).encode()
        self.text = self.content.decode()
        self.reason = "reason"

    def json(self):
        return self._body


class FakeNomad:
    def __init__(self, me=ADMIN, is_admin=True):
        self.me = me
        self.is_admin = is_admin
        self.users = {
            uid: {"user_id": uid, "username": uid[2:], "name": uid[2:].title()}
            for uid in (ADMIN, ALICE, BOB, CAROL, DAVE)
        }
        self.emails = {f"{uid[2:]}@kit.edu": uid for uid in self.users}
        self.groups = {}
        self.calls = []
        self.ignore_edits = False
        self.refuse_writes = None
        self.before_get = None  # called before a GET of one group (simulates other admins)
        self._next_id = 1

    def add_group(self, name, owner, members=(), description=None):
        group_id = f"g{self._next_id}"
        self._next_id += 1
        info = [{"user_id": owner, "role": "owner"}]
        info += [{"user_id": uid, "role": role} for uid, role in members]
        self.groups[group_id] = {
            "group_id": group_id,
            "group_name": name,
            "description": description,
            "members_info": info,
        }
        return group_id

    def _out(self, group):
        info = group["members_info"]
        return {
            **copy.deepcopy(group),
            "owner": next(m["user_id"] for m in info if m["role"] == "owner"),
            "members": [m["user_id"] for m in info],
        }

    def _validate(self, info, owner):
        ids = [m["user_id"] for m in info]
        owners = [m for m in info if m.get("role") == "owner"]
        if len(ids) != len(set(ids)) or len(owners) != 1 or owners[0]["user_id"] != owner:
            return FakeResponse({"detail": [{"msg": "There must be exactly one owner."}]}, 422)
        unknown = [uid for uid in ids if uid not in self.users]
        if unknown:
            return FakeResponse({"detail": [{"msg": f"User '{unknown[0]}' was not found."}]}, 422)
        return None

    def request(self, method, url, headers=None, params=None, json=None, timeout=None):
        assert timeout is not None, "every NOMAD request needs a timeout"
        assert headers == {"Authorization": f"Bearer {TOKEN}"}
        method = method.upper()
        path = url.removeprefix(URL)
        self.calls.append((method, path, copy.deepcopy(params), copy.deepcopy(json)))
        if method != "GET" and self.refuse_writes:
            return FakeResponse({"detail": "Not authorized."}, self.refuse_writes)

        if path == "/users" and method == "GET":
            found = []
            for uid in params.get("user_id") or []:
                if uid in self.users:
                    found.append(self.users[uid])
            email = params.get("email")
            if email and email in self.emails:
                found.append(self.users[self.emails[email]])
            return FakeResponse({"data": copy.deepcopy(found)})

        if path == "/groups" and method == "GET":
            ordered = sorted(self.groups.values(), key=lambda g: g["group_name"])
            size, page = params["page_size"], params["page"]
            data = [self._out(g) for g in ordered[(page - 1) * size : page * size]]
            return FakeResponse({"pagination": {"total": len(ordered)}, "data": data})

        if path == "/groups" and method == "POST":
            refusal = self._validate(json["members_info"], self.me)
            if refusal:
                return refusal
            group_id = f"g{self._next_id}"
            self._next_id += 1
            self.groups[group_id] = {"group_id": group_id, "description": None, **json}
            return FakeResponse(self._out(self.groups[group_id]), 201)

        group_id = path.split("/")[2]
        group = self.groups.get(group_id)
        if group is None:
            return FakeResponse({"detail": f"User group '{group_id}' was not found."}, 404)
        owner = self._out(group)["owner"]
        role = next((m["role"] for m in group["members_info"] if m["user_id"] == self.me), None)

        if method == "GET":
            if self.before_get:
                self.before_get(group)
            return FakeResponse(self._out(group))
        if method == "POST" and path.endswith("/edit"):
            if not (self.is_admin or role in ("owner", "maintainer")):
                return FakeResponse({"detail": "Not authorized to edit user group."}, 403)
            assert "members" not in json, "the deprecated members field must not be used"
            refusal = self._validate(json["members_info"], owner)
            if refusal:
                return refusal
            if not self.ignore_edits:
                group["members_info"] = copy.deepcopy(json["members_info"])
            return FakeResponse(self._out(group))
        if method == "DELETE":
            if not (self.is_admin or role == "owner"):
                return FakeResponse({"detail": "Not authorized to delete user group."}, 403)
            del self.groups[group_id]
            return FakeResponse(None, 204)
        raise AssertionError(f"unexpected call {method} {path}")

    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]


class FakeRequests:
    RequestException = requests.RequestException

    def __init__(self, nomad):
        self.request = nomad.request


@pytest.fixture
def dm(mods):
    return mods["data_manager"]


@pytest.fixture
def nomad(mods, monkeypatch):
    fake = FakeNomad()
    monkeypatch.setattr(mods["data_manager"], "requests", FakeRequests(fake))
    return fake


@pytest.fixture
def log(tmp_path):
    return tmp_path / "group_changes.log"


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ── Reading ──────────────────────────────────────────────────────────────────


def test_parse_group_reads_roles_and_marks_groups_without_them(dm):
    group = dm.parse_group(
        {
            "group_id": "g1",
            "group_name": "Perovskites",
            "owner": ALICE,
            "members_info": [
                {"user_id": ALICE, "role": "owner"},
                {"user_id": BOB, "role": "maintainer"},
                {"user_id": CAROL},
            ],
        }
    )
    assert group.has_roles
    assert group.owner == ALICE
    assert [(m.user_id, m.role) for m in group.members] == [
        (ALICE, "owner"),
        (BOB, "maintainer"),
        (CAROL, "member"),
    ]
    legacy = dm.parse_group({"group_id": "g2", "owner": ALICE, "members": [BOB]})
    assert not legacy.has_roles
    assert [(m.user_id, m.role) for m in legacy.members] == [(ALICE, "owner"), (BOB, "member")]


def test_list_groups_reads_every_page(dm, nomad, monkeypatch):
    monkeypatch.setattr(dm, "GROUP_PAGE_SIZE", 2)
    for name in ("c", "a", "e", "b", "d"):
        nomad.add_group(name, ALICE)
    groups = dm.list_groups(URL, TOKEN)
    assert [g.group_name for g in groups] == ["a", "b", "c", "d", "e"]
    assert [call[2]["page"] for call in nomad.calls] == [1, 2, 3]


def test_get_users_asks_in_chunks(dm, nomad, monkeypatch):
    monkeypatch.setattr(dm, "USER_ID_CHUNK", 2)
    users = dm.get_users(URL, TOKEN, [ALICE, BOB, CAROL, "u-unknown", ALICE])
    assert set(users) == {ALICE, BOB, CAROL}
    assert [call[2]["user_id"] for call in nomad.calls] == [[ALICE, BOB], [CAROL, "u-unknown"]]


def test_parse_emails_splits_dedupes_and_flags_other_text(dm):
    emails, invalid = dm.parse_emails(
        "alice@kit.edu\nBob@kit.edu, bob@KIT.edu; <carol@kit.edu>\nMax Muster\n\n"
    )
    assert emails == ["alice@kit.edu", "Bob@kit.edu", "carol@kit.edu"]
    assert invalid == ["Max", "Muster"]


def test_display_name_falls_back_to_username_then_id(dm):
    assert dm.display_name({"name": "Alice A", "username": "alice"}) == "Alice A"
    assert dm.display_name({"first_name": "Bob", "last_name": "B"}) == "Bob B"
    assert dm.display_name({"username": "carol"}) == "carol"
    assert dm.display_name(None, "u-x") == "u-x"


# ── Adding members ───────────────────────────────────────────────────────────


def test_plan_add_sorts_the_addresses(dm, nomad):
    gid = nomad.add_group("PV", ALICE, [(BOB, "member")])
    group = dm.get_group(URL, TOKEN, gid)
    plan = dm.plan_add(
        URL, TOKEN, group, "bob@kit.edu\ncarol@kit.edu\nnobody@kit.edu\nhello", "maintainer"
    )
    assert [u["user_id"] for u in plan.to_add] == [CAROL]
    assert plan.to_add[0]["email"] == "carol@kit.edu"
    assert [u["user_id"] for u in plan.already] == [BOB]
    assert plan.lookup.not_found == ["nobody@kit.edu"]
    assert plan.lookup.invalid == ["hello"]
    assert nomad.writes() == []


def test_plan_add_refuses_the_owner_role(dm, nomad):
    gid = nomad.add_group("PV", ALICE)
    with pytest.raises(ValueError):
        dm.plan_add(URL, TOKEN, dm.get_group(URL, TOKEN, gid), "bob@kit.edu", "owner")


def test_apply_add_writes_members_info_onto_the_fresh_group(dm, nomad, log):
    gid = nomad.add_group("PV", ALICE, [(BOB, "maintainer")])
    plan = dm.plan_add(URL, TOKEN, dm.get_group(URL, TOKEN, gid), "carol@kit.edu", "member")
    # Someone else adds Dave between the check and the confirmation.
    nomad.groups[gid]["members_info"].append({"user_id": DAVE, "role": "member"})

    result = dm.apply_add(URL, TOKEN, plan, "admin", log)

    assert result.ok, result.message
    [write] = nomad.writes()
    assert write[1] == f"/groups/{gid}/edit"
    assert write[3] == {
        "members_info": [
            {"user_id": ALICE, "role": "owner"},
            {"user_id": BOB, "role": "maintainer"},
            {"user_id": DAVE, "role": "member"},
            {"user_id": CAROL, "role": "member"},
        ]
    }
    stages = [r["stage"] for r in records(log)]
    assert stages == ["planned", "done"]
    first = records(log)[0]
    assert first["actor"] == "admin"
    assert first["action"] == "add_members"
    assert len(first["before"]) == 3 and len(first["after"]) == 4


def test_the_admin_need_not_be_in_the_group(dm, nomad, log):
    """The deprecated members field made NOMAD look the editor up as owner and fail."""
    gid = nomad.add_group("PV", ALICE)
    plan = dm.plan_add(URL, TOKEN, dm.get_group(URL, TOKEN, gid), "bob@kit.edu", "member")
    assert dm.apply_add(URL, TOKEN, plan, "admin", log).ok
    assert ADMIN not in [m["user_id"] for m in nomad.groups[gid]["members_info"]]


def test_no_change_log_means_no_write(dm, nomad, tmp_path):
    gid = nomad.add_group("PV", ALICE)
    plan = dm.plan_add(URL, TOKEN, dm.get_group(URL, TOKEN, gid), "bob@kit.edu", "member")
    with pytest.raises(dm.ChangeLogError):
        dm.apply_add(URL, TOKEN, plan, "admin", tmp_path / "missing" / "log.log")
    assert nomad.writes() == []


def test_a_refusal_by_nomad_is_reported_and_logged(dm, nomad, log):
    gid = nomad.add_group("PV", ALICE)
    plan = dm.plan_add(URL, TOKEN, dm.get_group(URL, TOKEN, gid), "bob@kit.edu", "member")
    nomad.refuse_writes = 403
    result = dm.apply_add(URL, TOKEN, plan, "admin", log)
    assert not result.ok
    assert "403" in result.message and "Not authorized" in result.message
    assert [r["stage"] for r in records(log)] == ["planned", "failed"]


def test_a_change_nomad_did_not_keep_is_flagged(dm, nomad, log):
    gid = nomad.add_group("PV", ALICE)
    plan = dm.plan_add(URL, TOKEN, dm.get_group(URL, TOKEN, gid), "bob@kit.edu", "member")
    nomad.ignore_edits = True
    result = dm.apply_add(URL, TOKEN, plan, "admin", log)
    assert not result.ok
    assert BOB in result.message
    assert records(log)[-1]["stage"] == "unverified"


def test_nothing_is_written_when_they_joined_meanwhile(dm, nomad, log):
    gid = nomad.add_group("PV", ALICE)
    plan = dm.plan_add(URL, TOKEN, dm.get_group(URL, TOKEN, gid), "bob@kit.edu", "member")
    nomad.groups[gid]["members_info"].append({"user_id": BOB, "role": "member"})
    result = dm.apply_add(URL, TOKEN, plan, "admin", log)
    assert result.ok
    assert nomad.writes() == []
    assert not log.exists()


def test_groups_without_roles_are_never_written(dm, nomad, log, monkeypatch):
    gid = nomad.add_group("PV", ALICE)
    plan = dm.plan_add(URL, TOKEN, dm.get_group(URL, TOKEN, gid), "bob@kit.edu", "member")
    legacy = dm.Group(gid, "PV", ALICE, (dm.Member(ALICE, "owner"),), has_roles=False)
    monkeypatch.setattr(dm, "get_group", lambda *_args: legacy)
    with pytest.raises(dm.GroupApiError):
        dm.apply_add(URL, TOKEN, plan, "admin", log)
    assert nomad.writes() == []


# ── Removing members ─────────────────────────────────────────────────────────


def test_the_owner_cannot_be_removed(dm, nomad):
    gid = nomad.add_group("PV", ALICE, [(BOB, "member")])
    group = dm.get_group(URL, TOKEN, gid)
    with pytest.raises(ValueError, match="owner"):
        dm.plan_remove(group, [ALICE, BOB])
    with pytest.raises(ValueError):
        dm.plan_remove(group, [])
    with pytest.raises(ValueError):
        dm.plan_remove(group, [CAROL])


def test_apply_remove_keeps_everyone_else_with_their_role(dm, nomad, log):
    gid = nomad.add_group("PV", ALICE, [(BOB, "maintainer"), (CAROL, "member"), (DAVE, "member")])
    plan = dm.plan_remove(dm.get_group(URL, TOKEN, gid), [CAROL])
    result = dm.apply_remove(URL, TOKEN, plan, "admin", log)
    assert result.ok, result.message
    assert nomad.groups[gid]["members_info"] == [
        {"user_id": ALICE, "role": "owner"},
        {"user_id": BOB, "role": "maintainer"},
        {"user_id": DAVE, "role": "member"},
    ]
    assert [r["stage"] for r in records(log)] == ["planned", "done"]


# ── Creating and deleting groups ─────────────────────────────────────────────


def test_create_makes_the_signed_in_user_owner(dm, nomad, log):
    plan = dm.plan_create(
        URL,
        TOKEN,
        "  New group ",
        "for tests",
        "bob@kit.edu\nadmin@kit.edu",
        "maintainer",
        ADMIN,
        [],
    )
    assert plan.group_name == "New group"
    result = dm.apply_create(URL, TOKEN, plan, "admin", log)
    assert result.ok, result.message
    [write] = nomad.writes()
    assert write[:2] == ("POST", "/groups")
    assert write[3] == {
        "group_name": "New group",
        "description": "for tests",
        "members_info": [
            {"user_id": ADMIN, "role": "owner"},
            {"user_id": BOB, "role": "maintainer"},
        ],
    }
    assert result.group.group_name == "New group"
    assert [r["stage"] for r in records(log)] == ["planned", "done"]
    assert records(log)[-1]["group_id"] == result.group.group_id


def test_a_name_that_exists_is_refused_at_check_and_at_write(dm, nomad, log):
    nomad.add_group("Perovskites", ALICE)
    groups = dm.list_groups(URL, TOKEN)
    with pytest.raises(ValueError, match="exists already"):
        dm.plan_create(URL, TOKEN, "perovskites ", "", "", "member", ADMIN, groups)
    plan = dm.plan_create(URL, TOKEN, "Tandem", "", "", "member", ADMIN, groups)
    nomad.add_group("Tandem", BOB)  # created by someone else meanwhile
    result = dm.apply_create(URL, TOKEN, plan, "admin", log)
    assert not result.ok
    assert nomad.writes() == []


def test_delete_needs_the_exact_name(dm, nomad):
    gid = nomad.add_group("PV", ALICE)
    group = dm.get_group(URL, TOKEN, gid)
    for typed in ("", "pv", "PV "):
        with pytest.raises(ValueError):
            dm.plan_delete(group, typed)
    assert dm.plan_delete(group, "PV").group == group


def test_delete_stops_when_the_group_changed_since_the_check(dm, nomad, log):
    gid = nomad.add_group("PV", ALICE)
    plan = dm.plan_delete(dm.get_group(URL, TOKEN, gid), "PV")
    nomad.groups[gid]["members_info"].append({"user_id": BOB, "role": "member"})
    result = dm.apply_delete(URL, TOKEN, plan, "admin", log)
    assert not result.ok
    assert nomad.writes() == []
    assert gid in nomad.groups


def test_delete_logs_the_members_and_checks_the_group_is_gone(dm, nomad, log):
    gid = nomad.add_group("PV", ALICE, [(BOB, "maintainer")], description="old")
    plan = dm.plan_delete(dm.get_group(URL, TOKEN, gid), "PV")
    result = dm.apply_delete(URL, TOKEN, plan, "admin", log)
    assert result.ok, result.message
    assert gid not in nomad.groups
    planned, done = records(log)
    assert planned["stage"] == "planned" and done["stage"] == "done"
    assert planned["before"] == [
        {"user_id": ALICE, "role": "owner"},
        {"user_id": BOB, "role": "maintainer"},
    ]
    assert planned["description"] == "old"


def test_read_log_returns_the_newest_first(dm, log):
    for index in range(5):
        dm.write_log({"action": "x", "n": index}, log)
    assert [r["n"] for r in dm.read_log(log, limit=3)] == [4, 3, 2]
    assert dm.read_log(log.with_name("none.log")) == []


# ── The app ──────────────────────────────────────────────────────────────────


@pytest.fixture
def app(mods, nomad, monkeypatch, log):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(mods["data_manager"], "change_log_path", lambda: log)
    application = mods["app"].GroupManagementApp()
    application.auth_manager.url = URL
    application.auth_manager.current_token = TOKEN
    application.auth_manager.current_user_info = {
        "user_id": ADMIN,
        "username": "admin",
        "is_admin": True,
    }
    return application


def test_app_constructs_offline(mods, monkeypatch):
    monkeypatch.delenv("JUPYTERHUB_USER", raising=False)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)
    application = mods["app"].GroupManagementApp()
    assert application.get_dashboard() is not None
    assert application.add_check.disabled


def test_app_adds_a_member_after_the_second_click(app, nomad, log):
    gid = nomad.add_group("PV", ALICE, [(BOB, "member")])
    app._on_auth_success()
    assert "1 group loaded" in app.status_html.value
    app.group_select.value = gid
    assert "Alice" in app.group_html.value and "owner" in app.group_html.value
    assert app.remove_select.options == (("Bob  (member)", BOB),)

    app.add_emails.value = "carol@kit.edu"
    app._check_add()
    assert app.confirm_box.layout.display == "flex"
    assert nomad.writes() == []
    app._confirm()

    assert "Done" in app.result_html.value
    assert CAROL in [m["user_id"] for m in nomad.groups[gid]["members_info"]]
    assert app.add_emails.value == ""
    assert app.group_select.value == gid
    assert app.confirm_box.layout.display == "none"


def test_changing_the_input_drops_the_checked_plan(app, nomad):
    gid = nomad.add_group("PV", ALICE)
    app._on_auth_success()
    app.group_select.value = gid
    app.add_emails.value = "bob@kit.edu"
    app._check_add()
    app.add_emails.value = "carol@kit.edu"
    assert app._pending is None
    assert app.confirm_box.layout.display == "none"
    app._confirm()
    assert nomad.writes() == []


def test_app_shows_errors_instead_of_raising(app, nomad):
    app._on_auth_success()
    app._guarded(app._check_remove)  # no group selected
    assert "Select a group" in app.status_html.value


def test_app_escapes_nomad_text(app, nomad):
    gid = nomad.add_group("<b>x</b>", ALICE, description="<script>")
    app._on_auth_success()
    app.group_select.value = gid
    assert "<script>" not in app.group_html.value
    assert "&lt;b&gt;x&lt;/b&gt;" in app.group_html.value
