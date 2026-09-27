"""2026-09-19 值守日志分析发现的三处修复契约。

1. Context Monitor 注入为**替换式**：消息流中始终只有最新一块
   （旧实现逐轮追加，值守长 run 线性膨胀数千 token）；
2. glob 工具：pattern 含通配符时走 fnmatch（旧实现子串匹配，"*" 恒空），
   纯文本保持子串语义向后兼容；
3. plan steps 格式说明（agent 实测误用 description 键被拒重试）。
"""

from __future__ import annotations

from app.core.engine.message.native_classes import HumanMessage


def _human(content) -> HumanMessage:
    return HumanMessage(content=content)





def test_glob_pattern_matches_wildcard(tmp_path):
    import asyncio

    from app.core.file.tools.find_files import _search_by_name

    (tmp_path / "a.xml").write_text("<x/>")
    (tmp_path / "b.py").write_text("x=1")

    out, meta = asyncio.run(_search_by_name("*", str(tmp_path), None, False, 20))
    assert meta["count"] == 2  # 旧实现传 "*" 恒空

    out, meta = asyncio.run(_search_by_name("*.xml", str(tmp_path), None, False, 20))
    assert meta["count"] == 1 and "a.xml" in out


def test_glob_plain_text_still_substring(tmp_path):
    import asyncio

    from app.core.file.tools.find_files import _search_by_name

    (tmp_path / "order_list.py").write_text("x=1")
    (tmp_path / "goods.xml").write_text("<x/>")

    out, meta = asyncio.run(_search_by_name("order", str(tmp_path), None, False, 20))
    assert meta["count"] == 1 and "order_list.py" in out


def test_context_filter_survives_partial_ctx(monkeypatch):
    """日志 filter 遇到无 thread_id 的 ctx 替身不得抛异常（生产等价：
    任何缺字段的 context 对象都不该让 logging 炸穿业务调用）。"""
    import logging

    from app.core.context.manager import ContextManager
    from app.logging import ContextFilter

    class _BrokenCtx:
        project_id = 7  # 没有 thread_id

    monkeypatch.setattr(
        ContextManager, "current", staticmethod(lambda: _BrokenCtx())
    )
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", None, None)
    assert ContextFilter().filter(record) is True
    assert record.thread_id == "-"
    assert record.project_id == 7
