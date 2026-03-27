---
name: Take and Save Screenshot (macOS)
description: Utilizing the native snipping tool (Cmd+Shift+4) to capture specific regions and verifying the save location on disk.
namespace: os/macos
trigger_patterns:
  - "take a screenshot of \\{region\\}"
  - "capture the \\{app_name\\} window"
  - "snip the screen"
  - "save a picture of the desktop"
parameters:
  region:
    type: string
    description: Optional description of the area to capture (e.g., full screen, active window, specific coordinates).
  app_name:
    type: string
    description: Optional target application window to capture.
---

# 🧠 Expert Guide (心法)
This SOP defines how to take system-level screenshots and ensure they are saved to a known location, rather than relying solely on the Agent's internal `desktop_control(action="screenshot")` action which only returns base64 data to the LLM context.

## Setup & Preconditions
1. Ensure the target `app_name` or `region` is visible on the screen.
2. The default macOS screenshot save location is usually `~/Desktop`. You must verify this after capture.

## Execution Matrix based on `region`

### Action: Full Screen
1. **Execute Capture**: Use the `keyboard` tool to press `Cmd+Shift+3`.
2. **Audio/Visual Cues**: You will hear a camera shutter sound. A thumbnail will appear in the bottom-right corner for a few seconds. Do NOT click the thumbnail unless you intend to annotate it.
3. **Verify File**: Execute `execute_command` command `ls -t ~/Desktop | grep "Screen Shot" | head -n 1`. Confirm the file exists.

### Action: Active Window (Clean Capture)
1. **Focus Window**: Ensure the target application is in the foreground.
2. **Trigger Crosshairs**: Press `Cmd+Shift+4`. The cursor will turn into a crosshair.
3. **Switch to Window Mode**: Press the `Spacebar`. The crosshair will turn into a Camera icon, and the active window will be highlighted green/blue.
4. **Execute Capture**: Perform a Left Click (`click` at current position or `Enter` if supported).
5. **Verify File**: Check `~/Desktop` for the new file as above.

### Action: Specific Region (Drag Select)
1. **Trigger Crosshairs**: Press `Cmd+Shift+4`.
2. **Execute Drag**: This is complex for an Agent. You MUST use the `mouse_drag` tool (if available in your `desktop_control` suite) from `(start_x, start_y)` to `(end_x, end_y)`.
3. **Fallback**: If `mouse_drag` is unavailable or unreliable, fallback to capturing the Full Screen and using a command tool (like ImageMagick `convert -crop`) to crop it later.

## 🛟 Recovery Strategy
- **Thumbnail Stuck**: If the thumbnail in the bottom right blocks UI elements you need to interact with, swipe it away (simulate a right-to-left swipe on trackpad) or wait 5 seconds for it to disappear naturally.
- **File Not on Desktop**: If the file is not on the desktop, the user may have changed the default location. Execute `defaults read com.apple.screencapture location` via execute_command to find where it went.
