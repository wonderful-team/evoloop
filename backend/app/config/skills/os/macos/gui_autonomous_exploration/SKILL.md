---
name: MacOS GUI Autonomous Exploration
description: Standard Operating Procedure for autonomous visual navigation and exploration of the MacOS desktop environment.
namespace: os/macos
trigger_patterns:
  - "Explore the MacOS desktop"
  - "Find where the {target} is"
  - "Navigate autonomously to {target}"
  - "No SOP available for this MacOS task"
parameters:
  target:
    type: string
    description: The application, feature, or element to locate or navigate to.
---

# MacOS GUI Autonomous Exploration

## Trigger Patterns
- "Explore the MacOS desktop"
- "Find where the [app/feature] is"
- "Navigate autonomously to [target]"
- "No SOP available for this MacOS task"

## Expert Guide (心法)
When operating without a specific task-level SOP, you must adopt a **High-Precision Visual Loop**. Avoid blind clicking or guessing coordinates.

1. **Window Anchoring**: Before any interaction, call `desktop_control(action="get_active_app")` to retrieve the current window's bounding box.
2. **ROI Focused Observation**: Take a screenshot of the specific region identified in the bounds: `desktop_control(action="screenshot", region=bounds, ocr=True)`.
3. **Semantic Analysis**: Use `analyze_image` or the Integrated OCR results to identify target elements. For "Opaque" applications (e.g., WeChat), rely strictly on OCR/Vision.
4. **Single-Action Execution**: Perform ONE atomic action (click, type, key_press) based on the analysis.
5. **Incremental Verification**: Wait for the UI to transition, then repeat Step 1 to verify the state change.

## Common Application Names
- **Chrome**: `Google Chrome`
- **Finder**: `Finder`
- **System Settings**: `System Settings`
- **WeChat**: `WeChat`
- **Terminal**: `Terminal`

## AppleScript Protocol
When using `desktop_control(action="applescript")`, always escape double quotes inside strings as `\"` to avoid syntax errors. 
Example: `tell application \"System Events\" to ...`

## Verification Contract
You MUST use `verify_ui_state` after every interaction to confirm success. High confidence is required before moving to the next operational node.
