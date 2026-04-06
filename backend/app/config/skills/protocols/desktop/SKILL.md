---
name: Desktop Automation Protocol
namespace: protocols
type: system_prompt_injection
trigger_patterns:
  - "打开 {app}"
  - "点击"
  - "桌面"
  - "截图"
  - "Mac"
  - "Windows"
  - "快捷键"
  - "聚焦"
  - "切换"
  - "WeChat"
  - "Chrome"
  - "微信"
  - "谷歌浏览器"
  - "桌面控制"
  - "GUI"
  - "坐标"
  - "open_app"
  - "desktop_control"
required_capabilities:
  - macos
required_tools:
  - desktop_control
  - open_app
  - screenshot
version: 1.0.0
---

## 🖥 Desktop Automation Protocol
When your mission involves MacOS/Windows desktop automation:

### ⚡ SPEED FIRST RULES

**1. ALWAYS Use Batch Mode for Multi-Step Sequences**
   - Group related actions in the SAME input field into ONE `action="batch"` call
   - This eliminates LLM round-trips and reduces screenshots by 50%+
   - ✅ **GOOD**: One batch with [click → type → cmd+return]
   - ❌ **BAD**: Three separate calls with screenshots between each

**2. 🎯 Keyboard First, Coordinates Second**
   - **ALWAYS prefer keyboard shortcuts over mouse clicks**
   - Priority: Keyboard shortcut > Coordinate click
   - Common shortcuts:
     - `return` = send message (WeChat)
     - `cmd+f` = search
     - `cmd+w` = close window/tab
     - `cmd+l` = focus address bar (Chrome)
     - `cmd+space` = Spotlight search
   - Use `click(x, y)` with coordinates when keyboard won't work

**3. ⚠️ STABLE vs UNSTABLE Operations (CRITICAL)**

   **✅ STABLE (Use these in batch):**
   - `open_app("AppName")` - Opens or focuses an app (DETERMINISTIC)
   - `key_press("cmd+l")` / `key_press("return")` - Reliable shortcuts
   - `click(x, y)` - Coordinates (stable when app is focused)
   - `type_text("...")` - Text input
   - `key_press("tab")` - Move to next field

   **❌ UNSTABLE (NEVER use in batch):**
   - `key_press("cmd+tab")` - Switches to "previous" app (UNKNOWN which one!)
   - `key_press("cmd+`")` - Switches window (UNPREDICTABLE)
   - Any operation relying on "current focus" without verifying

   **📋 Batch Planning Rule:**
   - Step 1: Ensure target app is focused (use `open_app` BEFORE batch)
   - Step 2: Batch should only operate within ONE stable context
   - Step 3: Prefer keyboard shortcuts, use coordinates only when necessary
   - NEVER assume "current app" is correct - always verify first!

**4. Smart Screenshot Strategy**
   - In batch mode: Only screenshot at START and END
   - DON'T screenshot after every intermediate step
   - Use `ocr=True` when you need to read UI text

**5. ⏱️ WAITING: Use `wait_for` Tool, NOT Screenshot Loops**
   
   When you need to wait for page load, animation, or UI transition:
   
   ✅ **CORRECT - Use generic `wait_for` tool:**
   ```python
   # After opening app or navigating, wait for UI to settle
   wait_for(seconds=2.0)
   desktop_control(action="screenshot", ocr=True)  # Then verify
   ```
   
   ❌ **WRONG - Don't loop screenshots:**
   ```python
   # DON'T repeatedly screenshot while waiting!
   desktop_control(action="screenshot", ocr=True)  # Page loading...
   desktop_control(action="screenshot", ocr=True)  # Still loading...
   desktop_control(action="screenshot", ocr=True)  # Wasteful!
   ```
   
   **Rule of Thumb:**
   - Expected wait time < 3 seconds → Use `wait_for(seconds=N)` then single screenshot
   - Need to poll for dynamic content → Wait 1-2s between screenshots, NOT continuous
   - Browser page load → Use `browser_control(action="wait_for", url_pattern="...")` if possible

### 📋 CORRECT BATCH PATTERNS (Copy-Paste Ready)

**⚠️ IMPORTANT: Always ensure app is focused BEFORE batch!**

**Pattern 1: Send WeChat Message (CORRECT)**
```python
# Step 1: Ensure WeChat is focused (OUTSIDE batch)
desktop_control(action="open_app", app_name="WeChat")
# Take screenshot with OCR to get input box coordinates
desktop_control(action="screenshot", ocr=True)

# Step 2: Batch operations within WeChat (STABLE context)
# Use coordinates from OCR, prefer keyboard shortcuts
desktop_control(action="batch", actions=[
    {"action": "click", "x": 800, "y": 900},    # Click input box (from OCR)
    {"action": "type_text", "text": "Your message here"},
    {"action": "key_press", "key": "return"}    # Keyboard shortcut to send
])
```

**Pattern 2: Chrome Navigate & Search (CORRECT - All Keyboard)**
```python
# Step 1: Ensure Chrome is active
desktop_control(action="open_app", app_name="Chrome")

# Step 2: Batch using keyboard shortcuts (NO coordinates needed!)
desktop_control(action="batch", actions=[
    {"action": "key_press", "key": "cmd+l"},    # Focus address bar
    {"action": "key_press", "key": "cmd+a"},    # Select all
    {"action": "type_text", "text": "google.com"},
    {"action": "key_press", "key": "return"}    # Navigate
])
```

**Pattern 3: Fill Form (MIXED - Keyboard + Coordinates)**
```python
# Step 1: Open/focus the application first
desktop_control(action="open_app", app_name="Safari")
desktop_control(action="screenshot", ocr=True)  # Get field coordinates

# Step 2: Batch form filling
# Use keyboard when possible, coordinates when necessary
desktop_control(action="batch", actions=[
    {"action": "click", "x": 600, "y": 400},    # Click username field
    {"action": "type_text", "text": "username"},
    {"action": "key_press", "key": "tab"},      # Use tab to move (keyboard!)
    {"action": "type_text", "text": "password"},
    {"action": "key_press", "key": "return"}    # Submit with keyboard
])
```

**❌ WRONG Pattern (DO NOT COPY):**
```python
# DON'T use cmd+tab - it's unreliable!
desktop_control(action="batch", actions=[
    {"action": "key_press", "key": "cmd+tab"},  # ❌ Unstable! Unknown app!
    {"action": "click", "x": 100, "y": 200},    # May click wrong app!
    ...
])
```

### ❌ When NOT to Use Batch

**1. Cross-Application Operations**
   - DON'T batch operations across different apps
   - ❌ BAD: `[click in Chrome → cmd+tab → type in WeChat]`
   - ✅ CORRECT: Chrome batch, then separate call for WeChat

**2. Unreliable State Transitions**
   - DON'T batch actions that trigger page/screen changes
   - ❌ BAD: `[click "Submit" → type in new page]` (page may still loading)
   - ✅ CORRECT: Click → verify → new batch for next page

**3. Unstable Operations (NEVER in batch)**
   - `cmd+tab` / `cmd+\`` (window switching)
   - Coordinate-based clicks without element_name
   - Actions depending on "current app" without open_app first

**4. Verification Required Between Steps**
   - If you need to check state between actions, don't batch
   - Example: Login attempt → check if success → next action
