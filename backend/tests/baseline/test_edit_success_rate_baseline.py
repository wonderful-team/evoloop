"""
Baseline Success Rate Test for edit_file (v5.2.9)

Run before upgrade to freeze current behavior.
pytest tests/baseline/test_edit_success_rate_baseline.py -v
"""

import asyncio
import os
import time
import json
import uuid
from dataclasses import dataclass, asdict
from typing import List

import pytest

from app.domain.tools.files.edit_file import handle_edit
from app.core.tools import get_working_directory


@dataclass
class BaselineResult:
    scenario_id: str
    description: str
    success: bool
    first_attempt_success: bool  # True if apply_edit_with_verification succeeded
    fallback_success: bool       # True if EditEngine fallback succeeded
    latency_ms: float
    output_preview: str


class TestEditSuccessRateBaseline:
    """Freeze baseline success rate for edit_file in v5.2.9."""

    @pytest.fixture
    def sample_file(self):
        # Create file inside the allowed workspace root
        root = get_working_directory(None)
        path = os.path.join(root, f"baseline_test_{uuid.uuid4().hex}.py")
        content = '''"""Sample module."""

import os


def foo():
    """Old function."""
    return True


def baz():
    """Another function."""
    return False


class Config:
    def __init__(self):
        self.debug = True
        self.timeout = 30

    def validate(self):
        return self.timeout > 0


def process(items):
    results = []
    for item in items:
        if item:
            results.append(item.strip())
    return results
'''
        with open(path, 'w') as f:
            f.write(content)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    async def _run_scenario(self, scenario_id: str, description: str, path: str, target: str, replacement: str):
        start = time.perf_counter()
        result = await handle_edit(
            path=path,
            target=target,
            content=replacement,
            allow_multiple=False,
            expected_hash=None,
            verify_types=False,
            config=None
        )
        latency_ms = (time.perf_counter() - start) * 1000

        success = "success" in result.lower() or "✅" in result or "fuzzy match" in result.lower()
        fallback_success = "fuzzy match" in result.lower()
        first_attempt_success = success and not fallback_success

        return BaselineResult(
            scenario_id=scenario_id,
            description=description,
            success=success,
            first_attempt_success=first_attempt_success,
            fallback_success=fallback_success,
            latency_ms=latency_ms,
            output_preview=result[:200].replace("\n", " ")
        )

    @pytest.mark.asyncio
    async def test_baseline_all_scenarios(self, sample_file):
        scenarios = [
            # Exact matches
            ("BASE-01", "Exact match", "def foo():\n    \"\"\"Old function.\"\"\"\n    return True", "def bar():\n    \"\"\"New function.\"\"\"\n    return True"),
            # True fuzzy: indentation normalized (3 spaces instead of 4)
            ("BASE-02", "Indentation diff (3 spaces vs 4)", "   return True", "   return False"),
            # True fuzzy: trailing whitespace added to target
            ("BASE-03", "Trailing whitespace diff", "    return False ", "    return False"),
            # True fuzzy: missing blank line in target
            ("BASE-04", "Missing blank line", "def baz():\n    \"\"\"Another function.\"\"\"\n    return False", "def qux():\n    pass"),
            # Block anchor fuzzy: slight content change in middle
            ("BASE-05", "Block anchor fuzzy", "    def __init__(self):\n        self.debug = True\n        self.timeout = 30", "    def __init__(self):\n        self.debug = False\n        self.timeout = 60"),
            # Short target
            ("BASE-06", "Short target (< 3 chars)", "os", "sys"),
            # Multiple occurrences no context
            ("BASE-07", "Multiple occurrences no context", "    return True", "    return None"),
            # Multiple occurrences with context
            ("BASE-08", "Multiple occurrences with context", "    def validate(self):\n        return self.timeout > 0", "    def validate(self):\n        return self.timeout >= 0"),
            # Empty old string
            ("BASE-09", "Empty old string (append)", "", "# End of file\n"),
            # Large unique block
            ("BASE-10", "Large unique block", "def process(items):\n    results = []\n    for item in items:\n        if item:\n            results.append(item.strip())\n    return results", "def process(items):\n    return [item.strip() for item in items if item]"),
        ]

        results: List[BaselineResult] = []
        for sid, desc, target, replacement in scenarios:
            # Reset file content for each scenario
            base_content = '''"""Sample module."""

import os


def foo():
    """Old function."""
    return True


def baz():
    """Another function."""
    return False


class Config:
    def __init__(self):
        self.debug = True
        self.timeout = 30

    def validate(self):
        return self.timeout > 0


def process(items):
    results = []
    for item in items:
        if item:
            results.append(item.strip())
    return results
'''
            with open(sample_file, 'w') as f:
                f.write(base_content)

            result = await self._run_scenario(sid, desc, sample_file, target, replacement)
            results.append(result)
            print(f"[{sid}] {desc}: success={result.success}, first={result.first_attempt_success}, fallback={result.fallback_success}, latency={result.latency_ms:.1f}ms")

        # Summary
        total = len(results)
        first_success = sum(1 for r in results if r.first_attempt_success)
        fallback_success = sum(1 for r in results if r.fallback_success)
        total_success = sum(1 for r in results if r.success)
        avg_latency = sum(r.latency_ms for r in results) / total

        summary = {
            "total": total,
            "first_attempt_success": first_success,
            "fallback_success": fallback_success,
            "total_failure": total - total_success,
            "avg_latency_ms": round(avg_latency, 2),
            "details": [asdict(r) for r in results]
        }

        report_path = "reports/baseline_edit_success_rate.json"
        os.makedirs("reports", exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"\nBaseline Summary: {first_success}/{total} first-attempt, {fallback_success} fallback, {total - total_success} failed, avg_latency={avg_latency:.1f}ms")
        print(f"Report written to {report_path}")

        # We don't assert strict values here because this is a baseline freeze.
        # Just ensure the test runs and produces a report.
        assert total == len(scenarios)
