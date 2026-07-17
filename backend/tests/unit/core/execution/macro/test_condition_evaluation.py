"""Regression: macro IF conditions (element_exists / element_visible) must parse
`BrowserController.check_element` output correctly.

Bug: `check_element` returned "Element status information for: SEL" with a Python
dict-repr details string, while `_evaluate_condition` scraped for "Found"
(element_exists) and "visible=True" (element_visible). Neither token was ever present,
so BOTH conditions were permanently False — any login-conditional / guard macro built on
`element_exists` silently took the else-branch.

Fix: `check_element` now returns "Found element: SEL" / "Not found: SEL" and emits flags
as "visible=True, enabled=True" (app/core/environment/controllers/browser/_perception.py).
These tests pin the string contract between the two files: if either side drifts, a
login-conditional macro breaks and one of these fails.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.core.environment.controllers.browser import BrowserController
from app.core.execution.macro.engine._control import ControlMixin
from app.core.execution.macro.schemas import MacroSource
from app.utils.controller_response import ControllerResponse

SEL = 'input[name="username"]'

# Strings produced exactly as the fixed check_element builds them.
FOUND_VISIBLE = ControllerResponse.success(f"Found element: {SEL}", details="visible=True, enabled=True")
FOUND_INVISIBLE = ControllerResponse.success(f"Found element: {SEL}", details="visible=False, enabled=True")
NOT_FOUND = ControllerResponse.success(f"Not found: {SEL}", details="visible=False, enabled=False")


async def _eval(cond_type, controller_return):
    with patch.object(BrowserController, "execute", new=AsyncMock(return_value=controller_return)):
        return await ControlMixin._evaluate_condition(cond_type, SEL, MacroSource.DOM)


@pytest.mark.asyncio
async def test_element_exists_true_when_found():
    assert await _eval("element_exists", FOUND_VISIBLE) is True


@pytest.mark.asyncio
async def test_element_exists_false_when_not_found():
    # "Not found" must NOT match the "Found" token (case-sensitive guard).
    assert await _eval("element_exists", NOT_FOUND) is False


@pytest.mark.asyncio
async def test_element_exists_true_even_when_invisible():
    # Existence is DOM presence, independent of visibility.
    assert await _eval("element_exists", FOUND_INVISIBLE) is True


@pytest.mark.asyncio
async def test_element_visible_true_when_visible():
    assert await _eval("element_visible", FOUND_VISIBLE) is True


@pytest.mark.asyncio
async def test_element_visible_false_when_invisible():
    assert await _eval("element_visible", FOUND_INVISIBLE) is False


@pytest.mark.asyncio
async def test_element_visible_false_when_not_found():
    assert await _eval("element_visible", NOT_FOUND) is False
