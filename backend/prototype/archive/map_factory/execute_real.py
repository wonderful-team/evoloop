"""真实执行腿(可见): 用真实浏览器驱动打开商城、登录、打开商品列表。

回答"有没有实质动作反馈": 有。这条腿用 Evoloop 真实 BrowserManager
(`app/infrastructure/drivers/browser.py`) 驱动**可见 Chrome**,真实 navigate + 登录 +
打开商品列表——你能在本机看到 Chrome 弹出并操作。`BrowserController.navigate`
(`controllers/browser/_navigation.py`) 用的正是这同一个 page/驱动。

绕过(不改 Evoloop 生产代码): browser_manager 的 Mode1->Mode2 回退有 bug——
except 只捕内建异常, 而 Playwright 连接失败抛 `playwright._impl._errors.Error`(不在其列),
导致无 CDP Chrome 时 get_page() 直接崩、Mode2 自启成死代码。故本脚本先自启 9222 Chrome,
再让 get_page() 走 Mode1 接管。

商城: http://127.0.0.1:9002/   登录: admin / admin888 (用户提供)
运行: uv run python -m prototype.map_factory.execute_real
安全: 只读导航 + 登录, 不改任何数据(不碰改价/写库)。
"""
from __future__ import annotations

import os

# 强制 IPv4 CDP 端点(规避 localhost->::1 与 Chrome IPv4 绑定的错配), 须在 import app 前设置
os.environ.setdefault("EVOLOOP_CHROME_CDP_URL", "http://127.0.0.1:9222")

import asyncio  # noqa: E402
import subprocess  # noqa: E402
import urllib.request  # noqa: E402

MALL = "http://127.0.0.1:9002"
LOGIN_URL = f"{MALL}/shop/login/login.html"
GOODS_LIST_URL = f"{MALL}/shop/goods/lists"
USERNAME = "admin"
PASSWORD = "admin888"
CDP = "http://127.0.0.1:9222"


def _cdp_up() -> bool:
    try:
        urllib.request.urlopen(f"{CDP}/json/version", timeout=1)
        return True
    except (OSError, ValueError):
        return False


async def _ensure_chrome() -> None:
    if _cdp_up():
        print("  [0] 9222 已有 Chrome(CDP), 直接接管")
        return
    from app.core.config import settings

    user_data = settings.CHROME_AUTOMATION_USER_DATA
    os.makedirs(user_data, exist_ok=True)
    cmd = [
        settings.CHROME_EXECUTABLE,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data}",
        "--disable-infobars",
        "--disable-extensions",
        "--no-first-run",
        "--disable-background-timer-throttling",
    ]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  [0] 自启可见 Chrome(9222, profile={user_data})...")
    for _ in range(40):
        await asyncio.sleep(0.5)
        if _cdp_up():
            print("  [0] Chrome 就绪(可见窗口应已弹出)")
            return
    raise RuntimeError("Chrome 未在 9222 就绪")


async def _body_snippet(page, n: int = 160) -> str:
    try:
        return (await page.inner_text("body"))[:n].replace("\n", " ")
    except (ValueError, OSError, RuntimeError) as e:
        return f"<读页面失败: {e}>"


async def run() -> int:
    from app.infrastructure.drivers.browser import browser_manager

    print("=== 真实执行腿: 打开商城 + 登录 + 商品列表(可见 Chrome) ===")
    await _ensure_chrome()
    page = await browser_manager.get_page()
    print(f"  [1] 已接管可见 Chrome, 当前页: {page.url!r}")

    print(f"  [2] navigate -> {LOGIN_URL}")
    await page.goto(LOGIN_URL, wait_until="load", timeout=60_000)
    await page.fill('input[name="username"]', USERNAME)
    await page.fill('input[name="password"]', PASSWORD)
    print("  [3] 已填 admin / admin888, 提交登录(回车, 失败再点按钮)")

    await page.press('input[name="password"]', "Enter")
    await page.wait_for_timeout(3500)
    if "login" in page.url:
        try:
            await page.locator(".layui-btn").first.click()
            await page.wait_for_timeout(3500)
        except (ValueError, OSError, RuntimeError) as e:
            print(f"      点登录按钮异常: {e}")

    after_login_url = page.url
    logged_in = "login" not in after_login_url
    print(f"  [4] 登录后 URL: {after_login_url}")
    print(f"      登录态: {'已登录' if logged_in else '仍停在登录页'}  页面片段: {await _body_snippet(page)!r}")

    print(f"  [5] navigate -> {GOODS_LIST_URL}")
    await page.goto(GOODS_LIST_URL, wait_until="load", timeout=60_000)
    await page.wait_for_timeout(2500)
    final_url = page.url
    title = await page.title()
    on_list = "login" not in final_url
    print(f"  [6] 商品列表 URL: {final_url}")
    print(f"      标题: {title!r}")
    print(f"      页面片段: {await _body_snippet(page, 200)!r}")
    print(f"      结果: {'已在商品列表(登录后真实页面)' if on_list else '被拦回登录页'}")

    print("\n  Chrome 保持打开, 请查看本机浏览器窗口。")
    return 0 if on_list else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
