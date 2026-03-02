
import asyncio
import os
import sys
import time
import logging
import random
import unicodedata

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.tools.environment.mobile import mobile_control
from app.infrastructure.drivers.adb import adb_driver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MarathonV5")

class MarathonRunner:
    def __init__(self, device_id=None, total_steps=100):
        self.device_id = device_id
        self.total_steps = total_steps
        self.current_step = 0
        self.apps_visited = set()
        self.start_time = 0

    def normalize(self, t):
        if not t: return ""
        return unicodedata.normalize('NFC', str(t)).lower().strip().replace(" ", "").replace("\u3000", "")

    async def run(self):
        self.start_time = time.time()
        logger.info(f"🚀 STARTING MARATHON V5: {self.total_steps} Steps on {self.device_id}")
        
        # 1. Get 3rd party apps
        apps = await mobile_control.coroutine(action="list_apps", device_id=self.device_id)
        # Parse apps string list to Python list
        import ast
        try:
            app_list = ast.literal_eval(apps)
        except:
            app_list = ["com.android.settings", "com.baidu.netdisk", "com.tencent.mm", "com.pinduoduo.utils"] # fallback
        
        while self.current_step < self.total_steps:
            # Pick a random app from some known interesting ones or just from the list
            target_app = random.choice(app_list)
            logger.info(f"\n📦 [App {len(self.apps_visited)+1}] Opening: {target_app}")
            self.apps_visited.add(target_app)
            
            await mobile_control.coroutine(action="open_app", text=target_app, device_id=self.device_id)
            await asyncio.sleep(4)
            self.current_step += 1
            
            # Interaction sub-loop (5-10 steps per app)
            sub_steps = random.randint(5, 10)
            for _ in range(sub_steps):
                if self.current_step >= self.total_steps: break
                
                # Reactor-powered interaction
                # We'll use dump_ui to see what's there and pick something to 'Reactor' click
                # or just random swipe/tap
                chance = random.random()
                if chance < 0.6: # 60% chance to try Reactor Click
                    logger.info(f"👉 Step {self.current_step}: Attempting Reactor Sense...")
                    res = await mobile_control.coroutine(action="screenshot", ocr=True, device_id=self.device_id)
                    # Simple heuristic: find a word and click it
                    lines = res.split("\n")
                    targets = []
                    for line in lines:
                        if "at (" in line and len(line.split('"')[1]) > 1:
                            targets.append(line.split('"')[1])
                    
                    if targets:
                        target = random.choice(targets[:5])
                        logger.info(f"✨ Reactor Target: '{target}'")
                        await mobile_control.coroutine(action="click", element_name=target, device_id=self.device_id)
                    else:
                        await mobile_control.coroutine(action="swipe", x=500, y=1500, x2=500, y2=800, device_id=self.device_id)
                else:
                    logger.info(f"👉 Step {self.current_step}: Scrolling...")
                    await mobile_control.coroutine(action="swipe", x=500, y=1600, x2=500, y2=600, device_id=self.device_id)
                
                self.current_step += 1
                await asyncio.sleep(1)

        duration = time.time() - self.start_time
        logger.info("\n" + "="*60)
        logger.info(f"🏆 MARATHON COMPLETE V5")
        logger.info(f"Total Steps: {self.current_step}")
        logger.info(f"Apps Visited: {len(self.apps_visited)}")
        logger.info(f"Total Duration: {duration:.1f}s")
        logger.info(f"Avg Latency: {duration/self.current_step:.2f}s")
        logger.info("="*60)

async def main():
    devices = adb_driver.list_devices()
    if not devices:
        print("No devices found")
        return
    dev = devices[0]["serial"]
    runner = MarathonRunner(device_id=dev, total_steps=100)
    await runner.run()

if __name__ == "__main__":
    asyncio.run(main())
