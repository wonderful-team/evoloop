"""一次性探针: 接管已登录 Chrome, dump 商品列表的搜索/表格真实选择器(供宏用)。"""
import asyncio
import os

os.environ.setdefault("EVOLOOP_CHROME_CDP_URL", "http://127.0.0.1:9222")

GOODS_LIST_URL = "http://127.0.0.1:9002/shop/goods/lists"


async def main():
    from app.infrastructure.drivers.browser import browser_manager

    page = await browser_manager.get_page()
    await page.goto(GOODS_LIST_URL, wait_until="load", timeout=60_000)
    await page.wait_for_timeout(2500)
    print("URL:", page.url, "| title:", await page.title())

    for sel in ["input", "button", "table", ".layui-table"]:
        els = await page.query_selector_all(sel)
        print(f"\n--- {sel}: {len(els)} ---")
        for e in els[:10]:
            info = await e.evaluate(
                "el => ({name: el.name||'', id: el.id||'', cls: (el.className||'').toString().slice(0,40), "
                "ph: el.placeholder||'', type: el.type||'', text: (el.innerText||'').trim().slice(0,24)})"
            )
            print("   ", info)


if __name__ == "__main__":
    asyncio.run(main())
