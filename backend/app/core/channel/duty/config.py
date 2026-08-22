"""值守配置读取 — 按项目加载值守配置（复用 project 工具，不新增读取层）。

从项目 .evoloop/project.json 读 customer_service_duty，按 local_path 推断
历史目录。供 scheduler / channel / provision 复用。

全局值守配置（总开关 + 渠道选择）存 SystemConfigService，
key = CUSTOMER_SERVICE_DUTY，值为 JSON 字符串。
MCP server 连接在系统启动时完成（APP_STARTED → connect_all），不在值守配置里。
"""

from __future__ import annotations

import json
import logging
import os

from app.core.project.utils import get_project_path, read_project_json
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)

GLOBAL_DUTY_CONFIG_KEY = "CUSTOMER_SERVICE_DUTY"

# 值守轮巡缺省间隔（秒）。对齐全局扫描粒度（engine_scheduler_tick_periodic
# 每 60s 一次，Huey crontab 仅分钟粒度）：DUTY 间隔语义 = 分钟级，
# 钳制 60~3600s（§8.5.2 v6.3），更小的间隔会被扫描粒度量化、无法兑现。
DUTY_INTERVAL = 60

# 钳制上下限（秒）：1 分钟 ~ 1 小时（v6.3，§8.5.2）
DUTY_INTERVAL_MIN = 60
DUTY_INTERVAL_MAX = 3600


def clamp_duty_interval(interval: object) -> int:
    """钳制轮巡间隔到 [60, 3600]（秒）；非法/缺省回退 DUTY_INTERVAL=60。

    非整数（None/str/bool/float 等）一律回退缺省——配置只接受整数秒。
    """
    if not isinstance(interval, int) or isinstance(interval, bool):
        return DUTY_INTERVAL
    return max(DUTY_INTERVAL_MIN, min(interval, DUTY_INTERVAL_MAX))


# 运营线（业务巡检）扫描频率（分钟）。固定系统常量，对齐 60s tick 粒度：
# 它只决定“扫描任务列表”的节奏，真正的执行时间由 prompts 各自的
# next_run_at/interval_minutes 控制，不随项目/全局配置。
BUSINESS_POLL_INTERVAL = 1  # 分钟


def load_global_duty_config() -> dict:
    """读全局值守配置（总开关 + 渠道选择）。"""
    raw = SystemConfigService.get_value(GLOBAL_DUTY_CONFIG_KEY)
    if not raw:
        return {"enabled": False, "channels": []}
    try:
        cfg = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("[duty_config] 全局值守配置解析失败: %r", raw[:60])
        return {"enabled": False, "channels": []}
    return cfg


def save_global_duty_config(cfg: dict) -> None:
    """写全局值守配置。"""
    SystemConfigService.set_value(
        GLOBAL_DUTY_CONFIG_KEY,
        json.dumps(cfg, ensure_ascii=False),
        description="客服值守全局配置（总开关 + 渠道选择）",
    )


async def load_duty_config(project_id: int) -> dict:
    """按项目加载值守配置。

    轮巡节奏是全局机制（60s tick 粒度 + 推送接管），故轮巡间隔取自全局
    配置（poll_interval）；业务巡检扫描频率固定为系统常量，不随项目配置。

    Returns:
        {
            "enabled": bool,
            "channels": dict,            # 各渠道参数（wecom / callback MCP 配置）
            "active_channels": list[str],  # 启用的渠道名（wecom/callback，缺省 enabled=true）
            "poll_interval": int,        # 兜底轮巡间隔（秒，来自全局，钳制 60~3600）
            "business_poll_prompts": list,  # 业务巡检任务列表（每条独立会话）
            "history_dir": str,      # <local_path>/.evoloop/wecom_history
            "project_path": str,
        }
    """
    path = await get_project_path(project_id)
    if not path:
        logger.warning("[duty_config] project_id=%s 无本地路径", project_id)
        return {}

    pj = read_project_json(path)
    cfg = pj.get("customer_service_duty") or {}
    history_dir = os.path.join(path, ".evoloop", "wecom_history")
    channels = cfg.get("channels") or {}
    # 启用的渠道列表。兼容两种格式：
    # - 新格式 dict：{"wecom": {...}, "callback": {...}}，enabled（缺省 true）决定是否启用
    # - 旧格式 list：["wecom"]（早期项目配置），全部视为启用
    if isinstance(channels, dict):
        active_channels = [
            name
            for name, c in channels.items()
            if isinstance(c, dict) and c.get("enabled", True)
        ]
    else:
        active_channels = [c for c in channels if isinstance(c, str)]
    # 轮巡间隔（兜底）从全局读取；缺省 DUTY_INTERVAL
    poll_interval = clamp_duty_interval(load_global_duty_config().get("poll_interval"))
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "channels": channels,
        "active_channels": active_channels,
        "poll_interval": poll_interval,
        "business_poll_prompts": cfg.get("business_poll_prompts") or [],
        "history_dir": history_dir,
        "project_path": path,
    }


async def save_business_poll_prompts(project_id: int, prompts: list[dict]) -> None:
    """写业务巡检任务列表（含更新后的 next_run_at）到项目 project.json。"""
    from app.core.project.utils import (
        get_project_path,
        read_project_json,
        write_project_json,
    )

    path = await get_project_path(project_id)
    if not path:
        return
    pj = read_project_json(path)
    duty = pj.get("customer_service_duty") or {}
    duty["business_poll_prompts"] = prompts
    write_project_json(path, {"customer_service_duty": duty})
