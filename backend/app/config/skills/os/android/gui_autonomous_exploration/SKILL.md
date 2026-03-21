---
name: Android GUI Autonomous Exploration
description: Standard Operating Procedure for autonomous visual navigation and exploration of the Android mobile environment.
namespace: os/android
trigger_patterns:
  - "Explore the Android device"
  - "Find where the {target} is in the app"
  - "Navigate autonomously to {target} on Android"
  - "No SOP available for this Android task"
parameters:
  target:
    type: string
    description: The application, feature, or element to locate or navigate to.
---

# gui_autonomous_exploration (Android)

Standard Operating Procedure for autonomous visual navigation and exploration of connected Android devices via ADB/Mobile Control.

## Trigger Patterns
- "Explore the Android phone"
- "Navigate on the mobile device"
- "Find the [app] on Android"
- "No SOP available for this Mobile task"

## Expert Guide (心法)
Mobile UI is dense and volatile. Follow the **Strict Mobile Verification Loop**:

1. **Snapshot**: Capture the current screen state: `mobile_control(action="screenshot")`.
2. **AX Tree Analysis**: Dump the accessibility tree: `mobile_control(action="dump_ax_tree")`.
3. **Cross-Validation**: Compare visual elements from the screenshot with the AX tree labels to ensure the target is interactable.
4. **Focused Action**: Execute `mobile_control(action="click", ...)` or `mobile_control(action="type_text", ...)`.
5. **State Lock**: Wait for the activity transition (approx 1-2s) and verify the new state using `verify_ui_state`.

## Common Package Names
- **Settings**: `com.android.settings`
- **Browser**: `com.android.chrome`
- **Files**: `com.google.android.documentsui`
- **Phone**: `com.android.dialer`

## Verification Contract
Mobile environments have high latency. Always verify navigation results visually before attempting deep data entry or multi-step logic.
