---
name: open_and_focus_app
description: Standard procedure to open and ensure an application is focused on macOS.
namespace: os/macos
trigger_patterns:
  - "Open {{app_name}}"
  - "Switch to {{app_name}}"
parameters:
  - name: app_name
    type: string
    description: Name of the application (e.g., Safari, Terminal)
    required: true
preconditions:
  - "System is responsive"
---

# Expert Skill Guide: Opening & Focusing Applications

## 1. Mental Model
Opening an application is a two-stage process: invocation and verification. We use Spotlight for speed and reliability, and verify focus via the Accessibility (AX) tree.

## 2. Contextual Anchors
- **Visual Evidence**: The Application menu bar (top left) should reflect the `app_name`.
- **AX Tree**: The `AXApplication` element with the matching title should be present.

## 3. Strategic Guidance
- **Phase 1 (Open)**: Use `desktop_control(action="open_app", app_name=app_name)`. This is faster than clicking the Dock.
- **Phase 2 (Wait)**: Wait 2-3 seconds for CPU/Disk spikes to settle.
- **Phase 3 (Verify)**: If focus isn't confirmed, use Cmd+Tab or click the app icon in the Dock semanticlly.

## 4. Recovery
- If the app doesn't appear, check if it's already open but in another Space or hidden.
- If Spotlight fails, use `applescript` to launch: `tell application "app_name" to activate`.
