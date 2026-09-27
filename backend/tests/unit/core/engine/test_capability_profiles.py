"""Capability profiles（域驱动能力装配注册表）单元测试。

覆盖：引擎级/项目级分层加载（项目覆盖引擎）、profile 字段语义、兜底原则。
域内容归项目侧——引擎不预置业务域。
"""

import textwrap

import pytest

from app.core.engine.capability_profiles import get_profile, reload


@pytest.fixture(autouse=True)
def _fresh_cache():
    reload()
    yield
    reload()


def test_engine_level_profile_loads():
    # 引擎级 yaml 当前不预置业务域（通用性原则）——未知域应无 profile
    assert get_profile("mall_ops") is None
    assert get_profile(None) is None
    assert get_profile("") is None


def test_project_level_profile_overrides(tmp_path):
    project_dir = tmp_path / "proj"
    (project_dir / ".evoloop").mkdir(parents=True)
    (project_dir / ".evoloop" / "capability_profiles.yaml").write_text(
        textwrap.dedent(
            """\
            domains:
              mall_ops:
                intent: worker_task
                native_tools: [webfetch, plan]
                prompt_fragments: ["project:.evoloop/fragments/mall_ops.md"]
                modules: [Base, Skill]
            """
        ),
        encoding="utf-8",
    )
    wd = str(project_dir)

    p = get_profile("mall_ops", working_directory=wd)
    assert p is not None
    assert p.intent == "worker_task"
    assert p.native_tools == ["webfetch", "plan"]
    # C3（v2）/v3：mcp_allowlist 与 packages 字段均已删除——
    # 域→包目录走 DB（包自声明 capability.domain）
    assert not hasattr(p, "mcp_allowlist")
    assert not hasattr(p, "packages")
    assert p.modules == ["Base", "Skill"]
    assert p.prompt_fragments == ["project:.evoloop/fragments/mall_ops.md"]


def test_project_level_unknown_domain_still_none(tmp_path):
    reload()
    # 项目 profile 存在但域未声明 → None（全量兜底）
    assert get_profile("nope", working_directory=str(tmp_path)) is None


def test_working_directory_scoped_cache(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    (a / ".evoloop").mkdir(parents=True)
    (b / ".evoloop").mkdir(parents=True)
    (a / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  d1:\n    intent: worker_task\n", encoding="utf-8"
    )
    (b / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  d2:\n    intent: direct_answer\n", encoding="utf-8"
    )

    assert get_profile("d1", working_directory=str(a)) is not None
    assert get_profile("d1", working_directory=str(b)) is None
    assert get_profile("d2", working_directory=str(b)) is not None
    assert get_profile("d2", working_directory=str(a)) is None


def test_reload_clears_working_directory_cache(tmp_path):
    wd = str(tmp_path)
    evoloop_dir = tmp_path / ".evoloop"
    evoloop_dir.mkdir(parents=True)
    cfg = evoloop_dir / "capability_profiles.yaml"

    # 首次加载（文件不存在）→ 无 profile
    assert get_profile("x", working_directory=wd) is None
    # 写入文件：未 reload 时旧缓存仍生效
    cfg.write_text("domains:\n  x:\n    intent: worker_task\n", encoding="utf-8")
    assert get_profile("x", working_directory=wd) is None
    # reload 该 wd 后读到新 profile
    reload(wd)
    assert get_profile("x", working_directory=wd) is not None


def test_engine_yaml_remains_domain_agnostic():
    """通用性回归锁：引擎级 yaml 的 domains 不声明业务域（仅机制与示例）。"""
    from app.core.engine.capability_profiles import _load

    engine_profiles = _load("")
    business_domains = {"mall_ops"}
    declared = set(engine_profiles)
    assert not (declared & business_domains), f"业务域泄漏进引擎级: {declared & business_domains}"


# ---------------------------------------------------------------------------
# resolve_profile：包归属项目回退（2026-09-18）
# ---------------------------------------------------------------------------


def _mk_pkg(resource_path: str | None):
    from types import SimpleNamespace

    return SimpleNamespace(name="pkg", resource_path=resource_path)


@pytest.mark.asyncio
async def test_resolve_profile_falls_back_to_package_home(tmp_path, monkeypatch):
    """会话工作区无 profile、包源项目有 → 按包 resource_path 推源项目解析。"""
    from unittest.mock import AsyncMock

    from app.core.engine.capability_profiles import reload, resolve_profile

    reload()
    home = tmp_path / "mall-backend"
    (home / ".evoloop").mkdir(parents=True)
    (home / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  mall_ops:\n    native_tools: [skill, question]\n",
        encoding="utf-8",
    )
    session_wd = tmp_path / "other-project"
    session_wd.mkdir()

    async def fake_get_packages_for_domain(domain):
        assert domain == "mall_ops"
        return [_mk_pkg(str(home / ".evoloop" / "skills" / "mall-products"))]

    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(side_effect=fake_get_packages_for_domain),
    )

    resolved = await resolve_profile("mall_ops", str(session_wd))
    assert resolved is not None
    profile, home_wd = resolved
    assert profile.native_tools == ["skill", "question"]
    assert home_wd == str(home)


@pytest.mark.asyncio
async def test_resolve_profile_session_wd_first(tmp_path):
    """会话工作区有 profile 时不做回退，home_wd = 会话工作区。"""
    from app.core.engine.capability_profiles import reload, resolve_profile

    reload()
    proj = tmp_path / "proj"
    (proj / ".evoloop").mkdir(parents=True)
    (proj / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  d1:\n    native_tools: [read]\n", encoding="utf-8"
    )
    resolved = await resolve_profile("d1", str(proj))
    assert resolved is not None
    assert resolved[1] == str(proj)


@pytest.mark.asyncio
async def test_resolve_profile_none_without_domain_or_profile(tmp_path, monkeypatch):
    """无域 → None；有域但无 profile 且包无 .evoloop 段 → None。"""
    from unittest.mock import AsyncMock

    from app.core.engine.capability_profiles import reload, resolve_profile

    reload()
    assert await resolve_profile(None, str(tmp_path)) is None

    async def fake(_domain):
        return [_mk_pkg("/opt/some/skills/x")]  # 无 .evoloop 段

    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(side_effect=fake),
    )
    assert await resolve_profile("d1", str(tmp_path)) is None


@pytest.mark.asyncio
async def test_alias_bridge_cross_project(tmp_path, monkeypatch):
    """别名桥：候选标签 'ecommerce' 不是包 domain，但包归属项目的 profile
    声明了该别名 → 跨项目命中 mall_ops（值守/单发会话首轮收窄的前提）。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.core.engine.capability_profiles import reload, resolve_profile

    reload()
    home = tmp_path / "mall-backend"
    (home / ".evoloop").mkdir(parents=True)
    (home / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n"
        "  mall_ops:\n"
        "    native_tools: [skill, question]\n"
        "    classifier_aliases: [ecommerce, shopping]\n",
        encoding="utf-8",
    )
    session = tmp_path / "session"
    session.mkdir()

    async def fake_get_packages_for_domain(d):
        return (
            [
                SimpleNamespace(
                    resource_path=str(home / ".evoloop" / "skills" / "mall-products")
                )
            ]
            if d == "mall_ops"
            else []
        )

    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(side_effect=fake_get_packages_for_domain),
    )
    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_capability_domains",
        AsyncMock(return_value=["mall_ops"]),
    )

    resolved = await resolve_profile("ecommerce", str(session))
    assert resolved is not None
    profile, home_wd = resolved
    assert profile.domain == "mall_ops"
    assert home_wd == str(home)


@pytest.mark.asyncio
async def test_alias_bridge_requires_declared_alias(tmp_path, monkeypatch):
    """包归属项目未声明该别名 → 不命中（opt-in 锁，fail-open 全量）。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.core.engine.capability_profiles import reload, resolve_profile

    reload()
    home = tmp_path / "mall-backend"
    (home / ".evoloop").mkdir(parents=True)
    (home / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  mall_ops:\n    native_tools: [skill]\n",  # 无 classifier_aliases
        encoding="utf-8",
    )
    session = tmp_path / "session"
    session.mkdir()

    async def fake(d):
        return (
            [SimpleNamespace(resource_path=str(home / ".evoloop" / "skills" / "x"))]
            if d == "mall_ops"
            else []
        )

    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(side_effect=fake),
    )
    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_capability_domains",
        AsyncMock(return_value=["mall_ops"]),
    )
    assert await resolve_profile("ecommerce", str(session)) is None


# ---------------------------------------------------------------------------
# get_fallback_native_tools：项目级 opt-in 兜底策略
# ---------------------------------------------------------------------------


def test_fallback_policy_declared_and_undeclared(tmp_path):
    from app.core.engine.capability_profiles import (
        get_fallback_native_tools,
        reload,
    )

    reload()
    # 未声明 → None（全量现状）
    assert get_fallback_native_tools(str(tmp_path)) is None

    (tmp_path / ".evoloop").mkdir()
    (tmp_path / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains: {}\nfallback:\n  native_tools: [skill, question, task, read]\n",
        encoding="utf-8",
    )
    reload(str(tmp_path))
    assert get_fallback_native_tools(str(tmp_path)) == ["skill", "question", "task", "read"]
    # 非字符串工作目录（防御 MagicMock 场景）→ None，不抛异常
    assert get_fallback_native_tools(None) is None


def test_reload_clears_fallback_cache(tmp_path):
    from app.core.engine.capability_profiles import (
        get_fallback_native_tools,
        reload,
    )

    reload()
    assert get_fallback_native_tools(str(tmp_path)) is None
    (tmp_path / ".evoloop").mkdir()
    (tmp_path / ".evoloop" / "capability_profiles.yaml").write_text(
        "fallback:\n  native_tools: [read]\n", encoding="utf-8"
    )
    # 未 reload → 旧缓存仍生效
    assert get_fallback_native_tools(str(tmp_path)) is None
    reload(str(tmp_path))
    assert get_fallback_native_tools(str(tmp_path)) == ["read"]


# ---------------------------------------------------------------------------
# classifier_aliases：分类器标签别名（2026-09-18 实测教训：50% 会话单发，
# 反哺来不及触发；别名让 hint 首轮即装配）
# ---------------------------------------------------------------------------


def test_hint_resolves_via_classifier_alias(tmp_path):
    """hint 域 'ecommerce' 无精确 key → 命中声明了别名的 mall_ops profile。"""
    from app.core.engine.capability_profiles import reload

    reload()
    (tmp_path / ".evoloop").mkdir()
    (tmp_path / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n"
        "  mall_ops:\n"
        "    native_tools: [skill, question]\n"
        "    classifier_aliases: [ecommerce, shopping]\n",
        encoding="utf-8",
    )
    reload(str(tmp_path))
    # 别名命中
    p = get_profile("ecommerce", str(tmp_path))
    assert p is not None and p.domain == "mall_ops"
    p = get_profile("shopping", str(tmp_path))
    assert p is not None and p.domain == "mall_ops"
    # 精确 key 优先语义不变；未声明别名不误命中
    assert get_profile("mall_ops", str(tmp_path)) is not None
    assert get_profile("coding_dev", str(tmp_path)) is None


def test_alias_requires_project_declaration(tmp_path):
    """未声明别名的 profile 不被别名命中（opt-in 锁）。"""
    reload()
    (tmp_path / ".evoloop").mkdir()
    (tmp_path / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  mall_ops:\n    native_tools: [skill]\n", encoding="utf-8"
    )
    reload(str(tmp_path))
    assert get_profile("ecommerce", str(tmp_path)) is None
