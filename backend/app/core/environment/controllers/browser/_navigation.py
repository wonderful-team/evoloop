"""
Browser controller mixin — navigation actions.
"""

from app.utils.controller_response import ControllerResponse


class BrowserNavigationMixin:
    @classmethod
    async def _handle_navigation(cls, action: str, **ctx) -> str | None:
        page = ctx["page"]
        recording_func = ctx["recording_func"]

        if action == "navigate":
            url = ctx.get("url")
            if not url:
                return ControllerResponse.missing_param("url")
            await page.goto(url, wait_until="load", timeout=60_000)
            await recording_func("navigate", {"url": url})

            post_url = page.url
            post_title = await page.title()
            return ControllerResponse.navigation_result(post_url, success=True, title=post_title)

        elif action == "back":
            await page.go_back(wait_until="load", timeout=15_000)
            await recording_func("back", {})
            return ControllerResponse.success(f"Navigated back. URL: {page.url}")

        elif action == "forward":
            await page.go_forward(wait_until="load", timeout=15_000)
            return ControllerResponse.success(f"Navigated forward. URL: {page.url}")

        elif action == "reload":
            await page.reload(wait_until="load", timeout=20_000)
            return ControllerResponse.success(f"Page reloaded. URL: {page.url}")

        elif action == "get_url":
            from app.infrastructure.drivers.browser import browser_manager

            return ControllerResponse.success(
                f"URL: {page.url}",
                details=f"Title: {await page.title()}\nTabs open: {browser_manager.tab_count}",
            )

        return None
