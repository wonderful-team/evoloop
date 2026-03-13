import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto("https://www.goofish.com/", wait_until="networkidle")
        locators = page.locator("input")
        count = await locators.count()
        for i in range(count):
             print(f"[{i}] Input HTML:", await locators.nth(i).evaluate("el => el.outerHTML"))
        
        button_locators = page.locator("button")
        btn_count = await button_locators.count()
        for i in range(btn_count):
             print(f"[{i}] Button HTML:", await button_locators.nth(i).evaluate("el => el.outerHTML"))
             
        await browser.close()

asyncio.run(main())
