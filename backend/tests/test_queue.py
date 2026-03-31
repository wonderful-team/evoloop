#!/usr/bin/env python3
"""队列功能测试 - 验证入队和消费是否正常工作."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "cbg_collector"))
from queue import create_queue, SQLiteQueue


def test_put_sync():
    """测试同步入队."""
    print("=" * 60)
    print("测试同步入队 (put_sync)")
    print("=" * 60)

    queue = create_queue()
    print(f"队列类型: {queue.__class__.__name__}")

    # 测试数据
    test_data = {
        "xml": "<test>test content</test>",
        "list_info": {
            "signature": "test|123",
            "price": "￥100",
            "features": ["test", "data"],
            "screen_num": 0,
        },
        "tap_coords": {"x": 540, "y": 800},
        "collected_at": "2026-03-18T10:00:00",
    }

    # 同步入队
    if isinstance(queue, SQLiteQueue):
        success = queue.put_sync(test_data)
        print(f"入队结果: {'✓ 成功' if success else '✗ 失败'}")

        # 检查队列大小
        size = queue.size_sync()
        print(f"队列大小: {size}")

        # 获取统计
        stats = queue.stats_sync()
        print(f"队列统计: {stats}")
    else:
        # 异步入队
        async def do_put():
            success = await queue.put(test_data)
            print(f"入队结果: {'✓ 成功' if success else '✗ 失败'}")
            size = await queue.size()
            print(f"队列大小: {size}")

        asyncio.run(do_put())

    queue.close() if hasattr(queue, 'close') else None
    print("\n" + "=" * 60)
    print("入队测试完成")
    print("=" * 60)


async def test_consume():
    """测试消费."""
    print("\n" + "=" * 60)
    print("测试消费 (get/ack)")
    print("=" * 60)

    queue = create_queue()
    print(f"队列类型: {queue.__class__.__name__}")

    # 检查队列大小
    size = await queue.size()
    print(f"队列大小: {size}")

    if size == 0:
        print("队列为空，无法消费")
        await queue.close()
        return

    # 消费一条
    message = await queue.get(timeout=1)
    if message:
        print(f"消费消息ID: {message.get('_queue_id', 'N/A')}")
        list_info = message.get("list_info", {})
        print(f"  价格: {list_info.get('price', 'N/A')}")
        print(f"  特征: {list_info.get('features', [])[:2]}")

        # 确认消息
        await queue.ack(message)
        print("✓ 消息已确认")

        # 再次检查队列大小
        size = await queue.size()
        print(f"队列剩余: {size}")
    else:
        print("未获取到消息")

    await queue.close()
    print("\n" + "=" * 60)
    print("消费测试完成")
    print("=" * 60)


if __name__ == "__main__":
    # 测试入队
    test_put_sync()

    # 测试消费
    asyncio.run(test_consume())
