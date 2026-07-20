#!/usr/bin/env python3
"""EvoLoop Mobile 真机端到端测试脚本（HarmonyOS + hdc uitest）."""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")
from scripts.mobile_ui import (
    back, center, find_by_text, find_nodes, find_one, load_nodes,
    parse_bounds, run, screenshot,
)


class MobileTester:
    def __init__(self):
        self.results = []

    def log(self, msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def record(self, case: str, passed: bool, detail: str = ""):
        self.results.append({"case": case, "passed": passed, "detail": detail})
        icon = "✅" if passed else "❌"
        self.log(f"{icon} {case}: {detail}")

    def find_send_button(self) -> dict | None:
        """根据绿色背景定位发送按钮."""
        nodes = load_nodes()
        for n in nodes:
            if n.get("type") == "Custom" and n.get("backgroundColor") == "#FF109C8F":
                x1, y1, x2, y2 = parse_bounds(n["bounds"])
                if x2 - x1 < 150 and y2 - y1 < 150:
                    return n
        return None

    def click_send(self) -> bool:
        btn = self.find_send_button()
        if not btn:
            self.log("Send button not found")
            return False
        x, y = center(parse_bounds(btn["bounds"]))
        run(f"uitest uiInput click {x} {y}")
        return True

    def is_in_chat_screen(self) -> bool:
        """检查当前是否处于聊天页面中."""
        nodes = load_nodes()
        for n in nodes:
            if n.get("type") == "TextArea" or n.get("text") == "按住说话" or n.get("hint") == "输入消息...":
                return True
        return False

    def ensure_text_mode(self) -> bool:
        """从语音输入模式（按住说话）自动切换回文本输入模式."""
        if find_one(type="TextArea"):
            return True
        self.log("TextArea not found, checking if we are in voice mode...")
        # 寻找右下角的键盘切换图标：bounds 坐标大概在 x1 > 900, y1 > 2400
        nodes = load_nodes()
        keyboard_btn = None
        for n in nodes:
            bounds = n.get("bounds")
            if bounds:
                m = re.findall(r"\d+", bounds)
                if m and len(m) == 4:
                    x1, y1, x2, y2 = map(int, m)
                    if y1 > 2400 and x1 > 900:
                        keyboard_btn = n
                        break
        if keyboard_btn:
            self.log("Found keyboard toggle button, clicking it...")
            x, y = center(parse_bounds(keyboard_btn["bounds"]))
            run(f"uitest uiInput click {x} {y}")
            time.sleep(1.0)
            if find_one(type="TextArea"):
                self.log("Successfully switched to text input mode!")
                return True
        return False

    def go_back_to_session_list(self) -> bool:
        """安全返回会话列表，处理键盘弹起和语音模式的问题."""
        self.log("Navigating back to session list...")
        for i in range(3):
            if not self.is_in_chat_screen():
                return True
            self.log(f"Still in chat screen, sending Back (attempt {i+1})...")
            back()
            time.sleep(1.5)
        return not self.is_in_chat_screen()

    def input_text(self, text: str) -> bool:
        if not self.ensure_text_mode():
            self.log("Failed to switch to text input mode")
            return False
        ta = find_one(type="TextArea")
        if not ta:
            self.log("TextArea still not found")
            return False
        x, y = center(parse_bounds(ta["bounds"]))
        run(f"uitest uiInput click {x} {y}")
        time.sleep(0.3)
        # 使用 text 命令输入；转义单引号
        safe = text.replace("'", "'\\''")
        run(f"uitest uiInput text '{safe}'")
        return True

    def wait_for_message(self, text: str, timeout: int = 30, poll: int = 2) -> bool:
        """等待聊天列表中出现指定文本."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            node = find_by_text(text)
            if node:
                return True
            time.sleep(poll)
        return False

    def test_long_text(self):
        """2.2 长文本消息."""
        case = "2.2 长文本消息"
        long_md = (
            "# 长文本测试\\n"
            "这是一条用于测试长文本传输的消息。\\n"
            "- 项目：EvoLoop\\n"
            "- 目标：验证 Gateway -> Desktop Agent -> Mobile 的长文本链路\\n"
            "- 期望：消息不截断、不 413、Mobile 端渲染正常\\n"
            "\\n"
            "```python\\n"
            "print('hello evoloop')\\n"
            "```\\n"
            "\\n"
            + "末尾填充字符。" * 20
        )
        if not self.input_text(long_md):
            self.record(case, False, "输入框未找到")
            return
        time.sleep(0.5)
        if not self.click_send():
            self.record(case, False, "发送按钮未找到")
            return
        # 等待 Mobile 本地出现该消息
        if self.wait_for_message("长文本测试", timeout=10):
            self.record(case, True, "长文本消息已出现在 Mobile 本地")
        else:
            self.record(case, False, "未在 Mobile 本地看到发送的长文本")

    def test_session_switch(self):
        """1.5 会话切换."""
        case = "1.5 会话切换"
        # 返回会话列表
        if not self.go_back_to_session_list():
            self.record(case, False, "无法返回会话列表（仍然停留在聊天页）")
            return
        time.sleep(1.5)
        # 截图查看
        screenshot("/tmp/mobile_session_list.png")
        # 尝试查找会话列表项（ListItem）
        nodes = load_nodes()
        list_items = [n for n in nodes if n.get("type") == "ListItem"]
        if len(list_items) < 2:
            self.record(case, False, f"会话列表项数量不足：{len(list_items)}")
            return
        # 点击第二个会话项
        item = list_items[1]
        x, y = center(parse_bounds(item["bounds"]))
        run(f"uitest uiInput click {x} {y}")
        time.sleep(1.5)
        # 确认进入聊天页
        if self.is_in_chat_screen():
            self.record(case, True, "成功切换到另一个会话")
        else:
            self.record(case, False, "切换后未进入聊天页")

    def test_copy_message(self):
        """2.5 复制消息."""
        case = "2.5 复制消息"
        # 查找一条 AI 或 human 文本消息
        nodes = load_nodes()
        text_nodes = [n for n in nodes if n.get("type") == "Text" and n.get("text")]
        target = None
        for n in text_nodes:
            text = n.get("text", "")
            if len(text) > 5 and "测试" in text:
                target = n
                break
        if not target:
            self.record(case, False, "未找到可复制的测试消息")
            return
        x, y = center(parse_bounds(target["bounds"]))
        # 长按
        run(f"uitest uiInput longClick {x} {y}")
        time.sleep(1)
        # 查找复制/Copy 选项
        if find_by_text("复制") or find_by_text("Copy"):
            self.record(case, True, "长按消息后出现复制选项")
            # 点空白处取消
            run("uitest uiInput click 600 1500")
        else:
            self.record(case, False, "长按后未出现复制选项")

    def test_add_to_memory(self):
        """2.6 加入记忆."""
        case = "2.6 加入记忆"
        # 查找消息并长按
        nodes = load_nodes()
        text_nodes = [n for n in nodes if n.get("type") == "Text" and n.get("text")]
        target = None
        for n in text_nodes:
            if len(n.get("text", "")) > 5:
                target = n
                break
        if not target:
            self.record(case, False, "未找到可加入记忆的消息")
            return
        x, y = center(parse_bounds(target["bounds"]))
        run(f"uitest uiInput longClick {x} {y}")
        time.sleep(1)
        if find_by_text("加入记忆") or find_by_text("记忆"):
            self.record(case, True, "长按消息后出现加入记忆选项")
            run("uitest uiInput click 600 1500")
        else:
            self.record(case, False, "长按后未出现加入记忆选项")

    def test_mobile_offline_recovery(self):
        """3.1 Mobile 离线后上线."""
        case = "3.1 Mobile 离线后上线"
        # 通过在 host 端杀掉 Nginx 模拟网络彻底中断（手机无法连上 80 端口的 Gateway/Backend）
        self.log("Simulating offline: killing Nginx on host...")
        subprocess.run("pkill -9 -f 'nginx-local.conf'", shell=True)
        time.sleep(2)
        
        # 在手机端发送消息（此时属于断网状态）
        msg = "离线补偿测试消息"
        if self.input_text(msg):
            self.click_send()
            self.log(f"Offline message sent on mobile UI: {msg}")
        
        # 恢复网络：重新启动 Nginx
        self.log("Simulating online: restarting Nginx on host...")
        subprocess.run("nginx -c /Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/deploy/nginx/nginx-local.conf", shell=True)
        time.sleep(8) # 等待手机端重连同步
        
        # 检查消息是否出现（应该通过重连上报）
        if self.wait_for_message(msg, timeout=20):
            self.record(case, True, "离线后发送的消息在恢复网络后到达")
        else:
            self.record(case, False, "离线补偿消息未到达")

    def test_php_queue_stop(self):
        """3.4 PHP queue 停止后恢复."""
        case = "3.4 PHP queue 停止后恢复"
        # 停止 PHP worker
        subprocess.run("pkill -f 'queue:work redis --queue gateway:mc:message_sync'", shell=True)
        time.sleep(1)
        msg = "PHP队列恢复测试消息"
        if not self.input_text(msg):
            self.record(case, False, "输入框未找到")
            return
        self.click_send()
        time.sleep(3)
        # 检查 Redis 是否有积压
        redis_out = subprocess.run(
            "redis-cli LLEN {queues:gateway:mc:message_sync}",
            shell=True, capture_output=True, text=True
        ).stdout.strip()
        pending = int(redis_out) if redis_out.isdigit() else 0
        # 重新启动 PHP worker
        subprocess.run(
            "cd /Users/huangjinhuan/Projects/develop-assistant.cn/member-center/backend && "
            "nohup php think queue:work redis --queue gateway:mc:message_sync --sleep 3 --tries 3 > /tmp/php_mc_worker.log 2>&1 &",
            shell=True
        )
        time.sleep(8)
        # 验证 MC 中是否有该消息
        mc_out = subprocess.run(
            f"docker exec -i evoloop-mysql mysql -uroot -padmin888 b2c_mall -e \"SELECT COUNT(*) FROM evoloop_messages WHERE content LIKE '%{msg}%';\"",
            shell=True, capture_output=True, text=True
        ).stdout
        count = 0
        for line in mc_out.splitlines():
            if line.strip().isdigit():
                count = int(line.strip())
        if count > 0:
            self.record(case, True, f"PHP worker 恢复后消息入库成功（积压前 {pending} 条）")
        else:
            self.record(case, False, f"PHP worker 恢复后消息未入库（积压前 {pending} 条）")

    def test_network_jitter(self):
        """3.5 网络抖动."""
        case = "3.5 网络抖动"
        # 通过快速杀死/重启 Nginx 两次模拟网络高频抖动
        self.log("Simulating network jitter on host...")
        for _ in range(2):
            subprocess.run("pkill -9 -f 'nginx-local.conf'", shell=True)
            time.sleep(1.5)
            subprocess.run("nginx -c /Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/deploy/nginx/nginx-local.conf", shell=True)
            time.sleep(2.0)
        time.sleep(3.0) # 等待重新稳定
        # 发送消息验证
        msg = "网络抖动测试消息"
        if self.input_text(msg):
            self.click_send()
        if self.wait_for_message(msg, timeout=20):
            self.record(case, True, "网络抖动后消息仍能正常收发")
        else:
            self.record(case, False, "网络抖动后消息未到达")

    def run_all(self):
        self.test_long_text()
        self.test_session_switch()
        # 确保回到聊天页再继续
        self.ensure_text_mode()
        self.test_copy_message()
        self.test_add_to_memory()
        self.test_mobile_offline_recovery()
        self.test_php_queue_stop()
        self.test_network_jitter()

        print("\n" + "=" * 60)
        print("真机测试结果汇总")
        print("=" * 60)
        passed = sum(1 for r in self.results if r["passed"])
        for r in self.results:
            icon = "✅" if r["passed"] else "❌"
            print(f"{icon} {r['case']}: {r['detail']}")
        print(f"\n通过 {passed}/{len(self.results)}")


if __name__ == "__main__":
    tester = MobileTester()
    tester.run_all()
