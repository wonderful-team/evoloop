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
    """

    domain: str
    intent: str | None = None
    native_tools: list[str] | None = None
    prompt_fragments: list[str] = field(default_factory=list)
    modules: list[str] | None = None


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
    """Return the capability profile for a domain, or None (full surface)."""
    if not domain:
        return None
    return _load(working_directory).get(domain)


def reload(working_directory: str | None = None) -> None:
    if working_directory is None:
        _cache.clear()
    else:
        _cache.pop(working_directory, None)


__all__ = ["CapabilityProfile", "get_profile", "reload"]
