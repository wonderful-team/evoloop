"""真实宏: 登录态条件 + 搜索 + 读取, 经生产 MacroService.run 在可见 Chrome 中执行。

诚实边界: 这里直接调用生产 MacroService.run(技能系统 skill_execution.py:155 走的就是它),
宏引擎 / 条件求值(element_exists, 刚修好的 bug)/ 浏览器执行 / 抽取 全部真实。
唯一 stub 的是 activity_monitor 遥测(start_run/log_event/end_run), 以避免与正在运行的
backend 争用 SQLite/Redis —— 不影响宏逻辑本身。

演示三段:
  Run 1  当前态(可能已登录或未登录)
  Run 2  紧接着(此时必有会话)  -> 期望 login_branch=skipped_login
  Run 3  clear_cookies 后       -> 期望 login_branch=did_login
"""
import asyncio
import os

os.environ.setdefault("EVOLOOP_CHROME_CDP_URL", "http://127.0.0.1:9222")

GOODS_LIST_URL = "http://127.0.0.1:9002/shop/goods/lists"


def _stub_activity_monitor():
    from app.core.monitoring.activity import activity_monitor

    async def _noop(*args, **kwargs):  # noqa: ARG001 - deliberate catch-all stub
        return None

    activity_monitor.start_run = _noop
    activity_monitor.end_run = _noop
    activity_monitor.log_event = _noop


def build_macro():
    mark_then = {"step_number": 37, "type": "extract", "extract_type": "run_js",
                 "source": "dom", "payload": {"script": "() => 'did_login'"}, "key": "login_branch"}
    mark_else = {"step_number": 38, "type": "extract", "extract_type": "run_js",
                 "source": "dom", "payload": {"script": "() => 'skipped_login'"}, "key": "login_branch"}
    return [
        # 1. 打开商品列表(未登录会被商城 302 到登录页)
        {"step_number": 1, "type": "action", "event_type": "navigate", "source": "dom",
         "payload": {"url": GOODS_LIST_URL, "wait_until": "load"}},
        {"step_number": 2, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 2}},

        # 2. 登录态条件: 登录表单(input[name=username])存在 => 未登录 => 走登录; 否则跳过
        {"step_number": 3, "type": "if", "source": "dom",
         "condition": {"type": "element_exists", "target_selector": 'input[name="username"]'},
         "then_steps": [
            {"step_number": 31, "type": "action", "event_type": "type_text", "source": "dom",
             "target_selector": 'input[name="username"]', "payload": {"text": "{{mall_user}}"}},
            {"step_number": 32, "type": "action", "event_type": "type_text", "source": "dom",
             "target_selector": 'input[name="password"]', "payload": {"text": "{{mall_pass}}"}},
            {"step_number": 33, "type": "action", "event_type": "key_press", "source": "dom",
             "payload": {"key": "Enter"}},
            {"step_number": 34, "type": "action", "event_type": "wait", "source": "dom",
             "payload": {"seconds": 4}},
            {"step_number": 35, "type": "action", "event_type": "navigate", "source": "dom",
             "payload": {"url": GOODS_LIST_URL, "wait_until": "load"}},
            {"step_number": 36, "type": "action", "event_type": "wait", "source": "dom",
             "payload": {"seconds": 2}},
            mark_then,
         ],
         "else_steps": [mark_else]},

        # 3. 搜索商品
        {"step_number": 4, "type": "action", "event_type": "type_text", "source": "dom",
         "target_selector": 'input[name="search_text"]', "payload": {"text": "{{search}}"}},
        {"step_number": 5, "type": "action", "event_type": "click", "source": "dom",
         "target_selector": 'button[lay-filter="search"]', "payload": {}},
        {"step_number": 6, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 3}},

        # 4. 读取结果表格(layui 渲染在 .layui-table-main, #goods_list 是空占位)
        {"step_number": 7, "type": "extract", "extract_type": "get_text", "source": "dom",
         "target_selector": ".layui-table-main", "key": "goods_table"},
    ]


async def run_macro(thread_id, params):
    from app.core.execution.macro.service import MacroService
    return await MacroService.run(thread_id, build_macro(), params=params)


async def report(label, res):
    from app.infrastructure.drivers.browser import browser_manager
    page = await browser_manager.get_page()
    data = res.extracted_data or {}
    branch = str(data.get("login_branch", "?")).replace("JS result: ", "")
    table = str(data.get("goods_table", "")).replace("\n", " ").strip()[:150]
    print(f"\n===== {label} =====")
    print("  success     :", res.success, "|", res.message)
    print("  login_branch:", branch)
    print("  final       :", page.url, "|", await page.title())
    print("  goods_table :", table)
    return branch


async def main():
    _stub_activity_monitor()
    from app.infrastructure.drivers.browser import browser_manager

    params = {
        "mall_user": os.environ.get("MALL_USER", "admin"),
        "mall_pass": os.environ.get("MALL_PASS", "admin888"),
        "search": os.environ.get("MALL_SEARCH", "订阅"),
    }

    page = await browser_manager.get_page()
    print("browser ready (visible):", page.url)

    res1 = await run_macro("macro-real-1", params)
    await report("Run 1 当前态", res1)

    res2 = await run_macro("macro-real-2", params)
    b2 = await report("Run 2 已登录态 (期望 skipped_login)", res2)

    print("\n----- clear_cookies 模拟登出 -----")
    await page.context.clear_cookies()

    res3 = await run_macro("macro-real-3", params)
    b3 = await report("Run 3 未登录态 (期望 did_login)", res3)

    print("\n===== 判定 =====")
    print("  Run2 跳过登录?", "PASS" if b2 == "skipped_login" else f"FAIL(got {b2})")
    print("  Run3 执行登录?", "PASS" if b3 == "did_login" else f"FAIL(got {b3})")

    await browser_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
