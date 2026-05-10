import asyncio
import sys
import os
import logging
import unittest
from unittest.mock import MagicMock

# 设置环境
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class TestEvoCloudManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.evocloud.manager import EvoCloudManager
        from app.core.evocloud.schemas import EvoCloudConfig
        self.manager = EvoCloudManager()
        self.config = EvoCloudConfig(
            api_url="http://localhost",
            ws_url="ws://localhost",
            app_data_dir="/tmp/evoloop_test"
        )
        # 屏蔽日志干扰
        logging.getLogger("app.core.evocloud").setLevel(logging.ERROR)

    async def test_lazy_initialization(self):
        """测试隐式懒加载：第一次访问属性时自动初始化"""
        print("\n[Test] Testing lazy initialization...")
        # 确保还没初始化
        self.assertFalse(self.manager._initialized)
        
        # 访问属性
        api = self.manager.api
        self.assertIsNotNone(api)
        # 验证已自动初始化
        self.assertTrue(self.manager._initialized)
        self.assertIsNotNone(self.manager.config)

    async def test_loop_isolation(self):
        """测试 Loop 隔离：不同 loop 应该拿到不同的 API 实例"""
        print("[Test] Testing loop isolation...")
        
        async def get_ids():
            return id(self.manager.api), id(self.manager.link)

        # 当前 Loop 的实例
        id1_api, id1_link = await get_ids()

        # 在另一个新 Loop 中运行
        new_loop = asyncio.new_event_loop()
        try:
            def run_new():
                asyncio.set_event_loop(new_loop)
                return new_loop.run_until_complete(get_ids())
            
            import threading
            class ThreadWithResult(threading.Thread):
                def __init__(self, target):
                    super().__init__()
                    self.target = target
                    self.result = None
                def run(self):
                    self.result = self.target()
            
            t = ThreadWithResult(run_new)
            t.start()
            t.join()
            id2_api, id2_link = t.result
        finally:
            new_loop.close()

        print(f"Loop 1 API: {id1_api}, Loop 2 API: {id2_api}")
        print(f"Loop 1 Link: {id1_link}, Loop 2 Link: {id2_link}")
        
        self.assertNotEqual(id1_api, id2_api, "API clients should be different across loops")
        self.assertNotEqual(id1_link, id2_link, "Links should be different across loops")

    async def test_sync_manager_consistency(self):
        """测试同步管理器的一致性"""
        print("[Test] Testing sync manager consistency...")
        self.manager.initialize(self.config)
        await self.manager._start_conversation_sync()
        
        sync_m = self.manager.sync_manager
        self.assertIsNotNone(sync_m)
        
        import app.core.evocloud.bridge.conversation_sync as bridge
        self.assertIs(sync_m, bridge._conversation_sync_manager, "Sync manager must be identical to bridge global")

    async def test_stop_cleanup(self):
        """测试资源清理"""
        print("[Test] Testing stop and cleanup...")
        self.manager.initialize(self.config)
        api = self.manager.api
        link = self.manager.link
        
        # 模拟运行状态
        link._running = True
        
        await self.manager.stop()
        
        # 验证 Pool 已被清空 (flush_all)
        self.assertEqual(len(self.manager._api_pool._resources), 0)
        self.assertEqual(len(self.manager._link_pool._resources), 0)

if __name__ == "__main__":
    unittest.main()
