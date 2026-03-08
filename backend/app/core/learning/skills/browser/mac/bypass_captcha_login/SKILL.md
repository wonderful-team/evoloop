---
name: Bypass Captcha Login (Browser)
description: Fallback protocol for delegating slider/image captchas to the VLM (Vision Large Language Model) or pausing for human intervention.
namespace: browser/mac
trigger_patterns:
  - "solve the captcha"
  - "verify I am human"
  - "complete the security check on \\{app_name\\}"
parameters:
  app_name:
    type: string
    description: Optional target application displaying the captcha.
---

# 🧠 Expert Guide (心法)
This SOP dictates how to handle anti-bot friction (captchas) encountered during automated browsing. It prioritizes autonomous visual deduction before escalating to human intervention.

## Setup & Preconditions
1.  **Identify Captcha**: You must be currently viewing a page with a visible captcha challenge.
2.  **Ensure Visibility**: Make sure no browser toolbars or system dialogs obscure the captcha widget.

## Execution Matrix based on Captcha Type

### Type 1: Text/Image Recognition (Find the Traffic Lights)
1.  **Analyze Image**: Use `desktop_control(action="screenshot")` to capture the entire captcha challenge box.
2.  **VLM Deduction**: Instruct the VLM (`analyze_image`) to identify the exact coordinates `(x, y)` of the requested objects (e.g., "all images with traffic lights").
1.  **Analyze Image**: Use `browser_control(action="screenshot")`.
2.  **Deduction**: Identify coordinates `(x, y)` of target objects from OCR results or VLM analysis.
3.  **Execute Clicks**: Use `browser_control(action="click", x=..., y=...)` for each coordinate.
4.  **Submit**: Click "Verify" using selector or coordinate.

### Type 2: Slider/Puzzle (Drag to Fit) - **PRIORITY: OS-Level Control**
⚠️ **CRITICAL**: Complex slider captchas (yidun, geetest, etc.) often have iframe protection and anti-bot detection that `browser_control` cannot bypass.

**Recommended Approach - Desktop Control**:
1.  **Take Snapshot**: Use `desktop_control(action="screenshot")` to capture the entire screen including the captcha widget.
2.  **Visual Analysis**: Use `analyze_image` with question: "What are the exact coordinates (x, y) of the slider thumb and the target gap/hole?"
3.  **Execute Drag at OS Level**: Use `desktop_control(action="drag_drop", x=<thumb_x>, y=<thumb_y>, x2=<target_x>, y2=<thumb_y>)`
    - **Why OS Level**: `desktop_control` bypasses all browser/iframe restrictions and anti-bot detection
    - The drag is performed by the OS mouse driver, indistinguishable from human operation

**Fallback - Browser Level** (only for simple sliders without protection):
- Use `browser_control(action="drag_drop", source_selector="...", target_selector="...")`
- If this fails or enters infinite loop, immediately switch to Desktop Control approach above.

### Type 3: Simple Checkbox (I am not a robot)
1.  **Execute Click**: Identify the checkbox via `browser_control(action="find_element", selector=".recaptcha-checkbox")` and click it.

## 🛟 Recovery Strategy
- **Loop Failure**: If repeated attempts fail, the site has detected automated patterns. Call `request_human_input` and ask the user to solve it manually.
- **Invisible ReCAPTCHA**: If the login fails without a visible challenge, halt and request human assistance.
