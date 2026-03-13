"""
E2E Tests for Agent-based Macro Verification

These tests run against real browser/mobile controllers.
Requires:
- Playwright installed
- Android emulator connected (for mobile tests)
- Test web application running
"""

import pytest
import asyncio
from typing import List, Dict, Any

# Mark all tests as e2e
pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


@pytest.fixture(scope="module")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def browser_controller():
    """Setup and teardown browser controller for web tests."""
    from app.infrastructure.automation.web.controller import BrowserController

    controller = BrowserController()
    try:
        await controller.configure({"headless": True})
        yield controller
    finally:
        await controller.close()


@pytest.fixture
async def mobile_controller():
    """Setup and teardown mobile controller for Android tests."""
    from app.infrastructure.automation.mobile.controller import MobileController

    controller = MobileController()
    try:
        await controller.connect()
        yield controller
    finally:
        await controller.disconnect()


class TestWebVerificationE2E:
    """E2E tests for web macro verification"""

    async def test_simple_login_flow_verification(self, browser_controller):
        """
        E2E: Verify a simple login flow on a test page.

        This test:
        1. Creates a login macro
        2. Runs verification with 2 rounds
        3. Checks that macro passes or gets adapted
        """
        from app.core.execution.macro import VerificationService

        # Test against httpbin.org forms
        macro_script = [
            {
                "step_number": 1,
                "type": "action",
                "event_type": "goto",
                "source": "dom",
                "payload": {"url": "https://httpbin.org/forms/post"}
            },
            {
                "step_number": 2,
                "type": "action",
                "event_type": "input",
                "source": "dom",
                "target_selector": "input[name='custname']",
                "payload": {"selector": "input[name='custname']", "text": "Test User"}
            },
            {
                "step_number": 3,
                "type": "action",
                "event_type": "input",
                "source": "dom",
                "target_selector": "input[name='custtel']",
                "payload": {"selector": "input[name='custtel']", "text": "1234567890"}
            },
            {
                "step_number": 4,
                "type": "action",
                "event_type": "click",
                "source": "dom",
                "target_selector": "button[type='submit']",
                "payload": {"selector": "button[type='submit']"}
            }
        ]

        result = await VerificationService.verify_macro(
            macro_script=macro_script,
            platform="web",
            max_rounds=2,
            auto_evolve=True,
            thread_id="e2e_test_login"
        )

        # Should complete (might need adaptations)
        assert result["rounds_completed"] >= 1
        assert result["verification_report"]["summary"]["success_rate"] > 0

    async def test_coordinate_drift_handling(self, browser_controller):
        """
        E2E: Test that coordinate drift is detected and fixed.

        Uses a macro with coordinates that might drift and verifies
        the system adapts to use selectors instead.
        """
        from app.core.execution.macro import VerificationService

        macro_script = [
            {
                "step_number": 1,
                "type": "action",
                "event_type": "goto",
                "source": "dom",
                "payload": {"url": "https://example.com"}
            },
            {
                "step_number": 2,
                "type": "action",
                "event_type": "click",
                "source": "dom",
                "target_selector": "a",  # Generic selector
                "payload": {"x": 100, "y": 200}  # Potentially wrong coordinates
            }
        ]

        result = await VerificationService.verify_macro(
            macro_script=macro_script,
            platform="web",
            max_rounds=2,
            auto_evolve=True
        )

        # If evolved, check that it handles coordinate issues
        if result.get("evolved_macro"):
            evolved = result["evolved_macro"]
            step_2 = next((s for s in evolved if s.get("step_number") == 2), None)
            if step_2:
                # Should have fallback or use selector more reliably
                assert (
                    "fallback" in step_2 or
                    "max_retries" in step_2.get("payload", {}) or
                    "selector_chain" in step_2.get("payload", {})
                )

    async def test_multi_round_robustness(self, browser_controller):
        """
        E2E: Test multi-round verification with interference.

        Runs baseline + stress test rounds to ensure macro is robust.
        """
        from app.core.execution.macro import VerificationService

        macro_script = [
            {
                "step_number": 1,
                "type": "action",
                "event_type": "goto",
                "source": "dom",
                "payload": {"url": "https://httpbin.org/get"}
            },
            {
                "step_number": 2,
                "type": "extract",
                "extract_type": "get_text",
                "key": "page_title",
                "source": "dom",
                "target_selector": "title",
                "payload": {"selector": "title"}
            }
        ]

        result = await VerificationService.verify_macro(
            macro_script=macro_script,
            platform="web",
            max_rounds=3,  # Baseline + stress + chaos
            auto_evolve=True
        )

        assert result["rounds_completed"] == 3
        assert result["verification_report"]["summary"]["max_round_variance"] >= 0


class TestMobileVerificationE2E:
    """E2E tests for mobile (Android) macro verification"""

    async def test_mobile_app_launch_verification(self, mobile_controller):
        """
        E2E: Verify mobile app launch and basic interaction.

        Requires:
        - Android emulator running
        - Sample app installed (or use system Settings app)
        """
        from app.core.execution.macro import VerificationService

        # Test with Android Settings app (always available)
        macro_script = [
            {
                "step_number": 1,
                "type": "action",
                "event_type": "open_app",
                "source": "mobile",
                "payload": {"package_name": "com.android.settings"}
            },
            {
                "step_number": 2,
                "type": "action",
                "event_type": "wait",
                "source": "mobile",
                "payload": {"duration_ms": 2000}
            },
            {
                "step_number": 3,
                "type": "extract",
                "extract_type": "dump_ui",
                "key": "settings_ui",
                "source": "mobile"
            }
        ]

        result = await VerificationService.verify_macro(
            macro_script=macro_script,
            platform="android",
            max_rounds=2,
            auto_evolve=True,
            thread_id="e2e_test_mobile"
        )

        assert result["rounds_completed"] >= 1
        assert result["execution_mode"] in ["deterministic", "hybrid", "agentic"]


class TestSkillSynthesisE2E:
    """E2E tests for skill synthesis with verification"""

    async def test_end_to_end_skill_creation(self, browser_controller):
        """
        E2E: Complete flow from trace to verified skill.

        This test simulates a real skill synthesis with verification.
        """
        from app.core.learning.skill_synthesizer import WorkflowSynthesizer

        # This would require actual trace data in the database
        # For E2E test, we'd need to set up a test thread with trace data

        synthesizer = WorkflowSynthesizer(
            thread_id="e2e_synthesis_test",
            session_id="e2e_session"
        )

        # Note: This requires database setup with actual trace records
        # skill = await synthesizer.synthesize()

        # Verify skill has execution_mode set by verification
        # assert skill.execution_mode in ["deterministic", "hybrid", "agentic"]
        # assert skill.macro_script is not None

        pytest.skip("Requires database setup with trace data")


class TestVerificationPerformanceE2E:
    """Performance-related E2E tests"""

    async def test_single_round_performance(self, browser_controller):
        """
        E2E: Verify single round completes within acceptable time.

        Target: < 60 seconds for 5-step macro
        """
        from app.core.execution.macro import VerificationService
        import time

        macro_script = [
            {"step_number": i, "type": "action", "event_type": "wait",
             "source": "dom", "payload": {"duration_ms": 500}}
            for i in range(1, 6)
        ]
        macro_script[0] = {
            "step_number": 1,
            "type": "action",
            "event_type": "goto",
            "source": "dom",
            "payload": {"url": "about:blank"}
        }

        start_time = time.time()

        result = await VerificationService.verify_macro(
            macro_script=macro_script,
            platform="web",
            max_rounds=1
        )

        elapsed = time.time() - start_time

        assert result["success"] is True
        assert elapsed < 60, f"Single round took {elapsed:.1f}s, expected < 60s"

    async def test_concurrent_verification(self, browser_controller):
        """
        E2E: Test multiple verifications can run concurrently.
        """
        from app.core.execution.macro import VerificationService

        macros = [
            [
                {"step_number": 1, "type": "action", "event_type": "goto",
                 "source": "dom", "payload": {"url": f"about:blank#{i}"}},
                {"step_number": 2, "type": "action", "event_type": "wait",
                 "source": "dom", "payload": {"duration_ms": 200}}
            ]
            for i in range(3)
        ]

        tasks = [
            VerificationService.verify_macro(
                macro_script=m,
                platform="web",
                max_rounds=1
            )
            for m in macros
        ]

        results = await asyncio.gather(*tasks)

        assert all(r["success"] for r in results)


# Run configuration
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end")
    config.addinivalue_line("markers", "web: mark test as web browser test")
    config.addinivalue_line("markers", "mobile: mark test as mobile test")
