"""
Voice router — L0 matching and intent resolution for voice input.

Extracted from VoiceInputChannel (channel/input/) into routing/ so that
routing decisions live in the routing layer.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.execution.macro.runner import is_navigation_macro
from app.core.routing.executor import (
    dispatch_macro,
    handle_builtin,
    handle_navigate,
)
from app.core.routing.init_spec import _TEMPLATES
from app.core.routing.intent_classifier import predict as classifier_predict
from app.core.routing.router import get_local_matcher
from app.infrastructure.database import session_scope
from app.models.macro import Macro
from sqlmodel import select

logger = logging.getLogger(__name__)


# ── 直接路由表 ──────────────────────────────────────────────

DIRECT_ROUTES: dict[str, str] = {
    "显示主界面": "/chat",
    "进入聊天": "/chat",
    "打开聊天": "/chat",
    "开始聊天": "/chat",
    "回首页": "/chat",
    "回到主界面": "/chat",
    "显示首页": "/chat",
    "首页": "/chat",
    "主界面": "/chat",
    "打开首页": "/chat",
    "返回首页": "/chat",
    "返回主界面": "/chat",
    "回到聊天": "/chat",
    "打开项目管理": "/projects",
    "项目管理": "/projects",
    "项目": "/projects",
    "我的项目": "/projects",
    "查看项目": "/projects",
    "项目列表": "/projects",
    "待办事项": "/todos",
    "待办": "/todos",
    "待办列表": "/todos",
    "我的待办": "/todos",
    "查看待办": "/todos",
    "进入学习中心": "/learning",
    "学习中心": "/learning",
    "学习": "/learning",
    "去学习": "/learning",
    "进入设置": "/settings",
    "打开设置": "/settings",
    "设置": "/settings",
    "管理订阅": "/subscription",
    "订阅": "/subscription",
    "我的订阅": "/subscription",
    "登录": "/login",
    "新建对话": "/chat?new=true",
    "新对话": "/chat?new=true",
    "关闭主界面": "__HIDE_WINDOW__",
    "关闭窗口": "__HIDE_WINDOW__",
    "隐藏界面": "__HIDE_WINDOW__",
    "最小化到托盘": "__HIDE_WINDOW__",
    "显示手机桌面": "/learning?tab=android",
    "手机桌面": "/learning?tab=android",
    "手机屏幕": "/learning?tab=android",
    "手机镜像": "/learning?tab=android",
    "技能录制": "/learning?tab=macros",
    "开始技能录制": "/learning?tab=macros",
    "结束技能录制": "/learning?tab=macros",
    "手机录屏": "/learning?tab=android",
}

ROUTE_ALIASES: dict[str, tuple[str, str]] = {
    "录屏": ("macro", "录屏"),
    "录制屏幕": ("macro", "录屏"),
    "开始录屏": ("macro", "录屏"),
    "录音": ("macro", "开始录音"),
    "录制声音": ("macro", "开始录音"),
    "开始录音": ("macro", "开始录音"),
}

CONTEXT_MAP: dict[str, dict[str, str]] = {
    "录制": {
        "QuickTime Player": "开始录屏",
        "录音": "开始录音",
        "Voice Memos": "开始录音",
        "__phone__": "手机录屏",
        "__default__": None,
    },
    "播放": {
        "Music": "播放音乐",
        "Spotify": "播放音乐",
        "IINA": "播放暂停",
        "QuickTime Player": "播放暂停",
        "__default__": None,
    },
    "下一曲": {
        "Music": "下一曲",
        "Spotify": "下一曲",
        "IINA": "下一曲",
        "__default__": None,
    },
}


async def resolve_context() -> dict[str, Any]:
    """获取当前环境上下文：活跃应用、手机连接等。"""
    from app.infrastructure.drivers.macos import macos_driver

    app_info = await asyncio.to_thread(macos_driver.get_current_app)
    active_app = app_info.get("name", "") if app_info else ""

    from app.core.environment.state import get_awakened_state
    state = get_awakened_state()
    phone_connected = any(d.is_reachable for d in (state.android_devices or []))

    return {"app": active_app, "phone_connected": phone_connected}


def extract_slots(intent_name: str, text: str) -> dict:
    """Simple slot extraction from raw text."""
    prefixes = ["打开", "启动", "关闭", "退出", "切换到", "去", "搜索", "搜一下"]
    for p in prefixes:
        if text.startswith(p):
            return {"_value": text[len(p):].strip(), "_text": text}
    return {}


async def resolve_intent(
    intent_name: str, text: str, thread_id: str, project_id: int
) -> tuple[str, dict] | None:
    """Resolve BERT intent_name to an L0 action. Returns (action, args) or None."""
    import re

    # 上下文感知路由：根据活跃应用/手机连接重定向 intent
    if intent_name in CONTEXT_MAP:
        ctx = await resolve_context()
        mapping = CONTEXT_MAP[intent_name]
        target = mapping.get("__default__")
        for app_key, target_intent in mapping.items():
            if app_key == "__default__" or app_key == "__phone__":
                continue
            if app_key.lower() in ctx["app"].lower():
                target = target_intent
                break
        if ctx.get("phone_connected") and "__phone__" in mapping:
            target = mapping["__phone__"]
        if target:
            intent_name = target

    # Intent-specific guards to reject false positives
    if intent_name == "报时" and not re.search(r"几[号点时]|星期|时间|日期|报时", text):
        return None
    if intent_name in ("打开应用", "切换到应用", "退出应用") and not re.search(
        r"(打开|启动|开一下|切换到|去|退出|关闭|关掉)\w", text
    ):
        return None

    # Device name redirect
    _device_intents = {
        "WiFi": ["打开_WiFi", "关闭_WiFi", "打开 WiFi", "关闭 WiFi"],
        "蓝牙": ["打开蓝牙", "关闭蓝牙"],
        "蓝牙设备": ["连接蓝牙设备", "断开蓝牙设备"],
    }
    for keyword, targets in _device_intents.items():
        if keyword in text and intent_name in (
            "打开应用", "打开_WiFi", "打开信息",
            "退出应用", "关闭_WiFi",
            "切换到应用",
        ):
            candidates = targets
            break
    else:
        candidates = [intent_name, intent_name.replace("_", " ")]

    async with session_scope() as session:
        for name in candidates:
            stmt = select(Macro).where(Macro.name == name, Macro.status == "verified")
            result = await session.execute(stmt)
            macro = result.scalar_one_or_none()
            if macro:
                args = extract_slots(intent_name, text)
                # 映射 _value 到宏的参数名
                if "_value" in args and macro.parameters:
                    import json
                    try:
                        params_list = json.loads(macro.parameters) if isinstance(macro.parameters, str) else macro.parameters
                        if isinstance(params_list, list) and params_list:
                            param_name = params_list[0].get("name")
                            if param_name:
                                args[param_name] = args.pop("_value")
                    except (json.JSONDecodeError, TypeError, IndexError):
                        pass
                return f"macro:{macro.id}", args

    # Try builtin from init_spec templates
    for tmpl in _TEMPLATES:
        if intent_name == tmpl["action"]:
            return tmpl["action"], {"name": text} if tmpl["action"] == "rename" else {}
    _BUILTIN_ALIASES = {"取消": "cancel", "结束": "end", "重说": "clarify", "改名": "rename"}
    if intent_name in _BUILTIN_ALIASES:
        action = _BUILTIN_ALIASES[intent_name]
        return action, {"name": text} if action == "rename" else {}

    return None


async def process_single(
    text: str,
    thread_id: str,
    project_id: int,
    worker_registry: Any = None,
) -> bool:
    """Run L0 on a single sub-command. Returns True if handled locally, False if it needs Agent."""
    from app.core.execution.macro.runner import load_macro  # noqa: TID252

    # 直接路由匹配
    route = DIRECT_ROUTES.get(text)
    if route:
        await handle_navigate(route, thread_id)
        return True

    # 别名匹配
    alias = ROUTE_ALIASES.get(text)
    if alias:
        kind, target = alias
        async with session_scope() as session:
            stmt = select(Macro).where(Macro.name == target, Macro.status == "verified")
            result = await session.execute(stmt)
            macro = result.scalar_one_or_none()
        if macro:
            await dispatch_macro(thread_id, macro.id, {}, project_id, worker_registry=worker_registry)
            return True

    # BERT 意图分类
    intent_name, margin = classifier_predict(text)
    l0_match = None
    if intent_name and margin >= 0.08:
        l0_match = await resolve_intent(intent_name, text, thread_id, project_id)
    # LocalMatcher 兜底
    if l0_match is None:
        matcher = await get_local_matcher()
        l0_match = matcher.match(text)
    if l0_match is not None:
        action, args = l0_match
        if action.startswith("macro:"):
            macro_id = int(action.split(":", 1)[1])
            macro = await load_macro(macro_id)
            if macro is not None:
                route = is_navigation_macro(macro)
                if route:
                    await handle_navigate(route, thread_id)
                    return True
            ok = await dispatch_macro(thread_id, macro_id, args, project_id, worker_registry=worker_registry)
            if ok:
                return True
            logger.info("[voice-router] macro failed, falling through to Agent for thread %s", thread_id)
        else:
            await handle_builtin(thread_id, action, args, worker_registry=worker_registry)
            return True
    return False
