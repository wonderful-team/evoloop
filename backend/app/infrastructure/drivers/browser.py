import asyncio
import logging
import os
import platform

from app.core.config import settings
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Browser Manager (Persistent Singleton)
# ─────────────────────────────────────────────


class _PageState:
    """Pages + active index for a thread or the default session."""

    __slots__ = ("pages", "active_idx")

    def __init__(self) -> None:
        self.pages: list = []
        self.active_idx: int = 0


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

    Pages are isolated per thread_id: each voice thread/macro execution gets its
    own page in the shared browser context, preventing concurrent DOM operations
    from interfering with each other.

    Settings are managed in app.core.config.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._default_state = _PageState()
        self._thread_states: dict[str, _PageState] = {}
        self._lock_pool = LoopBoundResource(asyncio.Lock)
        self._is_cdp = False
        self._chrome_proc = None  # Set if we auto-launched Chrome via subprocess

    def _resolve_thread_id(self, thread_id: str | None) -> str | None:
        """Return explicit thread_id or fall back to the current EvoContext."""
        if thread_id:
            return thread_id
        from app.core.context import ContextManager

        tid = ContextManager.get_var("thread_id")
        if tid:
            return str(tid)
        return None

    def _get_state(self, thread_id: str | None) -> _PageState:
        """Get or create the page state for a thread (or the default session)."""
        if thread_id is None:
            return self._default_state
        state = self._thread_states.get(thread_id)
        if state is None:
            state = _PageState()
            self._thread_states[thread_id] = state
        return state

    async def get_page(self, thread_id: str | None = None):
        """Return the active Page for a thread, lazily starting Chrome if needed."""
        thread_id = self._resolve_thread_id(thread_id)
        async with self._lock_pool.get():
            # Check if existing context belongs to a connected browser
            needs_init = self._context is None
            if not needs_init and self._browser:
                if not self._browser.is_connected():
                    logger.info("[Browser] Browser disconnected. Re-initializing...")
                    needs_init = True

            if needs_init:
                await self.close_internal()  # Clean up any partial state
                await self._start()

            state = self._get_state(thread_id)
            try:
                ctx_pages = self._context.pages
                # Drop pages that have been closed (e.g. by user action or crash).
                state.pages = [p for p in state.pages if p in ctx_pages]
                if not state.pages:
                    state.active_idx = 0

                if state.pages:
                    state.active_idx = min(state.active_idx, len(state.pages) - 1)
                    return state.pages[state.active_idx]

                page = await self._context.new_page()
                state.pages.append(page)
                state.active_idx = 0
                return page
            except Exception as e:
                # Catch cases where context exists but is closed (e.g. TargetClosed)
                if "closed" in str(e).lower():
                    logger.warning(f"[Browser] Context is closed ({e}). Re-starting.")
                    await self.close_internal()
                    await self._start()
                    page = await self._context.new_page()
                    state = self._get_state(thread_id)
                    state.pages = [page]
                    state.active_idx = 0
                    return page
                raise

    async def _start(self) -> None:
        import subprocess

        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # ─── Mode 1: Try Takeover (CDP – external Chrome already running) ──
        logger.info(f"[Browser] Attempting CDP takeover: {settings.CHROME_CDP_URL}")
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(settings.CHROME_CDP_URL, timeout=3000)
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = await self._browser.new_context()
            logger.info("✅ [Browser] Mode 1: Took over existing Chrome via CDP.")
            self._is_cdp = True
        except (
            PlaywrightError,
            ValueError,
            OSError,
            RuntimeError,
            TypeError,
            KeyError,
        ) as e:
            # Playwright wraps connection-refused/timeout in its own Error type, which is
            # NOT a built-in — without it here, Mode 1 failure crashes instead of falling
            # through to Mode 2 auto-launch (dead code). Probe failure = expected "no
            # external Chrome" env condition, so catch it and auto-launch.
            logger.info(f"ℹ️ [Browser] No external Chrome found ({type(e).__name__}). Will auto-launch.")
            self._is_cdp = False

        # ─── Mode 2: Auto-Launch (subprocess → CDP) ─────────────────────────
        if not self._context:
            automation_dir = settings.CHROME_AUTOMATION_USER_DATA
            logger.info(f"[Browser] Mode 2: Launching Chrome-Automation → {automation_dir}")
            os.makedirs(automation_dir, exist_ok=True)

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

            chrome_cmd.extend(
                [
                    "--remote-debugging-port=9222",
                    f"--user-data-dir={automation_dir}",
                    "--disable-infobars",
                    "--disable-extensions",
                    "--no-first-run",
                    # "--disable-blink-features=AutomationControlled",
                    "--disable-background-timer-throttling",
                ]
            )
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

        # ─── Initialize default page list ────────────────────────────────────────────
        default_state = self._get_state(None)
        if self._context.pages:
            default_state.pages = list(self._context.pages)
        else:
            default_state.pages = [await self._context.new_page()]
        default_state.active_idx = 0
        logger.info(f"[Browser] Ready — {len(default_state.pages)} page(s), mode={'CDP-Takeover' if self._is_cdp and not hasattr(self, '_chrome_proc') else 'CDP-AutoLaunch' if self._is_cdp else 'Launch'}.")

    async def new_tab(self, url: str | None = None, thread_id: str | None = None):
        """Open a new tab, optionally navigate to url, and switch to it."""
        thread_id = self._resolve_thread_id(thread_id)
        async with self._lock_pool.get():
            needs_init = self._context is None
            if not needs_init and self._browser:
                if not self._browser.is_connected():
                    needs_init = True
            if needs_init:
                await self.close_internal()
                await self._start()

            state = self._get_state(thread_id)
            page = await self._context.new_page()
            state.pages.append(page)
            state.active_idx = len(state.pages) - 1
            if url:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            return page

    async def switch_tab(self, index: int, thread_id: str | None = None):
        """Switch active tab by index for a thread or the default session."""
        thread_id = self._resolve_thread_id(thread_id)
        async with self._lock_pool.get():
            state = self._get_state(thread_id)
            if index < 0 or index >= len(state.pages):
                raise IndexError(f"Tab index {index} out of range (0–{len(state.pages) - 1})")
            state.active_idx = index
            return state.pages[index]

    def tab_count(self, thread_id: str | None = None) -> int:
        """Return the number of tabs for a thread or the default session."""
        thread_id = self._resolve_thread_id(thread_id)
        state = self._get_state(thread_id)
        return len(state.pages)

    def get_status(self, thread_id: str | None = None) -> dict:
        """Return connectivity and state info for environment prompts."""
        thread_id = self._resolve_thread_id(thread_id)
        state = self._get_state(thread_id)
        if not self._context:
            return {
                "mode": "Disconnected",
                "cdp_url": settings.CHROME_CDP_URL,
                "tab_count": 0,
            }

        mode = (
            "CDP-Takeover"
            if self._is_cdp and not self._chrome_proc
            else "CDP-AutoLaunch"
            if self._is_cdp
            else "Launch"
        )
        active_url = "None"
        try:
            if state.pages and state.active_idx < len(state.pages):
                active_url = state.pages[state.active_idx].url
        except Exception as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)

        return {
            "mode": mode,
            "cdp_url": settings.CHROME_CDP_URL,
            "active_url": active_url,
            "tab_count": len(state.pages),
        }

    async def close(self) -> None:
        """Public entry to close the browser, synchronized."""
        async with self._lock_pool.get():
            await self.close_internal()

    async def close_internal(self) -> None:
        """Internal close logic, caller must hold the lock."""
        # 1. Close Playwright browser/context
        if self._is_cdp and self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)
        elif self._context:
            try:
                await self._context.close()
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

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
        self._default_state = _PageState()
        self._thread_states = {}
        self._is_cdp = False
        self._chrome_proc = None
        logger.info("[Browser] Browser closed.")


browser_manager = BrowserManager()
