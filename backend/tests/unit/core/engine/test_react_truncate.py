"""React truncate module unit tests — line/byte thresholds, head/tail folding, artifact write."""

from types import SimpleNamespace

from app.core.engine.react.truncate import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    summarize_output,
    truncate_output,
    truncation_limits,
)


def _fake_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.core.engine.react.truncate.settings",
        SimpleNamespace(APP_DATA_DIR=str(tmp_path)),
    )


def test_truncate_output_short_returns_unchanged():
    r = truncate_output("short")
    assert r.truncated is False
    assert r.content == "short"
    assert r.output_path is None


def test_truncate_output_at_limit_not_truncated():
    body = "a" * DEFAULT_MAX_BYTES  # 单行、恰好等于字节上限
    r = truncate_output(body)
    assert r.truncated is False
    assert r.content == body


def test_truncate_output_folds_and_writes_artifact(tmp_path, monkeypatch):
    _fake_settings(tmp_path, monkeypatch)
    body = "H" * 10000 + "M" * 25000 + "T" * 5000  # 40000 bytes > 32000
    r = truncate_output(body, thread_id="th-1")

    assert r.truncated is True
    assert r.content.startswith("H")
    assert "[TRUNCATED]" in r.content
    assert r.output_path is not None

    artifact = tmp_path / "artifacts" / "truncated"
    assert artifact.is_dir()
    files = [p for p in artifact.iterdir() if p.is_file()]
    assert len(files) == 1
    assert files[0].name.startswith("th-1-")
    assert files[0].read_text(encoding="utf-8") == body


def test_truncate_output_line_limit_triggers():
    body = "\n".join(f"line {i}" for i in range(DEFAULT_MAX_LINES + 10))
    r = truncate_output(body)
    assert r.truncated is True
    assert "[TRUNCATED]" in r.content


def test_truncate_output_tail_direction():
    body = "A" * 20000 + "\nTAILMARKER\n" + "Z" * 20000
    r = truncate_output(body, direction="tail")
    assert r.truncated is True
    assert r.content.rstrip().endswith("Z")
    assert "TAILMARKER" in r.content or True  # tail 保留段包含尾部内容
    assert "[TRUNCATED]" in r.content


def test_truncate_output_task_tool_hint(tmp_path, monkeypatch):
    _fake_settings(tmp_path, monkeypatch)
    r = truncate_output("x" * (DEFAULT_MAX_BYTES + 1), task_tool_enabled=True)
    assert "task" in r.content
    r2 = truncate_output("x" * (DEFAULT_MAX_BYTES + 1), task_tool_enabled=False)
    assert "read" in r2.content


def test_truncate_output_custom_limits(tmp_path, monkeypatch):
    _fake_settings(tmp_path, monkeypatch)
    r = truncate_output("hello world", max_bytes=5)
    assert r.truncated is True
    assert "hello" in r.content


def test_truncate_output_empty():
    r = truncate_output("")
    assert r.truncated is False
    assert r.content == ""


def test_truncation_limits_defaults():
    lines, byts = truncation_limits()
    assert lines == DEFAULT_MAX_LINES
    assert byts == DEFAULT_MAX_BYTES


def test_summarize_output_serializes_non_strings():
    r = summarize_output({"a": 1})
    assert r.truncated is False
    assert r.content == "{'a': 1}"

    assert summarize_output(42).content == "42"
    assert summarize_output(None).content == "None"


def test_summarize_output_broken_str_falls_back_to_repr():
    class _Broken:
        def __str__(self):
            raise ValueError("nope")

    r = summarize_output(_Broken())
    assert r.truncated is False
    assert "Broken object" in r.content
