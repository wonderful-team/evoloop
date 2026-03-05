import asyncio
import logging
import os

from app.core.config import settings
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Browser Manager (Persistent Singleton)
# ─────────────────────────────────────────────

class BrowserManager:
    """
    Manages a single, persistent Playwright browser session.

    Dual-mode architecture:
    ─────────────────────────────────────────────────────────
    Mode 1 (Takeover / CDP):  Detects an existing Chrome with `--remote-debugging-port`
                              and connects via ChromeDevTools Protocol. Agent actions
                              directly appear in the user's own browser window.

    Mode 2 (Auto-Launch / CDP): No existing Chrome found → launches a dedicated
                                Chrome instance (arch -arm64, separate profile dir)
                                with `--remote-debugging-port`, waits for it to boot,
                                then connects via CDP.

    Both modes use the same CDP connection path, so the rest of the codebase is
    completely unaware of which mode is active.

    Settings are managed in app.core.config.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: list = []
        self._active_page_idx: int = 0
        self._lock_pool = LoopBoundResource(asyncio.Lock)
        self._is_cdp = False
        self._chrome_proc = None  # Set if we auto-launched Chrome via subprocess

    async def get_page(self):
        """Return the active Page, lazily starting Chrome if needed."""
        async with self._lock_pool.get():
            if self._context is None:
                await self._start()
            ctx_pages = self._context.pages
            if not ctx_pages:
                self._pages = [await self._context.new_page()]
                self._active_page_idx = 0
            else:
                self._pages = list(ctx_pages)
                self._active_page_idx = min(self._active_page_idx, len(self._pages) - 1)
            return self._pages[self._active_page_idx]

    async def _start(self) -> None:
        import subprocess
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()

        # ─── Mode 1: Try Takeover (CDP – external Chrome already running) ──
        logger.info(f"[Browser] Attempting CDP takeover: {settings.CHROME_CDP_URL}")
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                settings.CHROME_CDP_URL, timeout=3000  # fast probe, 3 s
            )
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = await self._browser.new_context()
            logger.info("✅ [Browser] Mode 1: Took over existing Chrome via CDP.")
            self._is_cdp = True
        except Exception as e:
            logger.info(f"ℹ️ [Browser] No external Chrome found ({type(e).__name__}). Will auto-launch.")
            self._is_cdp = False

        # ─── Mode 2: Auto-Launch (subprocess → CDP) ─────────────────────────
        if not self._context:
            automation_dir = settings.CHROME_AUTOMATION_USER_DATA
            logger.info(f"[Browser] Mode 2: Launching Chrome-Automation → {automation_dir}")
            os.makedirs(automation_dir, exist_ok=True)

            import platform
            chrome_cmd = [settings.CHROME_EXECUTABLE]

            # Performance optimization: force native ARM64 on Apple Silicon Macs
            # Even if Python is running under Rosetta (x86_64), we want Chrome to run natively.
            is_apple_silicon = False
            if platform.system() == "Darwin":
                try:
                    # Check if the hardware supports arm64
                    is_apple_silicon = subprocess.check_output(["sysctl", "-n", "hw.optional.arm64"]).decode().strip() == "1"
                except Exception:
                    # Fallback to platform check
                    is_apple_silicon = platform.machine() == "arm64"

            if is_apple_silicon:
                chrome_cmd = ["arch", "-arm64"] + chrome_cmd

            chrome_cmd.extend([
                f"--remote-debugging-port=9222",
                f"--user-data-dir={automation_dir}",
                "--disable-infobars",
                "--disable-extensions",
                "--no-first-run",
                # "--disable-blink-features=AutomationControlled",
                "--disable-background-timer-throttling",
            ])
            try:
                self._chrome_proc = subprocess.Popen(
                    chrome_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info(f"[Browser] Chrome launched (pid={self._chrome_proc.pid}). Waiting {settings.CHROME_STARTUP_TIMEOUT}s...")
                await asyncio.sleep(settings.CHROME_STARTUP_TIMEOUT)

                self._browser = await self._playwright.chromium.connect_over_cdp(
                    settings.CHROME_CDP_URL, timeout=10000  # more lenient after launch
                )

                if self._browser.contexts:
                    self._context = self._browser.contexts[0]
                else:
                    self._context = await self._browser.new_context()
                self._is_cdp = True
                logger.info("✅ [Browser] Mode 2: auto-launched Chrome + CDP connected.")
            except Exception as e:
                logger.error(f"[Browser] Mode 2 (auto-launch CDP) failed: {e}")
                raise RuntimeError(
                    f"Browser startup failed. Could not connect to CDP at {settings.CHROME_CDP_URL}. "
                    "Please ensure Google Chrome is installed at the default path."
                ) from e

        # ─── Initialize page list ────────────────────────────────────────────
        if self._context.pages:
            self._pages = list(self._context.pages)
        else:
            self._pages = [await self._context.new_page()]
        self._active_page_idx = 0
        logger.info(
            f"[Browser] Ready — {len(self._pages)} page(s), mode={'CDP-Takeover' if self._is_cdp and not hasattr(self, '_chrome_proc') else 'CDP-AutoLaunch' if self._is_cdp else 'Launch'}.")

    async def new_tab(self, url: str | None = None):
        """Open a new tab, optionally navigate to url, and switch to it."""
        page = await self._context.new_page()
        self._pages = list(self._context.pages)
        self._active_page_idx = self._pages.index(page)
        if url:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
        return page

    def switch_tab(self, index: int):
        """Switch active tab by index."""
        if index < 0 or index >= len(self._pages):
            raise IndexError(f"Tab index {index} out of range (0–{len(self._pages) - 1})")
        self._active_page_idx = index
        return self._pages[index]

    @property
    def tab_count(self) -> int:
        return len(self._pages)

    def get_status(self) -> dict:
        """Return connectivity and state info for environment prompts."""
        if not self._context:
            return {"mode": "Disconnected", "cdp_url": settings.CHROME_CDP_URL, "tab_count": 0}

        mode = "CDP-Takeover" if self._is_cdp and not self._chrome_proc else "CDP-AutoLaunch" if self._is_cdp else "Launch"
        active_url = "None"
        try:
            if self._pages and self._active_page_idx < len(self._pages):
                active_url = self._pages[self._active_page_idx].url
        except Exception:
            pass

        return {
            "mode": mode,
            "cdp_url": settings.CHROME_CDP_URL,
            "active_url": active_url,
            "tab_count": len(self._pages),
        }

    async def close(self) -> None:
        async with self._lock_pool.get():
            # 1. Close Playwright browser/context
            if self._is_cdp and self._browser:
                await self._browser.close()
            elif self._context:
                await self._context.close()

            if self._playwright:
                await self._playwright.stop()

            # 2. Terminate auto-launched subprocess if any
            if self._chrome_proc:
                logger.info(f"[Browser] Terminating auto-launched Chrome (pid={self._chrome_proc.pid})")
                try:
                    self._chrome_proc.terminate()
                    # Wait slightly for it to die
                    for _ in range(10):
                        if self._chrome_proc.poll() is not None:
                            break
                        await asyncio.sleep(0.1)
                    if self._chrome_proc.poll() is None:
                        self._chrome_proc.kill()
                except Exception as e:
                    logger.warning(f"[Browser] Failed to terminate Chrome subprocess: {e}")
                self._chrome_proc = None

            # 3. Reset state
            self._context = None
            self._browser = None
            self._playwright = None
            self._pages = []
            self._is_cdp = False
            self._active_page_idx = 0
        logger.info("[Browser] Browser closed.")


browser_manager = BrowserManager()
