"""Tests for App_dashboard: link building, the app registry and the widget tree."""

import os

from perotf_utils.config import NORTH_ENDPOINT, URL_BASE

TEST_USER = "test-user"
REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
APPS_DIR = os.path.join(REPO_ROOT, "apps")


def _entry(dm):
    return dm.AppEntry("XRD_PF", "peak_analyzer.ipynb", "XRD Peak Analyzer", "desc", "fa-mountain")


def _registered(dm):
    return [
        (entry.folder, entry.notebook)
        for entries in dm.CATEGORIES.values()
        for entry in entries
        if not entry.external_url
    ]


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_get_current_user_reads_env_var(dm, monkeypatch):
    monkeypatch.setenv("NOMAD_CLIENT_USER", TEST_USER)
    assert dm.get_current_user() == TEST_USER


def test_get_current_user_empty_when_unset(dm, monkeypatch):
    monkeypatch.delenv("NOMAD_CLIENT_USER", raising=False)
    assert dm.get_current_user() == ""


def test_get_uploads_path_derives_upload_id_and_container_from_cwd(dm, monkeypatch):
    upload_dir = "test-upload-session-abc123"
    monkeypatch.setattr(
        os, "getcwd", lambda: f"/home/jovyan/uploads/{upload_dir}/apps/App_dashboard"
    )
    assert dm.get_uploads_path() == f"uploads/{upload_dir}/apps"


def test_get_uploads_path_keeps_a_repo_subdirectory_inside_the_upload(dm, monkeypatch):
    """A repo cloned inside an upload sits one level deeper than an unpacked one.

    `git clone` adds the repo directory, so the cwd is
    uploads/<upload_id>/Voila-Apps-V2/apps/<AppFolder>. Walking a fixed two levels up
    used to return the repo folder as the upload ID, dropping the real upload from every
    dashboard link.
    """
    upload_dir = "dashboard_test-ne_Y0arITbmweei7SZW5ug"
    monkeypatch.setattr(
        os,
        "getcwd",
        lambda: f"/home/jovyan/uploads/{upload_dir}/Voila-Apps-V2/apps/App_dashboard",
    )

    assert dm.get_upload_id() == upload_dir
    assert dm.get_uploads_path() == f"uploads/{upload_dir}/Voila-Apps-V2/apps"


def test_get_uploads_path_uses_the_leftmost_uploads_segment(dm, monkeypatch):
    """An upload literally named 'uploads' must not shadow the real mount point."""
    monkeypatch.setattr(os, "getcwd", lambda: "/home/jovyan/uploads/uploads/apps/App_dashboard")

    assert dm.get_upload_id() == "uploads"
    assert dm.get_uploads_path() == "uploads/uploads/apps"


def test_get_upload_id_derives_from_cwd(dm, monkeypatch):
    upload_dir = "test-upload-session-abc123"
    monkeypatch.setattr(
        os, "getcwd", lambda: f"/home/jovyan/uploads/{upload_dir}/apps/App_dashboard"
    )
    assert dm.get_upload_id() == upload_dir


def test_path_templates_are_built_from_north_endpoint(dm):
    assert dm.VOILA_PATH_TEMPLATE == f"{NORTH_ENDPOINT}/user/{{user}}/voila/voila/render"
    assert dm.JUPYTER_PATH_TEMPLATE == f"{NORTH_ENDPOINT}/user/{{user}}/voila/lab/tree"


def test_build_voila_url_matches_expected_nomad_structure(dm):
    uploads_path = "uploads/test-upload-session-abc123/apps"
    url = dm.build_voila_url(_entry(dm), TEST_USER, uploads_path)

    assert url == (
        dm.VOILA_PATH_TEMPLATE.format(user=TEST_USER)
        + f"/{uploads_path}/XRD_PF/peak_analyzer.ipynb"
    )
    assert url.startswith(f"{NORTH_ENDPOINT}/user/{TEST_USER}/voila/voila/render/")


def test_build_jupyter_url_matches_expected_nomad_structure(dm):
    url = dm.build_jupyter_url(dm.LEARNING_FOLDER, TEST_USER, "abc123")

    assert url == (
        dm.JUPYTER_PATH_TEMPLATE.format(user=TEST_USER)
        + f"/uploads/abc123/{dm.LEARNING_FOLDER.path}"
    )
    assert url.startswith(f"{NORTH_ENDPOINT}/user/{TEST_USER}/voila/lab/tree/")


def test_build_jupyter_url_never_hardcodes_an_upload_id(dm):
    """Regression test: LEARNING_FOLDER must resolve against *this* dashboard's own
    upload (via get_upload_id(), the same way Voila links do), not a fixed ID from some
    other upload -- that mismatch is exactly what caused the original 404."""
    url_a = dm.build_jupyter_url(dm.LEARNING_FOLDER, TEST_USER, "upload-one")
    url_b = dm.build_jupyter_url(dm.LEARNING_FOLDER, TEST_USER, "upload-two")
    assert "upload-one" in url_a
    assert "upload-two" in url_b


def test_url_base_has_no_trailing_slash():
    assert not URL_BASE.endswith("/")


def test_categories_cover_every_app_folder_without_repeating_a_notebook(dm):
    """Every app folder appears, and no notebook is registered twice.

    Uniqueness is per (folder, notebook), not per folder: one app may expose several
    notebooks as separate cards, as Hansen_green_calculator and SEM_crystal_counter do.
    """
    all_folders = {
        name
        for name in os.listdir(APPS_DIR)
        if os.path.isdir(os.path.join(APPS_DIR, name))
        and name != "App_dashboard"
        and not name.startswith((".", "__"))
    }
    listed = _registered(dm)

    assert len(listed) == len(set(listed)), "duplicate notebook in dashboard registry"
    assert {folder for folder, _ in listed} == all_folders


def test_every_registered_notebook_exists_on_disk(dm):
    missing = [
        f"{folder}/{notebook}"
        for folder, notebook in _registered(dm)
        if not os.path.isfile(os.path.join(APPS_DIR, folder, notebook))
    ]
    assert not missing, f"dashboard links to notebooks that do not exist: {missing}"


def test_every_category_has_an_icon_and_no_icon_is_unused(mods):
    categories = set(mods["data_manager"].CATEGORIES)
    icons = set(mods["gui_components"].CATEGORY_ICONS)
    assert categories == icons


def test_build_your_own_entry_links_straight_to_the_prompt_doc(dm):
    entries = dm.CATEGORIES["Build Your Own"]
    assert len(entries) == 1
    assert entries[0].external_url == (
        "https://raw.githubusercontent.com/NOMADe-Joshua/Voila-Apps-V2/main/"
        "NOMAD_DATA_ACCESS_PROMPT.md"
    )
    assert os.path.isfile(os.path.join(REPO_ROOT, "NOMAD_DATA_ACCESS_PROMPT.md"))


def test_learning_folder_opens_the_first_notebook_and_it_exists_in_repo(dm):
    assert dm.LEARNING_FOLDER.path.endswith(".ipynb"), (
        "LEARNING_FOLDER should point at a specific notebook so JupyterLab opens it "
        "directly, not just the bare folder"
    )
    assert os.path.isfile(os.path.join(REPO_ROOT, dm.LEARNING_FOLDER.path)), (
        f"missing learning notebook: {dm.LEARNING_FOLDER.path}"
    )


def test_log_navigation_writes_through_log_button_usage(dm, monkeypatch):
    calls = []
    monkeypatch.setattr(
        dm, "log_button_usage", lambda action, user=None: calls.append((action, user))
    )
    monkeypatch.setenv("NOMAD_CLIENT_USER", TEST_USER)

    dm.log_navigation("whats_new")

    assert calls == [("whats_new", TEST_USER)]


def test_setup_app_builds_one_section_per_category_offline(mods, monkeypatch):
    monkeypatch.setenv("NOMAD_CLIENT_USER", TEST_USER)
    monkeypatch.delenv("NOMAD_CLIENT_ACCESS_TOKEN", raising=False)

    widget = mods["app"].setup_app()

    root, _js_output = widget.children
    # style, header, one section per category, footer
    assert len(root.children) == len(mods["data_manager"].CATEGORIES) + 3
