#!/usr/bin/env python3
"""
幂等注册"预设（preset）"宏到 macros 表（恢复 docs 中 seed_preset_macros.py 的设计）。

当前内置：
  - 淘宝自动登录：DOM 宏，账号密码从密码箱自动注入（parameters=username/password）
  - 好单库自动登录：DOM 宏，账号密码从密码箱自动注入

幂等：按 (name, project_id) 查重，已存在则跳过。
写入即 verified + is_active，免审核（内置宏），并发布 mutation 事件重建 L0 路由索引。

用法:
  uv run python scripts/seed_preset_macros.py
"""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select

from app.core.events.publishers import publish_macro_mutated
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models.macro import Macro

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ID = 120  # 商城项目；宏的 vault 自动补参按此项目匹配密码箱凭据

_PRESET_MACROS: list[dict] = [
    {
        "name": "淘宝自动登录",
        "description": "打开淘宝登录页并填入账号密码登录（账号密码自动取自密码箱）",
        "trigger_patterns": ["淘宝自动登录", "登录淘宝", "淘宝登录", "登录淘宝账号"],
        "parameters": [
            {"name": "username", "required": True, "description": "淘宝登录账号"},
            {"name": "password", "required": True, "description": "淘宝登录密码"},
        ],
        "risk_tier": "ui",
        "macro_script": """version: '1.0'
metadata:
  format: evoloop-macro
  step_count: 5
steps:
- step_number: 1
  type: action
  source: dom
  event_type: navigate
  description: 打开淘宝登录页
  payload:
    url: 'https://login.taobao.com/member/login.jhtml?redirectURL=https%3A%2F%2Fwww.taobao.com%2F'
    wait_until: domcontentloaded
    timeout_ms: 30000
- step_number: 2
  type: action
  source: dom
  event_type: wait
  payload:
    seconds: 4
    timeout_ms: 10000
- step_number: 3
  type: action
  source: dom
  event_type: run_js
  description: 填入账号密码并勾选协议
  payload:
    script: "() => { const set=(n,v)=>{ if(!v||String(v).indexOf('{{')===0) return; const el=document.querySelector(n); if(el){ const st=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set; st.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true})); } }; set('#fm-login-id','{{username}}'); set('#fm-login-password','{{password}}'); const ag=document.querySelector('.fm-agreement .fm-agreement-text, .fm-agreement label, .fm-agreement'); if(ag) ag.click(); return true; }"
    timeout_ms: 10000
- step_number: 4
  type: action
  source: dom
  event_type: run_js
  description: 点击登录按钮
  payload:
    script: "() => { const b=document.querySelector('#login-form button[type=submit], .password-login button[type=submit]'); if(b){ b.click(); return true; } return false; }"
    timeout_ms: 10000
- step_number: 5
  type: action
  source: dom
  event_type: wait
  description: 等待跳转
  payload:
    seconds: 10
    timeout_ms: 20000
""",
    },
    {
        "name": "好单库自动登录",
        "description": "打开好单库并完成登录（手机号/密码），账号密码自动取自密码箱",
        "trigger_patterns": ["好单库自动登录", "登录好单库", "好单库登录", "登录好单库账号"],
        "parameters": [
            {"name": "username", "required": True, "description": "好单库登录手机号"},
            {"name": "password", "required": True, "description": "好单库登录密码"},
        ],
        "risk_tier": "ui",
        "macro_script": """version: '1.0'
metadata:
  format: evoloop-macro
  step_count: 8
steps:
- step_number: 1
  type: action
  source: dom
  event_type: navigate
  description: 打开好单库首页
  payload:
    url: 'https://www.haodanku.com/'
    wait_until: domcontentloaded
    timeout_ms: 30000
- step_number: 2
  type: action
  source: dom
  event_type: wait
  payload:
    seconds: 3
    timeout_ms: 10000
- step_number: 3
  type: action
  source: dom
  event_type: run_js
  description: 点击顶部登录入口打开登录弹窗
  payload:
    script: "() => { const a=[...document.querySelectorAll('.comhead-top-centre a, .comhead-top-user a')].find(x=>/登录/.test((x.textContent||'').trim())); if(a){ a.click(); return true; } return false; }"
    timeout_ms: 10000
- step_number: 4
  type: action
  source: dom
  event_type: wait
  payload:
    seconds: 2
    timeout_ms: 10000
- step_number: 5
  type: action
  source: dom
  event_type: run_js
  description: 切换到密码登录页签
  payload:
    script: "() => { const tabs=[...document.querySelectorAll('.c-login .c-tab li, .login-tab .c-tab li')]; const p=tabs.find(x=>/密码/.test(x.textContent||''))||tabs[1]; if(p){ p.click(); return true; } return false; }"
    timeout_ms: 10000
- step_number: 6
  type: action
  source: dom
  event_type: run_js
  description: 填入手机号与密码
  payload:
    script: "() => { const set=(n,v)=>{ if(!v||String(v).indexOf('{{')===0) return; const el=document.querySelector(n); if(el){ const st=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set; st.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); } }; set('input[placeholder=\\"手机号\\"]','{{username}}'); set('input[placeholder=\\"密码\\"]','{{password}}'); return true; }"
    timeout_ms: 10000
- step_number: 7
  type: action
  source: dom
  event_type: run_js
  description: 点击登录按钮
  payload:
    script: "() => { const b=document.querySelector('.c-login .btn-submit, .btn-submit'); if(b){ b.click(); return true; } return false; }"
    timeout_ms: 10000
- step_number: 8
  type: action
  source: dom
  event_type: wait
  description: 等待登录完成
  payload:
    seconds: 5
    timeout_ms: 15000
""",
    },
]


async def _seed_one(db, spec: dict) -> None:
    existing = (
        await db.execute(
            select(Macro).where(
                Macro.name == spec["name"],
                Macro.project_id == PROJECT_ID,
            )
        )
    ).scalars().first()
    if existing is not None:
        logger.info("[seed] 已存在，跳过: %s (id=%s)", spec["name"], existing.id)
        return

    macro = Macro(
        app_map_id=None,
        entity=None,
        name=spec["name"],
        description=spec["description"],
        trigger_patterns=spec["trigger_patterns"],
        parameters=spec["parameters"],
        macro_script=spec["macro_script"],
        namespace="preset",
        risk_tier=spec["risk_tier"],
        requires_confirmation=False,
        status="verified",
        is_active=True,
        project_id=PROJECT_ID,
        member_id=0,
        domain="ops",
    )
    db.add(macro)
    await db.flush()
    await db.commit()
    await db.refresh(macro)
    logger.info("[seed] 已写入: %s (id=%s, namespace=preset, verified, active)", spec["name"], macro.id)
    try:
        await publish_macro_mutated(macro.id, action="create")
    except Exception as e:
        logger.warning("[seed] 发布 mutation 事件失败（不影响已落库）: %s", e, exc_info=True)


async def main() -> None:
    await db_resource_manager.initialize()
    async with db_resource_manager.session_factory() as db:
        for spec in _PRESET_MACROS:
            await _seed_one(db, spec)
    logger.info("[seed] 完成。新增内置宏: %s", json.dumps([m["name"] for m in _PRESET_MACROS], ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
