"""Unit tests for ``ToolState.get_summary``（解耦后契约）。

解耦后：不再从 ``affected_path_keys`` 推导 is_file_content（UI 语义已移交给
``tool_meta.affected_paths``），``get_summary`` 只做纯文本摘要格式化。
"""

from app.core.context.tool_state import ToolState


def _state(**meta_overrides):
    metadata = {"summary_template": None}
    metadata.update(meta_overrides)
    return ToolState(
        name="edit_file",
        arguments="{}",
        start_time=0.0,
        path="/tmp/f.py",
        metadata=metadata,
    )


def test_returns_string_not_tuple():
    """契约：返回 str（解耦前是 (summary, is_file_content) 元组）。"""
    s = _state()
    result = s.get_summary("some output")
    assert isinstance(result, str)
    assert result == "some output"


def test_uses_summary_template_with_path():
    s = _state(summary_template="domain_tools.files.edit_success")
    result = s.get_summary("x\n" * 5)
    assert isinstance(result, str)
    assert "f.py" in result


def test_truncates_long_output():
    s = _state()
    long_output = "line\n" * 200  # >500 字符 且 >20 行
    result = s.get_summary(long_output)
    assert isinstance(result, str)
    assert "[Truncated" in result
    assert len(result) < len(long_output)


def test_does_not_depend_on_affected_path_keys():
    """解耦核心：summary 结果与 affected_path_keys 无关（不再推导 is_file_content）。"""
    with_keys = _state(affected_path_keys=["path"]).get_summary("out")
    without_keys = _state().get_summary("out")
    assert with_keys == without_keys == "out"
