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


# 运营线（业务巡检）检查间隔（分钟）。该频率只决定“扫描任务列表”的节奏，
# 真正的任务执行时间由 prompts 各自的 next_run_at/interval_minutes 控制。
BUSINESS_POLL_INTERVAL = 1  # 分钟
BUSINESS_POLL_INTERVAL_MIN = 1  # 分钟
BUSINESS_POLL_INTERVAL_MAX = 1440  # 分钟（24h）


def clamp_business_poll_interval(interval: object) -> int:
    """钳制运营线巡检间隔到 [5, 1440]（分钟）；非法/缺省回退 60。

    非整数（None/str/bool/float 等）一律回退缺省——配置只接受整数分钟。
    """
    if not isinstance(interval, int) or isinstance(interval, bool):
        return BUSINESS_POLL_INTERVAL
    return max(
        BUSINESS_POLL_INTERVAL_MIN, min(interval, BUSINESS_POLL_INTERVAL_MAX)
    )


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

    Returns:
        {
            "enabled": bool,
            "channels": dict,        # 该项目企微参数（corp_id/agent_id/secret）
            "interval": int,         # 轮巡间隔（秒，钳制 60~3600，缺省 DUTY_INTERVAL）
            "business_poll_interval": int,  # 业务巡检扫描间隔（分钟，钳制 1~1440）
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
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "channels": cfg.get("channels") or {},
        "interval": clamp_duty_interval(cfg.get("interval")),
        "business_poll_interval": clamp_business_poll_interval(
            cfg.get("business_poll_interval")
        ),
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
