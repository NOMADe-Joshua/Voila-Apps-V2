"""Fixtures for Entry_Auditor's tests -- never hits the real API."""

import pytest

MODULES = ["data_manager", "gui_components", "app"]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("Entry_Auditor", MODULES)


@pytest.fixture
def fresh_session(mods):
    """A clean EntryAuditSession instance for each test."""
    return mods["data_manager"].EntryAuditSession()
