"""Unit tests for P1.3: verify raw open() is eliminated from target modules."""

import importlib.util
import re


def _read_module_source(module_name: str) -> str:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, f"Module {module_name} not found"
    assert spec.origin is not None
    with open(spec.origin, "r") as f:
        return f.read()


def _has_raw_open(source: str) -> list[str]:
    """Return list of lines containing bare open( calls (not in imports/strings)."""
    bad: list[str] = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if "import " in stripped:
            continue
        if re.search(r'(?<!=)\bopen\(', stripped):
            if "read_file" not in stripped and "write_file" not in stripped:
                bad.append(f"  L{i}: {stripped}")
    return bad


class TestFilterNoRawOpen:
    def test_uses_read_file(self):
        src = _read_module_source("app.domain.codebase.filter")
        assert "read_file" in src
        bad = _has_raw_open(src)
        assert not bad, f"raw open() calls found:\n" + "\n".join(bad)


class TestCodeAnalyzerNoRawOpen:
    def test_uses_read_file(self):
        src = _read_module_source("app.domain.codebase.analysis.code_analyzer")
        assert "read_file" in src
        bad = _has_raw_open(src)
        assert not bad, f"raw open() calls found:\n" + "\n".join(bad)


class TestDirectorySummarizerNoRawOpen:
    def test_uses_write_file(self):
        src = _read_module_source("app.domain.codebase.indexing.directory_summarizer")
        assert "write_file" in src or "read_file" in src
        bad = _has_raw_open(src)
        assert not bad, f"raw open() calls found:\n" + "\n".join(bad)


class TestProjectUtilsNoRawOpen:
    def test_uses_read_file(self):
        src = _read_module_source("app.core.project.utils")
        assert "read_file" in src or "write_file_with_verification" in src
        bad = _has_raw_open(src)
        assert not bad, f"raw open() calls found:\n" + "\n".join(bad)


class TestDynamicToolsNoRawOpen:
    def test_uses_write_file(self):
        src = _read_module_source("app.domain.tools.dynamic")
        assert "write_file" in src
        bad = _has_raw_open(src)
        assert not bad, f"raw open() calls found:\n" + "\n".join(bad)
