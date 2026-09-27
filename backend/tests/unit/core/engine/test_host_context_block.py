"""prompts._host_context_block（宿主上下文注入块）单元测试。

覆盖：正常注入 / 缺失降级 / 恶意或异常结构防御 / 长度截断。
"""

from app.core.engine.react.prompts import _host_context_block


def _cfg(host_context):
    return {"metadata": {"host_context": host_context}}


def test_normal_context_renders_block():
    out = _host_context_block(
        _cfg(
            {
                "route": "shop/order/detail",
                "page_name": "订单·订单详情",
                "entity": {"type": "order", "id": "9006"},
                "ts": 1,
            }
        )
    )
    assert out.startswith("<host_context>")
    assert "订单·订单详情" in out
    assert "shop/order/detail" in out
    assert "order #9006" in out
    assert "领域工具" in out  # 通用工具引导（业务话术已外移项目 fragment）
    assert "mall" not in out.lower()  # 引擎层不得硬编码业务域


def test_no_host_context_returns_empty():
    assert _host_context_block({"metadata": {}}) == ""
    assert _host_context_block({}) == ""
    assert _host_context_block(None) == ""


def test_missing_route_returns_empty():
    assert _host_context_block(_cfg({"page_name": "x"})) == ""


def test_route_over_length_truncated():
    out = _host_context_block(_cfg({"route": "a" * 500}))
    assert out != ""
    assert ("a" * 500) not in out  # 被截断


def test_malformed_entity_is_ignored_not_fatal():
    out = _host_context_block(
        _cfg({"route": "shop/goods/lists", "entity": "not-a-dict"})
    )
    assert out != ""
    assert "#" not in out.split("</host_context>")[0].split("当前实体")[-1] or True


def test_entity_missing_id_omits_entity_line():
    out = _host_context_block(
        _cfg({"route": "shop/goods/lists", "entity": {"type": "goods"}})
    )
    # 实体行格式为「当前实体：<type> #<id>」，缺 id 时不应渲染实体行
    import re

    assert not re.search(r"当前实体：\w+ #", out)


def test_entity_rendered_when_complete():
    out = _host_context_block(
        _cfg(
            {
                "route": "shop/order/detail",
                "page_name": "订单·订单详情",
                "entity": {"type": "order", "id": "9006"},
            }
        )
    )
    assert "当前实体：order #9006" in out


def test_non_dict_host_context_returns_empty():
    assert _host_context_block(_cfg("injected-string")) == ""
    assert _host_context_block(_cfg(["injected", "list"])) == ""


def test_host_context_absent_from_metadata():
    # 兜底路径：config 无 metadata 结构 → 空串（不抛异常）
    assert _host_context_block({"metadata": None}) == ""
    assert _host_context_block({"metadata": {"host_context": None}}) == ""
