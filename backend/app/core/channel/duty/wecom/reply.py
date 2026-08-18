"""企业微信：向指定联系人发送消息。

值守渠道内联调用 run() 发送回复，返回是否成功。
"""
import asyncio
import logging
import time

from app.infrastructure.drivers.macos import macos_driver

from .common import current_chat_and_find, open_wecom

logger = logging.getLogger(__name__)


async def run(contact: str, message: str) -> bool:
    """向指定联系人发送消息，返回是否成功。"""
    target = contact.split("@")[0].split("◎")[0].split("®")[0].strip()

    # 单次 AX dump 同时检测「当前会话」和「目标联系人位置」
    current, pos = await current_chat_and_find(contact)
    if current != target:
        # 不在目标会话：从会话列表定位并点击
        if not pos:
            await open_wecom()
            current, pos = await current_chat_and_find(contact)
        if not pos:
            logger.warning("[wecom_reply] 未找到联系人 %s", contact)
            return False
        cx, cy = pos
        await asyncio.to_thread(macos_driver.click, cx + 20, cy + 8)
        time.sleep(0.3)

    # 聚焦输入框：企业微信聊天界面按 Tab 键即可聚焦输入框（可靠）
    await asyncio.to_thread(macos_driver.key_press, "tab")
    time.sleep(0.1)
    # 清空输入框（避免残留）
    await asyncio.to_thread(macos_driver.key_press, "command+a")
    time.sleep(0.05)
    await asyncio.to_thread(macos_driver.key_press, "delete")
    time.sleep(0.05)

    # 输入（Tab 聚焦已确认可靠，直接输入并发送）
    await asyncio.to_thread(macos_driver.type_text, message)
    time.sleep(0.2)
    await asyncio.to_thread(macos_driver.key_press, "enter")
    time.sleep(0.2)

    logger.info("[wecom_reply] 已发送给 %s", contact)
    return True
