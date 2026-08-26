
import asyncio
import os
import sys
import time
import logging
import random
import unicodedata

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.environment.tools.mobile import mobile_control
from app.infrastructure.drivers.adb import adb_driver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WeChatMainline")

class WeChatMainlineReactor:
    def __init__(self, device_id=None):
        self.device_id = device_id
        self.step_count = 0
        self.pkg = "com.tencent.mm"

    async def run_demo(self):
        logger.info(f"🚀 Launching Mainline WeChat Odyssey on {self.device_id}")
        
        # 1. Open WeChat
        await mobile_control.coroutine(action="open_app", text=self.pkg, device_id=self.device_id)
        await asyncio.sleep(4)
        self.step_count += 1
        
        # 2. Search & Send to File Transfer Assistant
        logger.info("\n--- TASK 1: File Transfer Assistant (Mainline Reactor) ---")
        # Go to Chat tab
        await mobile_control.coroutine(action="click", element_name="微信", device_id=self.device_id)
        # Search
        await mobile_control.coroutine(action="click", element_name="搜索", device_id=self.device_id)
        await mobile_control.coroutine(action="input_text", text="文件传输助手", device_id=self.device_id)
        await asyncio.sleep(2)
        await mobile_control.coroutine(action="click", element_name="文件传输助手", device_id=self.device_id)
        
        # Send
        msg = f"Mainline Reactor Test {random.randint(100,999)}"
        logger.info(f"👉 Sending: {msg}")
        await mobile_control.coroutine(action="input_text", text=msg, device_id=self.device_id)
        await mobile_control.coroutine(action="click", element_name="发送", device_id=self.device_id)
        self.step_count += 5 # Approx steps
        
        # 3. Mini Program Odyssey (Hybrid Detection Test)
        logger.info("\n--- TASK 2: Mini Program Odyssey (Hybrid Detection) ---")
        await mobile_control.coroutine(action="click", element_name="发现", device_id=self.device_id)
        await mobile_control.coroutine(action="click", element_name="小程序", device_id=self.device_id)
        await mobile_control.coroutine(action="click", element_name="搜索", device_id=self.device_id)
        await mobile_control.coroutine(action="input_text", text="京东", device_id=self.device_id)
        await asyncio.sleep(2)
        await mobile_control.coroutine(action="click", element_name="京东", device_id=self.device_id)
        
        logger.info("⏱ Waiting for Mini Program to load...")
        await asyncio.sleep(6)
        
        # Auto-Wander inside H5/Hybrid (15 steps)
        for i in range(15):
            if self.step_count >= 30: break
            logger.info(f"👉 Hybrid Step {i+1}: Random click via Mainline Reactor...")
            # Use 'intent_flow' mock or just sequential clicks
            # In H5, Reactor will automatically fallback to OCR due to Hybrid Probe
            res = await mobile_control.coroutine(action="screenshot", ocr=True, device_id=self.device_id)
            lines = res.split("\n")
            targets = [l.split('"')[1] for l in lines if 'at (' in l and len(l.split('"')[1]) >= 2]
            
            if targets:
                target = random.choice(targets[:3])
                await mobile_control.coroutine(action="click", element_name=target, device_id=self.device_id)
            else:
                await mobile_control.coroutine(action="swipe", x=500, y=1600, x2=500, y2=800, device_id=self.device_id)
            
            self.step_count += 1
            await asyncio.sleep(2)

        logger.info(f"\n✅ MAINLINE WECHAT ODYSSEY COMPLETE: {self.step_count} steps.")

async def main():
    devices = adb_driver.list_devices()
    if not devices:
        print("No devices found")
        return
    dev = devices[0]["serial"]
    reactor = WeChatMainlineReactor(device_id=dev)
    await reactor.run_demo()

if __name__ == "__main__":
    asyncio.run(main())
