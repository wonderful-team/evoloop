"""企业微信：扫描有未读消息的会话，找出可回复的联系人。

值守渠道内联调用 run()，返回 (replyable, non_replyable) 或 None（未就绪）。

设计：点击左侧"未读"分组，一次 AX dump 列出所有未读会话（快，不逐个点击）。
"""

import logging

from app.core.channel.duty.constants import SERVICE_ACCOUNTS

from .common import open_wecom, scan_unread_view

logger = logging.getLogger(__name__)


async def has_input_toolbar(pos, preview: str = "") -> bool:
    """判断联系人能否回复（个人联系人可回复，服务号/未验证不可）。

    基于联系人名 + 消息预览判断：
    - 预览含"还不是你的联系人/请发送申请验证"→ 未验证，不可回复
    - 服务号/系统通知（企业微信团队/服务商助手等）→ 不可回复
    - 其他个人联系人 → 可回复
    """
    x, y, name = pos
    del x, y
    if any(s in name for s in SERVICE_ACCOUNTS):
        return False
    if any(
        k in preview for k in ("还不是你的联系人", "请发送申请验证", "发送联系人申请")
    ):
        return False
    return True


async def run(history_dir: str) -> tuple[list[str], list[str]] | None:  # noqa: ARG001 — 保留入参兼容调用方（扫描不需历史目录）
    """扫描未读会话并分类可回复联系人。

    Returns:
        (replyable, non_replyable) 联系人名列表；企业微信未就绪或无可读未读返回 None。
    """
    # 激活企微到前台（扫描依赖前台 AX 坐标/点击生效，后台读树会拿到过期状态
    # 导致误判"无可读未读"）。open_wecom 内部已点击"未读"导航进入未读视图。
    await open_wecom()
    # 一次（或切换视图后两次）AX dump 扫描未读红点，避免反复 dump
    contacts = await scan_unread_view()

    if not contacts:
        logger.info("[wecom_scan_all] 企业微信未就绪或无可读未读会话")
        return None

    replyable = []
    non_replyable = []
    for item in contacts:
        x, y, name, unread_count, preview = item
        can = await has_input_toolbar((x, y, name), preview)
        flag = "REPLYABLE" if can else "NON_REPLYABLE"
        logger.info(
            "[wecom_scan_all] %s %s | 未读=%d | 预览=%s",
            flag,
            name,
            unread_count,
            preview,
        )
        (replyable if can else non_replyable).append((name, unread_count))
    return replyable, non_replyable
