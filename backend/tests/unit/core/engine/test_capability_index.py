"""索引渲染契约（capability-packages-refactor.md v3 §5.2）。"""

from unittest.mock import MagicMock

from app.core.context.schemas import ContextMetadata
from app.core.engine.react.prompts import MAX_SKILLS, _capability_index


def _ctx(active, loaded=(), preselected=()):
    ctx = MagicMock()
    m = ContextMetadata(
        active_skills=active,
        loaded_packages=list(loaded),
        preselected_packages=list(preselected),
    )
    ctx.metadata = m
    return ctx


def _skill(name, desc="d", capability=None):
    s = MagicMock()
    s.name = name
    s.description = desc
    s.capability = capability
    # 项目级技能隔离过滤用 getattr(s, "project_id", None)：MagicMock 属性
    # 是 Mock 对象而非 None，会被 "project_id is None" 分支误杀 → 显式置 None
    s.project_id = None
    return s


class TestCapabilityIndexMarkers:
    def _active(self):
        return [
            _skill("mall-orders", "订单查询与管理。"),
            _skill("mall-channel", "社媒内容运营。"),
            _skill("plain-skill", "普通技能。"),
        ]

    def test_preselected_and_loaded_marked(self) -> None:
        ctx = _ctx(self._active(), loaded=["mall-channel"], preselected=["mall-orders"])
        block = _capability_index(ctx)
        assert "mall-orders: 订单查询与管理。 [已预挂（写操作需先加载本包）]" in block
        assert "mall-channel: 社媒内容运营。 [已加载，工具可用]" in block

    def test_plain_skill_unmarked(self) -> None:
        ctx = _ctx(self._active(), loaded=["mall-channel"], preselected=["mall-orders"])
        block = _capability_index(ctx)
        assert "plain-skill" in block and "已预挂" not in block.split("plain-skill")[1][:30]


def _mk_item(name: str, desc: str = "d"):
    from types import SimpleNamespace

    return SimpleNamespace(name=name, description=desc)


class _Ctx:
    def __init__(self, metadata):
        self.metadata = metadata


def test_domain_ranking_keeps_domain_packages_under_truncation():
    """域裁剪：通用技能再多也不挤掉域内包（v3 mall-orders 事故同构场景）。"""
    items = [_mk_item(f"generic-{i:02d}", "g") for i in range(45)]
    items += [
        _mk_item("mall-orders", "订单包"),
        _mk_item("mall-refunds", "退款包"),
    ]
    ctx = _Ctx(
        {
            "active_skills": items,
            "loaded_packages": [],
            "preselected_packages": ["mall-orders"],
        }
    )
    out = _capability_index(ctx, domain_pkgs={"mall-orders", "mall-refunds"})
    assert "mall-orders" in out and "已预挂" in out
    assert "mall-refunds" in out
    assert "另有" in out  # 截断尾注
    # 域内包必须出现在截断线内：计数行数
    lines = [l for l in out.splitlines() if l.startswith("- ")]
    body = [l for l in lines if not l.startswith("- …（")]
    assert len(body) <= MAX_SKILLS


def test_domain_ranking_order_loaded_first():
    items = [_mk_item("generic-1"), _mk_item("mall-orders"), _mk_item("mall-refunds")]
    ctx = _Ctx(
        {
            "active_skills": items,
            "loaded_packages": ["mall-refunds"],
            "preselected_packages": ["mall-orders"],
        }
    )
    out = _capability_index(ctx, domain_pkgs={"mall-orders", "mall-refunds"})
    idx_loaded = out.index("mall-refunds")
    idx_pre = out.index("mall-orders")
    idx_generic = out.index("generic-1")
    assert idx_loaded < idx_pre < idx_generic
