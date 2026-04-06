---
name: Browser Automation Protocol
namespace: protocols
type: system_prompt_injection
trigger_patterns:
  - "浏览器"
  - "网页"
  - "打开网站"
  - "搜索"
  - "点击链接"
  - "导航"
  - "访问"
  - "URL"
  - "Chrome"
  - "Safari"
  - "网页截图"
  - "DOM"
  - "元素"
  - "选择器"
  - "browser_control"
  - "navigate"
required_capabilities: []
required_tools:
  - browser_control
  - navigate
  - click
version: 1.0.0
---

## 🌐 Browser Automation Protocol
When your mission involves web pages or browser UI:

1. **Use `browser_control` directly**: It handles the entire lifecycle, including automatically launching Chrome if it's not already running.
2. **DOM-first interaction**: Always prefer `selector`-based actions (`click`, `type_text`, `wait_for`) for maximum precision and speed.
3. **OS Coordination**: Only use `desktop_control` for tasks *outside* the browser viewport (e.g., handling native macOS dialogs, uploading files from a non-browser folder, or bringing the browser window to focus if another app is covering it).
4. **State Persistence**: Cookies and session state are preserved across tool calls.
5. **Robust Text Selection**: When matching elements by `text="..."` (in `click`, `wait_for`, etc.), NEVER use long phrases or full sentences. The HTML DOM may split text across multiple nodes causing text match timeouts. Always use a SHORT, UNIQUE keyword.
6. **Coordinate Fallback**: If DOM interaction fails or you cannot find the right selector, you can fall back to using `x` and `y` coordinates for `click` with `browser_control` if you have spatial information from `screenshot` OCR.
7. **Fixed-Time Waiting**: If you just need to wait for a fixed duration, DO NOT use `browser_control(action="wait_for")` with only `timeout_ms`. `wait_for` strictly requires a `selector`, `text`, or `url_pattern`. To sleep, use the generic `wait` tool instead.
