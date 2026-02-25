---
name: Vision-Guided Info Bridge
description: A high-precision cross-app skill that scrapes information from a source application (e.g., Browser) and shares it with a verified contact in a target app (e.g., WeChat) using window-aware vision scanning.
namespace: cross_app
trigger_patterns:
  - "find information about \\{topic\\} on Chrome and send a summary to \\{contact_name\\} in WeChat"
  - "share the latest \\{topic\\} news with \\{contact_name\\}"
  - "research \\{topic\\} and forward the results to \\{contact_name\\} on \\{im_app\\}"
parameters:
  topic:
    type: string
    description: The subject to search for or extract.
    required: true
  contact_name:
    type: string
    description: The specific person or group in the target application.
    required: true
  im_app:
    type: string
    description: "The target application (e.g., WeChat, Lark, Slack). Default: WeChat."
    default: "WeChat"
---

# 🧠 Expert Guide (心法)
This skill leverages "Window-Aware Vision" to ensure precision in complex UI environments. It eliminates background noise by focusing the Agent's "eyes" only on the active window bounds.

> [!IMPORTANT]
> **The Coordinate Offset Rule (必杀技)**:
> When using `screenshot(region="x,y,w,h")`, the OCR results will be relative to that region.
> You MUST manually calculate the absolute screen coordinates before clicking:
> `Absolute_X = window_x + relative_x`
> `Absolute_Y = window_y + relative_y`

## 🚀 Execution Workflow

### 1. Discovery & Synthesis (Source App)
- **Action**: Focus source app and extract `topic` information.
- **Extraction**: Identify keywords or summaries.
- **Buffer**: Use the clipboard (`Cmd+C` or `pbcopy`) to store the content for reliable cross-app transfer.

### 2. Contextual Focus (Target App)
- **Targeting**: Use `desktop_control(action="open_app")` to focus `im_app`. Wait for the tool to return the window `bounds`.
- **Coordinate Extraction**: Split the `bounds` string into `win_x, win_y, win_w, win_h`.
- **ROI Scanning**: Use `desktop_control(action="screenshot", region=bounds)` to performs an OCR scan focused strictly on the application's interface.

### 3. Precise Navigation & Interaction
- **Search**: Locate the search icon or bar using the OCR result from the focused scan.
- **Offset Math**: ADD `win_x` and `win_y` to the search bar coordinates found in the OCR.
- **Batch Typing**: Call `desktop_control(action="batch")` to click the search bar and type `contact_name`.
- **Target Selection**: Re-scan the result list using a focused screenshot. Distinguish the "Real" contact from input mirrors by filtering elements by `y > 60`.

### 4. Verification & Submission
- **Window Check**: Verify `get_active_app` returns a `title` containing `contact_name`.
- **Visual Check**: Perform a secondary focused scan of the top-header area (usually `y:0` to `y:100` within the window) to confirm header text.
- **Final Send**: Paste (`Cmd+V`) and Send (`Enter`).

## 🛟 Recovery Strategy
- **Search Latency**: If results don't appear, wait 1s and re-scan the region.
- **Ambiguous Matches**: If multiple matches exist, check secondary labels via OCR.
- **Bounds Failure**: Fallback to full-screen `desktop_control(action="screenshot")` but ignore the OS Menu Bar (y < 25).
