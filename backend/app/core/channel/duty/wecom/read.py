"""企业微信：读取指定联系人的新增客户消息（AX + md 增量）。

值守渠道内联调用 run() 获取新增客户消息。
"""

from .common import read_customer_messages


async def run(history_dir: str, contact: str, unread_count: int = 0) -> list[str]:
    """读取并返回「新增的客户消息」列表。"""
    return await read_customer_messages(contact, history_dir, unread_count)
