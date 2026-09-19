"""Domain capability profiles — 域驱动的能力装配注册表。

每个域（domain）声明该场景下 Agent 的能力面：
  - native_tools：原生工具白名单（null = 沿用 agent_main.yaml 静态面）
  - packages 已于 v3 删除：包自声明 capability.domain，域→包目录走 DB 查询（skill_discovery.get_packages_for_domain）
  - prompt_fragments：追加到 system prompt 的域专属规则段
    （``project:`` 前缀 = 相对当前项目工作区，供项目侧声明域内容）
  - modules：hydrate 上下文模块集（null = domain_mapping 默认）

分层加载（同名域项目级覆盖引擎级）：
  1. 引擎级：app/core/engine/config/capability_profiles.yaml
  2. 项目级：{working_directory}/.evoloop/capability_profiles.yaml

兜底原则：域无 profile / 解析失败 → 全量现状，任何场景零回归。
引擎本身不预置业务域——域内容归项目侧，保持引擎通用性。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ENGINE_PROFILE_PATH = (
    Path(__file__).resolve().parent / "config" / "capability_profiles.yaml"
)
_PROJECT_PROFILE_RELPATH = ".evoloop/capability_profiles.yaml"

_cache: dict[str, dict[str, CapabilityProfile]] = {}


@dataclass
class CapabilityProfile:
    """单个域的能力面声明（全部字段可选，null = 沿用现状）。

    intent：引擎功能意图标签（如 worker_task/direct_answer），
    null = domain_mapping 默认解析。
    classifier_aliases：本域可响应的 L1 分类器标签别名（项目侧声明）——
    分类器标签集（ecommerce/shopping 等，见 docs 域词汇表小节）与项目域
    命名是两套词汇表，别名让 hint 信号首轮即可装配，不必等包反哺。
    """

    domain: str
    intent: str | None = None
    native_tools: list[str] | None = None
    prompt_fragments: list[str] = field(default_factory=list)
    modules: list[str] | None = None
    classifier_aliases: list[str] = field(default_factory=list)


def _parse(raw: dict[str, Any]) -> dict[str, CapabilityProfile]:
    profiles: dict[str, CapabilityProfile] = {}
    for domain, spec in (raw.get("domains") or {}).items():
        if not isinstance(spec, dict):
            continue
        profiles[domain] = CapabilityProfile(
            domain=domain,
            intent=spec.get("intent"),
            native_tools=spec.get("native_tools"),
            prompt_fragments=spec.get("prompt_fragments") or [],
            modules=spec.get("modules"),
            classifier_aliases=[
                str(a).strip()
                for a in (spec.get("classifier_aliases") or [])
                if str(a).strip()
            ],
        )
    return profiles


def _load(working_directory: str | None) -> dict[str, CapabilityProfile]:
    """加载并合并（项目级覆盖引擎级同名域），按工作目录缓存。"""
    cache_key = working_directory or ""
    if cache_key in _cache:
        return _cache[cache_key]

    merged: dict[str, CapabilityProfile] = {}

    try:
        if _ENGINE_PROFILE_PATH.exists():
            with open(_ENGINE_PROFILE_PATH, encoding="utf-8") as f:
                merged.update(_parse(yaml.safe_load(f) or {}))
    except Exception:
        logger.exception("[CapabilityProfiles] engine-level load failed")

    if working_directory:
        project_path = Path(working_directory) / _PROJECT_PROFILE_RELPATH
        try:
            if project_path.exists():
                with open(project_path, encoding="utf-8") as f:
                    project_profiles = _parse(yaml.safe_load(f) or {})
                merged.update(project_profiles)
                logger.info(
                    f"[CapabilityProfiles] project profiles loaded from {project_path}: "
                    f"{sorted(project_profiles)}"
                )
        except Exception:
            logger.exception("[CapabilityProfiles] project-level load failed")

    _cache[cache_key] = merged
    return merged


def list_domains(working_directory: str | None = None) -> list[str]:
    """List domains declared by the project-side capability profile."""
    return list(_load(working_directory).keys())


def get_profile(
    domain: str | None, working_directory: str | None = None
) -> CapabilityProfile | None:
    """Return the capability profile for a domain, or None (full surface).

    匹配顺序：域 key 精确匹配 → ``classifier_aliases`` 别名匹配（项目侧
    声明"该分类器标签也属于本域"，纯数据配置，引擎不含业务词汇）。
    """
    if not domain:
        return None
    profiles = _load(working_directory)
    profile = profiles.get(domain)
    if profile is not None:
        return profile
    for profile in profiles.values():
        if domain in profile.classifier_aliases:
            return profile
    return None


def _project_root_of(resource_path: str | None) -> str | None:
    """从包的 resource_path（…/<project>/.evoloop/skills/<name>）推项目根目录。

    包是 DB 全局资源，resource_path 指向源项目；profile 与包同源——
    项目根 = ``.evoloop`` 段的父目录。无 ``.evoloop`` 段返回 None。
    """
    if not resource_path:
        return None
    parts = Path(resource_path).resolve().parts
    if ".evoloop" not in parts:
        return None
    idx = parts.index(".evoloop")
    if idx == 0:
        return None
    return str(Path(*parts[:idx]))


async def resolve_profile(
    domain: str | None, working_directory: str | None
) -> tuple[CapabilityProfile, str] | None:
    """域 → profile 解析（含包归属项目回退），返回 (profile, home_wd)。

    1. 会话工作区：get_profile(domain, working_directory)——现有主路径；
    2. 包归属项目回退：包是 DB 全局资源（跨项目可见），profile 却是
       working_directory 本地文件——会话工作区 ≠ 包源项目时（如桌面会话
       跨项目调用 mall 包），按包的 resource_path 推源项目并加载其 profile。

    纯机制层：不引入任何业务域词汇；域信号仍由上游
    （host_declared > classified）决定，本函数只负责「信号 → 装配面」。

    Returns:
        (profile, profile 所属项目工作区)；无域/无 profile 返回 None。
    """
    profile = get_profile(domain, working_directory)
    if profile is not None:
        return profile, working_directory or ""
    if not domain:
        return None

    try:
        from app.core.learning.skills.discovery import skill_discovery

        packages = await skill_discovery.get_packages_for_domain(domain)
        for pkg in packages:
            home = _project_root_of(getattr(pkg, "resource_path", None))
            if not home or home == (working_directory or ""):
                continue
            home_profile = get_profile(domain, home)
            if home_profile is not None:
                logger.info(
                    "[CapabilityProfiles] domain '%s' profile resolved from "
                    "package home project: %s",
                    domain,
                    home,
                )
                return home_profile, home

        # 别名桥（跨项目）：候选标签（分类器/值守 L1 输出的 'ecommerce' 等）
        # 不是任何包的 domain 时，遍历包目录的域分组 → 包归属项目 → 对其
        # profile 做别名匹配（get_profile 内含 classifier_aliases）。
        # 纯机制：别名值归项目侧声明，引擎不含业务词汇。
        if not packages:
            for pkg_domain in await skill_discovery.get_capability_domains():
                home_packages = await skill_discovery.get_packages_for_domain(pkg_domain)
                for pkg in home_packages[:1]:
                    home = _project_root_of(getattr(pkg, "resource_path", None))
                    if not home or home == (working_directory or ""):
                        continue
                    home_profile = get_profile(domain, home)
                    if home_profile is not None:
                        logger.info(
                            "[CapabilityProfiles] label '%s' matched profile '%s' "
                            "via classifier_aliases (package home: %s)",
                            domain,
                            home_profile.domain,
                            home,
                        )
                        return home_profile, home
    except Exception:
        logger.exception(
            "[CapabilityProfiles] package-home profile fallback failed for domain '%s'",
            domain,
        )
    return None


# --- 项目级 fallback 策略（opt-in，零回归） -------------------------------
# 域/信号缺失时 ToolManager 的原生面默认沿用全量（兜底原则）；项目可在
# .evoloop/capability_profiles.yaml 顶层声明 fallback.native_tools 白名单
# 显式收窄。引擎级 yaml 不声明（保持通用）。

_fallback_cache: dict[str, list[str] | None] = {}


def get_fallback_native_tools(working_directory: str | None) -> list[str] | None:
    """项目级 fallback 白名单；未声明返回 None（沿用全量，零回归）。

    yaml 形态（项目侧）::

        fallback:
          native_tools: [skill, question, task, read]
    """
    key = working_directory or ""
    if key in _fallback_cache:
        return _fallback_cache[key]

    result: list[str] | None = None
    if working_directory and isinstance(working_directory, str):
        project_path = Path(working_directory) / _PROJECT_PROFILE_RELPATH
        try:
            if project_path.exists():
                with open(project_path, encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                tools = (raw.get("fallback") or {}).get("native_tools")
                if isinstance(tools, list) and tools:
                    result = [str(t) for t in tools]
        except Exception:
            logger.exception("[CapabilityProfiles] fallback policy load failed")
    _fallback_cache[key] = result
    return result


def session_domain_of(ctx: Any) -> str | None:
    """会话域解析（单一出处）：intent_hint.domain > session_domain（包反哺）。

    hint 域来自路由（host_declared > classified），包反哺域由 skill 激活时
    写入（react_skill）。两者都缺 → None（工具面走全量/项目 fallback）。
    """
    try:
        metadata = ctx.metadata
        hint = (
            metadata.get("intent_hint")
            if isinstance(metadata, dict)
            else getattr(metadata, "intent_hint", None)
        )
        if hint is not None:
            domain = getattr(hint, "domain", None) or (
                hint.get("domain") if isinstance(hint, dict) else None
            )
            if domain:
                return domain
        return (
            metadata.get("session_domain")
            if isinstance(metadata, dict)
            else getattr(metadata, "session_domain", None)
        )
    except Exception:
        logger.exception("[CapabilityProfiles] session domain resolution failed")
        return None


def hint_domain_of(ctx: Any) -> str | None:
    """仅取路由 hint 域（host_declared > classified），不含包反哺。"""
    try:
        metadata = ctx.metadata
        hint = (
            metadata.get("intent_hint")
            if isinstance(metadata, dict)
            else getattr(metadata, "intent_hint", None)
        )
        if hint is None:
            return None
        return getattr(hint, "domain", None) or (
            hint.get("domain") if isinstance(hint, dict) else None
        )
    except Exception:
        logger.exception("[CapabilityProfiles] hint domain resolution failed")
        return None


def feedback_domain_of(ctx: Any) -> str | None:
    """仅取包反哺域（session_domain，skill 激活时写入）。"""
    try:
        metadata = ctx.metadata
        return (
            metadata.get("session_domain")
            if isinstance(metadata, dict)
            else getattr(metadata, "session_domain", None)
        )
    except Exception:
        logger.exception("[CapabilityProfiles] feedback domain resolution failed")
        return None


async def resolve_profile_candidates(
    ctx: Any, hint_domain: str | None = None
) -> tuple[CapabilityProfile, str] | None:
    """会话 → profile 装配解析（单一出处，逐候选尝试）。

    候选顺序：hint 域 → 包反哺域；每个域先会话工作区（get_profile）、
    再包归属项目回退（resolve_profile）。

    语义要点（2026-09-18 实测教训）：hint 域（如分类器标签）若不可装配
    （无 profile 且无包归属），**不得阻塞**可装配的反哺域——分类器标签
    与包声明目录可能是两套词汇表，逐候选尝试让可装配证据胜出。
    """
    candidates: list[str] = []
    for domain in (hint_domain, feedback_domain_of(ctx)):
        if domain and domain not in candidates:
            candidates.append(domain)
    trail: list[str] = []
    for domain in candidates:
        wd_profile = get_profile(domain, getattr(ctx, "working_directory", None))
        if wd_profile is not None:
            trail.append(f"{domain}(workspace)")
            logger.info(
                "[CapabilityProfiles] domain resolution: %s -> profile '%s'",
                " -> ".join(trail),
                wd_profile.domain,
            )
            return wd_profile, getattr(ctx, "working_directory", "") or ""
        trail.append(f"{domain}(workspace miss)")
        resolved = await resolve_profile(domain, getattr(ctx, "working_directory", None))
        if resolved is not None:
            trail.append(f"{domain}(package-home)")
            logger.info(
                "[CapabilityProfiles] domain resolution: %s -> profile '%s' (home=%s)",
                " -> ".join(trail),
                resolved[0].domain,
                resolved[1],
            )
            return resolved
        trail.append(f"{domain}(unresolvable)")
    if candidates:
        logger.info(
            "[CapabilityProfiles] domain resolution: %s -> no profile "
            "(full surface / project fallback)",
            " -> ".join(trail),
        )
    return None


def reload(working_directory: str | None = None) -> None:
    if working_directory is None:
        _cache.clear()
        _fallback_cache.clear()
    else:
        _cache.pop(working_directory, None)
        _fallback_cache.pop(working_directory, None)


__all__ = [
    "CapabilityProfile",
    "get_profile",
    "get_fallback_native_tools",
    "resolve_profile",
    "resolve_profile_candidates",
    "session_domain_of",
    "hint_domain_of",
    "feedback_domain_of",
    "reload",
]
