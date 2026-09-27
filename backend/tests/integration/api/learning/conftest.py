# ruff: noqa: ARG001
"""Shared fixtures for API integration tests under tests/integration/api/learning/.

Adds on top of the shared ``tests/integration/api/conftest.py`` harness the mocks
needed to exercise the learning sub-routers without touching external services
(benefit checks, ADB driver, mirror manager, and the global event session store).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mock_benefit_check(monkeypatch):
    """Always grant required benefits so rely-on-benefit routes are reachable."""

    async def _granted(benefit_code: str, token: str) -> bool:
        return True

    monkeypatch.setattr("app.api.deps.check_benefit", _granted)
