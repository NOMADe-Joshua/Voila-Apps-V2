"""Group Management: list, change, create and delete NOMAD user groups.

No widgets here. Every write is planned first (plan_*) and shown to the admin, then applied
(apply_*) only after a second click:

- the group is read again right before the write and the change is computed from that fresh
  state, so members someone else added meanwhile are kept (NOMAD's group edit has no
  concurrency check of its own);
- the planned change (members before and after) goes into the change log before NOMAD is
  touched: no log line, no write. The log is what lets an admin undo a change by hand;
- afterwards the group is read back and compared with what was written.

Members are written as `members_info` (user id plus role), the format NOMAD uses since 1.4.1.
The older `members` field still exists but is deprecated, and NOMAD's edit endpoint fails on
it when the editing user is not in the group (it looks the editor up as the group's owner),
which is the usual case for the admin account. Logins are not handled here: the app uses the
shared AuthenticationManager (POST, NOMAD 1.4 removed the GET login).
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from perotf_utils.access_token import usage_log_dir
from perotf_utils.api_calls import REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

OWNER = "owner"
MAINTAINER = "maintainer"
MEMBER = "member"
ASSIGNABLE_ROLES = (MEMBER, MAINTAINER)
"""Roles the app gives. The owner is fixed: NOMAD keeps the creator as owner and refuses an
edit that names a different one."""

GROUP_PAGE_SIZE = 100
MAX_GROUP_PAGES = 100
USER_ID_CHUNK = 40
"""User ids per /users request (repeated query parameters, so the URL stays short)."""

LOG_FILENAME = "group_changes.log"


class GroupApiError(RuntimeError):
    """A NOMAD request failed; the message holds NOMAD's own reason, `status` the HTTP code
    (None when NOMAD did not answer at all)."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class ChangeLogError(RuntimeError):
    """The change log could not be written, so nothing was changed in NOMAD."""


# ── NOMAD requests ───────────────────────────────────────────────────────────


def _detail(response):
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, list):
        detail = "; ".join(
            str(item.get("msg", item)) if isinstance(item, dict) else str(item) for item in detail
        )
    text = detail or (response.text or "")[:300] or response.reason
    return f"NOMAD answered {response.status_code}: {text}"


def _call(method, url, token, *, params=None, json_body=None):
    try:
        response = requests.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            json=json_body,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise GroupApiError(f"No answer from NOMAD: {exc}") from exc
    if not response.ok:
        raise GroupApiError(_detail(response), response.status_code)
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _group_url(url, group_id):
    return f"{url}/groups/{quote(str(group_id), safe='')}"


# ── Groups and users ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Member:
    user_id: str
    role: str = MEMBER


@dataclass(frozen=True)
class Group:
    group_id: str
    group_name: str
    owner: str
    members: tuple[Member, ...]
    description: str = ""
    has_roles: bool = True
    """False when NOMAD reported no `members_info` (older than 1.4.1): shown, never written."""

    @property
    def member_ids(self) -> list[str]:
        return [member.user_id for member in self.members]

    def role_of(self, user_id):
        return next((m.role for m in self.members if m.user_id == user_id), None)


def parse_group(data) -> Group:
    """A Group from NOMAD's JSON (GET /groups, GET /groups/{id}, POST /groups)."""
    if not isinstance(data, dict) or not data.get("group_id"):
        raise GroupApiError("NOMAD returned a group without an id")
    info = data.get("members_info")
    owner = data.get("owner") or ""
    if isinstance(info, list):
        members = tuple(
            Member(str(item["user_id"]), str(item.get("role") or MEMBER))
            for item in info
            if isinstance(item, dict) and item.get("user_id")
        )
        owner = owner or next((m.user_id for m in members if m.role == OWNER), "")
        has_roles = True
    else:
        ids = list(dict.fromkeys([owner, *(data.get("members") or [])]))
        members = tuple(Member(uid, OWNER if uid == owner else MEMBER) for uid in ids if uid)
        has_roles = False
    return Group(
        group_id=str(data["group_id"]),
        group_name=str(data.get("group_name") or ""),
        owner=owner,
        members=members,
        description=str(data.get("description") or ""),
        has_roles=has_roles,
    )


def list_groups(url, token) -> list[Group]:
    """Every group of the Oasis, sorted by name (all pages)."""
    groups = []
    for page in range(1, MAX_GROUP_PAGES + 1):
        body = _call(
            "get",
            f"{url}/groups",
            token,
            params={"page_size": GROUP_PAGE_SIZE, "page": page, "order_by": "group_name"},
        )
        data = (body or {}).get("data") or []
        groups.extend(parse_group(item) for item in data)
        total = ((body or {}).get("pagination") or {}).get("total")
        if not data or total is None or len(groups) >= total:
            break
    else:
        logger.warning("Stopped listing groups after %d pages", MAX_GROUP_PAGES)
    return sorted(groups, key=lambda group: group.group_name.lower())


def get_group(url, token, group_id) -> Group:
    return parse_group(_call("get", _group_url(url, group_id), token))


def get_users(url, token, user_ids) -> dict[str, dict]:
    """NOMAD's public user records by user id. An id NOMAD does not know is left out."""
    ids = list(dict.fromkeys(uid for uid in user_ids if uid))
    users = {}
    for start in range(0, len(ids), USER_ID_CHUNK):
        chunk = ids[start : start + USER_ID_CHUNK]
        body = _call("get", f"{url}/users", token, params={"user_id": chunk})
        for user in (body or {}).get("data") or []:
            if isinstance(user, dict) and user.get("user_id"):
                users[user["user_id"]] = user
    return users


def find_user_by_email(url, token, email):
    """The NOMAD user with this email address, or None. NOMAD never returns the address
    itself, so callers keep it next to the record."""
    body = _call("get", f"{url}/users", token, params={"email": email})
    data = [user for user in (body or {}).get("data") or [] if user.get("user_id")]
    return data[0] if len(data) == 1 else None


def display_name(user, user_id=""):
    """A readable name for a user record (falls back to the username, then the id)."""
    if not user:
        return user_id
    name = user.get("name") or " ".join(
        part for part in (user.get("first_name"), user.get("last_name")) if part
    )
    return name or user.get("username") or user.get("user_id") or user_id


# ── Email input ──────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[^@\s<>,;\"']+")


def parse_emails(text):
    """(emails, not_emails) from free text: one address per line, or separated by commas,
    semicolons or spaces. Duplicates are dropped (ignoring case)."""
    emails, invalid, seen = [], [], set()
    for token in re.split(r"[\s,;]+", text or ""):
        token = token.strip().strip("<>\"'()")
        if not token or token.lower() in seen:
            continue
        seen.add(token.lower())
        (emails if EMAIL_RE.fullmatch(token) else invalid).append(token)
    return emails, invalid


@dataclass
class UserLookup:
    found: list[dict] = field(default_factory=list)
    """One record per user (input order), with the email it was found by under "email"."""
    not_found: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)


def look_up_emails(url, token, text) -> UserLookup:
    emails, invalid = parse_emails(text)
    lookup = UserLookup(invalid=invalid)
    seen_ids = set()
    for email in emails:
        user = find_user_by_email(url, token, email)
        if user is None:
            lookup.not_found.append(email)
        elif user["user_id"] not in seen_ids:
            seen_ids.add(user["user_id"])
            lookup.found.append({**user, "email": email})
    return lookup


# ── Plans (shown before anything is written) ─────────────────────────────────


@dataclass
class AddPlan:
    group: Group
    role: str
    lookup: UserLookup
    to_add: list[dict]
    already: list[dict]


@dataclass
class RemovePlan:
    group: Group
    user_ids: list[str]


@dataclass
class CreatePlan:
    group_name: str
    description: str
    owner_id: str
    role: str
    lookup: UserLookup


@dataclass
class DeletePlan:
    group: Group


def _check_role(role):
    if role not in ASSIGNABLE_ROLES:
        raise ValueError(f"Unknown role {role!r}: use one of {', '.join(ASSIGNABLE_ROLES)}.")


def plan_add(url, token, group, emails_text, role) -> AddPlan:
    _check_role(role)
    lookup = look_up_emails(url, token, emails_text)
    current = set(group.member_ids)
    return AddPlan(
        group=group,
        role=role,
        lookup=lookup,
        to_add=[user for user in lookup.found if user["user_id"] not in current],
        already=[user for user in lookup.found if user["user_id"] in current],
    )


def plan_remove(group, user_ids) -> RemovePlan:
    ids = list(dict.fromkeys(user_ids))
    if not ids:
        raise ValueError("Choose at least one member to remove.")
    if group.owner in ids:
        raise ValueError("The owner cannot be removed from the group.")
    unknown = [uid for uid in ids if uid not in group.member_ids]
    if unknown:
        raise ValueError(f"Not members of this group: {', '.join(unknown)}")
    return RemovePlan(group=group, user_ids=ids)


def duplicate_names(groups, name):
    key = name.strip().lower()
    return [group for group in groups if group.group_name.strip().lower() == key]


def plan_create(url, token, name, description, emails_text, role, owner_id, groups) -> CreatePlan:
    """`groups` is the current group list: a name that exists already is refused (NOMAD
    would allow it, but two groups of the same name are easily mixed up)."""
    _check_role(role)
    name = (name or "").strip()
    if not name:
        raise ValueError("Enter a name for the new group.")
    if not owner_id:
        raise ValueError("Your NOMAD user id is unknown: sign in again.")
    if duplicate_names(groups, name):
        raise ValueError(f"A group named '{name}' exists already.")
    lookup = look_up_emails(url, token, emails_text) if (emails_text or "").strip() else None
    return CreatePlan(
        group_name=name,
        description=(description or "").strip(),
        owner_id=owner_id,
        role=role,
        lookup=lookup or UserLookup(),
    )


def plan_delete(group, typed_name) -> DeletePlan:
    if (typed_name or "") != group.group_name:
        raise ValueError("Type the group name exactly as shown to confirm the deletion.")
    return DeletePlan(group=group)


# ── Change log ───────────────────────────────────────────────────────────────


def change_log_path() -> Path:
    """Next to the usage log (gitignored, in the upload under NORTH), read by admins only."""
    return usage_log_dir() / LOG_FILENAME


def _members_record(members):
    return [{"user_id": member.user_id, "role": member.role} for member in members]


def write_log(record, path=None):
    """Append one JSON line. Raises ChangeLogError: before a write that means no write."""
    path = Path(path) if path else change_log_path()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = json.dumps({"time": stamp, **record}, ensure_ascii=False)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        raise ChangeLogError(f"Cannot write the change log {path}: {exc}") from exc


def _log_after(record, path):
    """The log line after a write: a failure here must not hide what NOMAD did."""
    try:
        write_log(record, path)
    except ChangeLogError:
        logger.exception("Change log not written after a group change")


def read_log(path=None, limit=50) -> list[dict]:
    """The last `limit` log records, newest first ([] when there is no log yet)."""
    path = Path(path) if path else change_log_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    records = []
    for line in reversed(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(records) >= limit:
            break
    return records


# ── Applying a plan ──────────────────────────────────────────────────────────


@dataclass
class ChangeResult:
    ok: bool
    message: str
    group: Group | None = None
    """The group as NOMAD shows it afterwards (None after a deletion)."""


def compare_members(actual, expected) -> list[str]:
    """What differs between the members NOMAD shows and the ones written ([] = identical)."""
    have = {member.user_id: member.role for member in actual}
    want = {member.user_id: member.role for member in expected}
    problems = []
    missing = [uid for uid in want if uid not in have]
    extra = [uid for uid in have if uid not in want]
    roles = [uid for uid in want if uid in have and have[uid] != want[uid]]
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if extra:
        problems.append(f"not expected: {', '.join(extra)}")
    if roles:
        problems.append(
            "other role: " + ", ".join(f"{uid} ({have[uid]}, not {want[uid]})" for uid in roles)
        )
    return problems


def _require_roles(group):
    if not group.has_roles:
        raise GroupApiError(
            "NOMAD reported no member roles for this group; this app writes only to NOMAD "
            "1.4.1 or newer."
        )


def _write_members(url, token, before, target, action, actor, log_path):
    record = {
        "action": action,
        "actor": actor,
        "group_id": before.group_id,
        "group_name": before.group_name,
        "before": _members_record(before.members),
        "after": _members_record(target),
    }
    write_log({**record, "stage": "planned"}, log_path)
    try:
        _call(
            "post",
            f"{_group_url(url, before.group_id)}/edit",
            token,
            json_body={"members_info": _members_record(target)},
        )
    except GroupApiError as exc:
        _log_after({**record, "stage": "failed", "error": str(exc)}, log_path)
        return ChangeResult(False, f"NOMAD refused the change. {exc}", before)
    return _read_back(url, token, before.group_id, target, record, log_path)


def _read_back(url, token, group_id, target, record, log_path, extra_problems=()):
    try:
        after = get_group(url, token, group_id)
    except GroupApiError as exc:
        _log_after(
            {**record, "group_id": group_id, "stage": "unverified", "error": str(exc)}, log_path
        )
        return ChangeResult(False, f"Written, but the group could not be read back: {exc}")
    problems = [*extra_problems, *compare_members(after.members, target)]
    _log_after(
        {
            **record,
            "group_id": group_id,
            "stage": "unverified" if problems else "done",
            "problems": problems,
        },
        log_path,
    )
    if problems:
        return ChangeResult(
            False,
            "NOMAD took the change, but the group read back differs: " + "; ".join(problems),
            after,
        )
    return ChangeResult(True, "Done; NOMAD shows the group as written.", after)


def apply_add(url, token, plan: AddPlan, actor, log_path=None) -> ChangeResult:
    fresh = get_group(url, token, plan.group.group_id)
    _require_roles(fresh)
    current = set(fresh.member_ids)
    new_members = tuple(
        Member(user["user_id"], plan.role) for user in plan.to_add if user["user_id"] not in current
    )
    if not new_members:
        return ChangeResult(True, "Nothing to add: all of them are members already.", fresh)
    target = (*fresh.members, *new_members)
    return _write_members(url, token, fresh, target, "add_members", actor, log_path)


def apply_remove(url, token, plan: RemovePlan, actor, log_path=None) -> ChangeResult:
    fresh = get_group(url, token, plan.group.group_id)
    _require_roles(fresh)
    remove = set(plan.user_ids)
    if fresh.owner in remove:
        return ChangeResult(False, "The owner cannot be removed from the group.", fresh)
    target = tuple(member for member in fresh.members if member.user_id not in remove)
    if len(target) == len(fresh.members):
        return ChangeResult(True, "Nothing to remove: none of them is a member any more.", fresh)
    return _write_members(url, token, fresh, target, "remove_members", actor, log_path)


def apply_create(url, token, plan: CreatePlan, actor, log_path=None) -> ChangeResult:
    if duplicate_names(list_groups(url, token), plan.group_name):
        return ChangeResult(False, f"A group named '{plan.group_name}' exists already.")
    members = (
        Member(plan.owner_id, OWNER),
        *(
            Member(user["user_id"], plan.role)
            for user in plan.lookup.found
            if user["user_id"] != plan.owner_id
        ),
    )
    payload = {"group_name": plan.group_name, "members_info": _members_record(members)}
    if plan.description:
        payload["description"] = plan.description
    record = {
        "action": "create_group",
        "actor": actor,
        "group_name": plan.group_name,
        "description": plan.description,
        "after": _members_record(members),
    }
    write_log({**record, "stage": "planned"}, log_path)
    try:
        created = parse_group(_call("post", f"{url}/groups", token, json_body=payload))
    except GroupApiError as exc:
        _log_after({**record, "stage": "failed", "error": str(exc)}, log_path)
        return ChangeResult(False, f"NOMAD did not create the group. {exc}")
    problems = []
    if created.group_name != plan.group_name:
        problems.append(f"name is '{created.group_name}'")
    return _read_back(url, token, created.group_id, members, record, log_path, problems)


def apply_delete(url, token, plan: DeletePlan, actor, log_path=None) -> ChangeResult:
    fresh = get_group(url, token, plan.group.group_id)
    if fresh.group_name != plan.group.group_name or compare_members(
        fresh.members, plan.group.members
    ):
        return ChangeResult(
            False, "The group changed since you checked it; check it again first.", fresh
        )
    record = {
        "action": "delete_group",
        "actor": actor,
        "group_id": fresh.group_id,
        "group_name": fresh.group_name,
        "description": fresh.description,
        "before": _members_record(fresh.members),
    }
    write_log({**record, "stage": "planned"}, log_path)
    try:
        _call("delete", _group_url(url, fresh.group_id), token)
    except GroupApiError as exc:
        _log_after({**record, "stage": "failed", "error": str(exc)}, log_path)
        return ChangeResult(False, f"NOMAD did not delete the group. {exc}", fresh)
    try:
        get_group(url, token, fresh.group_id)
    except GroupApiError as exc:
        if exc.status == 404:
            _log_after({**record, "stage": "done"}, log_path)
            return ChangeResult(True, "Deleted; NOMAD no longer knows the group.")
        _log_after({**record, "stage": "unverified", "error": str(exc)}, log_path)
        return ChangeResult(False, f"Deleted, but the check afterwards failed: {exc}")
    _log_after({**record, "stage": "unverified", "error": "still listed"}, log_path)
    return ChangeResult(False, "NOMAD answered the deletion but still lists the group.", fresh)
