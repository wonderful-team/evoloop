---
name: Window Management (macOS)
description: Standardized Maximize/Minimize/Close actions using macOS traffic light buttons or keyboard shortcuts.
namespace: os/macos
trigger_patterns:
  - "maximize the window"
  - "minimize \\{app_name\\}"
  - "close current view"
  - "hide the application"
  - "put \\{app_name\\} in full screen"
parameters:
  action:
    type: string
    description: The window action to perform (maximize, minimize, close, hide, fullscreen).
  app_name:
    type: string
    description: Optional target application. If omitted, acts on the currently focused window.
---

# 🧠 Expert Guide (心法)
This SOP defines the standard protocol for manipulating application windows visually. It is critical for clearing clutter before complex visual tasks.

## Setup & Preconditions
1. If `app_name` is provided, you MUST first ensure the application is focused. Use the `os/macos/open_and_focus_app` SOP if necessary.
2. If `app_name` is NOT provided, assume the action applies to the currently active foreground window.

## Execution Matrix based on `action`

### Action: Close
- **Primary Method (Keyboard)**: Execute `Cmd+W` to close the active *window*. If the intent is to kill the app completely, use `Cmd+Q`.
- **Fallback (Visual)**: If keyboard fails, locate the Red "Traffic Light" button in the top-left corner of the window and click it.

### Action: Minimize
- **Primary Method (Keyboard)**: Execute `Cmd+M`.
- **Fallback (Visual)**: Locate the Yellow "Traffic Light" button in the top-left corner and click it.

### Action: Maximize (Zoom)
- **Primary Method (Visual)**: macOS does not have a native "maximize" shortcut that doesn't trigger Full Screen. You MUST hold `Option` (Alt) and click the Green "Traffic Light" button.
- **Verification**: Call `verify_ui_state` to ensure the window expanded to fill the available desktop space without entering a new Space.

### Action: Fullscreen
- **Primary Method (Keyboard)**: Execute `Ctrl+Cmd+F`.
- **Fallback (Visual)**: Click the Green "Traffic Light" button without holding any modifiers.
- **Verification**: The menu bar should auto-hide.

### Action: Hide
- **Primary Method (Keyboard)**: Execute `Cmd+H`. This hides all windows of the active application without closing them.

## 🛟 Recovery Strategy
- If a visual click on the Traffic Lights fails (e.g., hidden by a custom title bar like in Chrome or Spotify), fallback immediately to the Keyboard shortcuts.
- If a "Save Changes" dialogue blocks a Close (`Cmd+W`) action, you must use `analyze_image` to read the prompt and decide whether to click "Save", "Don't Save", or "Cancel".
