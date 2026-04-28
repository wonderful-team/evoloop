"""
Baseline Latency Test for edit_file (v5.2.9)

Run before upgrade to freeze current latency profile.
pytest tests/baseline/test_edit_latency_baseline.py -v
"""

import asyncio
import os
import tempfile
import time
import json
from unittest.mock import patch

import pytest

from app.domain.tools.files.edit_file import handle_edit
from app.domain.tools.schemas import EditFileRequest


class TestEditLatencyBaseline:
    """Freeze baseline latency for simple edits."""

    @pytest.fixture
    def sample_file(self):
        from app.core.tools import get_working_directory
        import uuid

        lines = [f"def func_{i}():\n    return {i}\n" for i in range(200)]
        content = "\"\"\"Large sample module.\"\"\"\n\n" + "".join(lines)
        root = get_working_directory(None)
        path = os.path.join(root, f"latency_test_{uuid.uuid4().hex}.py")
        with open(path, 'w') as f:
            f.write(content)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_baseline_latency_simple_edit(self, sample_file):
        target = "def func_50():\n    return 50\n"
        replacement = "def func_50():\n    return 9999\n"

        latencies = []
        engine_call_counts = []

        for i in range(10):
            # Reset file
            base_lines = [f"def func_{j}():\n    return {j}\n" for j in range(200)]
            base_content = "\"\"\"Large sample module.\"\"\"\n\n" + "".join(base_lines)
            with open(sample_file, 'w') as f:
                f.write(base_content)

            # Count EditEngine calls by patching apply_replacement
            from app.core.file.editor import EditEngine
            original_apply = EditEngine.apply_replacement
            call_count = [0]

            def tracked_apply(content, old_string, new_string, replace_all=False):
                call_count[0] += 1
                return original_apply(content, old_string, new_string, replace_all)

            with patch.object(EditEngine, 'apply_replacement', staticmethod(tracked_apply)):
                start = time.perf_counter()
                result = await handle_edit(
                    EditFileRequest(
                        path=sample_file,
                        target=target,
                        content=replacement,
                        allow_multiple=False,
                        expected_hash=None,
                        verify_types=False,
                        config=None
                    )
                )
                latency_ms = (time.perf_counter() - start) * 1000

            latencies.append(latency_ms)
            engine_call_counts.append(call_count[0])
            print(f"Run {i+1}: {latency_ms:.2f}ms, engine_calls={call_count[0]}")

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        avg_engine_calls = sum(engine_call_counts) / len(engine_call_counts)

        summary = {
            "runs": 10,
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "avg_engine_calls": round(avg_engine_calls, 2),
            "all_latencies_ms": [round(x, 2) for x in latencies]
        }

        report_path = "reports/baseline_edit_latency.json"
        with open(report_path, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"\nBaseline Latency: p50={p50:.2f}ms, p95={p95:.2f}ms, avg_engine_calls={avg_engine_calls:.2f}")
        print(f"Report written to {report_path}")

        # Soft assertions: just ensure it runs in reasonable time
        assert p95 < 5000, f"p95 latency unexpectedly high: {p95}ms"
