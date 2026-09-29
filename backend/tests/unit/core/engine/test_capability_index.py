"""索引渲染契约（capability-packages-refactor.md v3 §5.2）。"""

import os
import re
from pathlib import Path
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
    lines = [line for line in out.splitlines() if line.startswith("- ")]
    body = [line for line in lines if not line.startswith("- …（")]
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


# ===================== 真实数据回归（2026-09-23 事故形态） =====================
# 事故记录：prompts.py 截断注释 / user.py duty 跳 L0 注释 —— Upwork 侦察轮，
# Agent Reach 被域过滤/截断藏出 <available_skills>，Agent 退化为 webfetch 死循环。
# 本节用仓库内置真实 SKILL.md（app/config/skills）解析出的 name+description
# 作为通用技能数据源，锁定渲染层的两个面：
#   正面：无域会话全量可见（当前数据 15<20 恒不截断的保障来源）
#   反面（已知缺口，故意固化）：域会话域包超载时通用技能全灭——
#   scope: universal 落地后需把 test_domain_overload 中 universal 代表的断言翻转为可见。

_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parents[4] / "app" / "config" / "skills"


def _parse_builtin_skills() -> list:
    """解析 app/config/skills/*/SKILL.md frontmatter 的 name+description（真实数据）。"""
    items = []
    for d in sorted(os.listdir(_BUILTIN_SKILLS_DIR)):
        md = _BUILTIN_SKILLS_DIR / d / "SKILL.md"
        if not md.is_file():
            continue
        text = md.read_text(encoding="utf-8")
        m = re.search(r"^---\n(.*?)\n---", text, re.S)
        if not m:
            continue
        fm = m.group(1)
        name_m = re.search(r"^name:\s*(.+)$", fm, re.M)
        desc_m = re.search(r"^description:\s*>-?\s*\n((?:  .+\n?)+)", fm, re.M)
        name = name_m.group(1).strip() if name_m else d
        desc = (
            re.sub(r"\s+", " ", " ".join(ln.strip() for ln in desc_m.group(1).splitlines()))
            if desc_m
            else name
        )[:160]
        items.append(_skill(name, desc))
    return items


def test_no_domain_session_shows_all_real_builtin_skills():
    """控制组：无域会话（domain_pkgs=None）→ 内置真实技能全量可见、不截断。"""
    items = _parse_builtin_skills()
    assert len(items) >= 5, "内置技能解析失败，数据源异常"
    out = _capability_index(_ctx(items))
    lines = [ln.lstrip("- ") for ln in out.splitlines() if ln.startswith("- ")]
    names = [ln.split(":", 1)[0].strip() for ln in lines]
    for item in items:
        assert item.name in names, f"无域会话下 {item.name} 不可见"
    assert "另有" not in out, "无域会话不应出现截断尾注"


def test_domain_overload_hides_all_generic_skills():
    """反面固化（已知缺口）：域会话 + 域包超载 → 通用技能（含 reach 类）整组消失。

    域包为合成数据（真实项目侧 .evoloop/skills 的域包随项目注入，不可在单测
    固定）；通用技能为真实内置 SKILL.md 解析结果。断言的是当前实现的结构性
    行为：无 capability.domain 的技能永远排在截断区，域包数 ≥ MAX_SKILLS 时
    全部不可见。scope: universal 落地后此测试需同步更新。
    """
    items = _parse_builtin_skills()
    domain_pkgs = [_skill(f"mall-domain-pkg-{i:02d}", f"项目域包 {i}") for i in range(25)]
    out = _capability_index(
        _ctx(items + domain_pkgs, preselected=["mall-domain-pkg-00"]),
        domain_pkgs={p.name for p in domain_pkgs},
    )
    body = [
        ln.lstrip("- ").split(":")[0].strip()
        for ln in out.splitlines()
        if ln.startswith("- ") and not ln.startswith("- …（")
    ]
    # 前 20 全部被域包占据（preselected 1 + domain 19），通用技能 0 幸存
    assert sum(1 for n in body if n.startswith("mall-domain")) == MAX_SKILLS
    for item in items:
        assert item.name not in body, f"域超载下 {item.name} 意外可见（排序或 cap 回归）"
    assert "另有" in out, "超载场景必须出现截断尾注"
