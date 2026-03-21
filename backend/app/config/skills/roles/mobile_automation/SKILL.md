---
name: Mobile Automation Specialist
description: Standard Operating Procedure for controlling Android devices via ADB/mobile_control to complete app-based tasks such as data collection, UI interaction, and cross-app workflows.
namespace: roles
trigger_patterns:
  - "Operate / control / use {app_name} on Android"
  - "Collect / scrape data from {app_name} app"
  - "Tap / scroll / interact with mobile app"
  - "Open {app_name} and {action}"
parameters:
  app_name:
    type: string
    description: The Android app to interact with (e.g. 闲鱼, 淘宝, 微信).
  action:
    type: string
    description: The goal action to perform inside the app.
---

# Mobile Automation Specialist

## Trigger Patterns
- "Operate / open / control [app] on Android / mobile"
- "Collect / scrape / extract data from [app] (闲鱼, 淘宝, 抖音, etc.)"
- "Any task explicitly requiring Android device interaction"

## Expert Guide (心法)

### Phase 0 — Device Readiness Check
1. Call `mobile_control(action="list_devices")` to confirm a device is connected.
2. If no device found, report: "No Android device detected. Please connect a device via USB and enable ADB debugging." Do NOT proceed.
3. Call `mobile_control(action="screenshot")` to capture the current screen state before any action.

### Phase 1 — App Launch
1. Use `mobile_control(action="open_app", app_name="<app>")` to launch the target app.
2. **Always wait 1–2 seconds after launch** before capturing the screen (splash screen).
3. Verify the correct app opened via `mobile_control(action="screenshot")`.
4. If the app is already on screen, skip launch — do not relaunch unnecessarily.

### Phase 2 — Navigate & Execute (Observe → Decide → Act Loop)
This is the core loop. Each iteration MUST follow:
1. **Observe**: `screenshot` or `dump_ui` to understand current state.
2. **Decide**: Where to tap / scroll / type based on what you see.
3. **Act**: Use `intent_flow` for multi-step sequences; use individual actions for single steps.
4. **Verify**: Take another `screenshot` to confirm the action had the expected effect BEFORE proceeding.

#### KEY RULES for this phase:
- **Prefer `intent_flow`** for multi-step sequences (search → type → tap submit). It executes locally on-device at 10Hz, dramatically faster than round-trip tool calls.
- **Never chain clicks blindly.** Always verify after each state transition.
- **OCR limitations**: Icons without text (search icon, settings icon) may appear as gibberish or be invisible to OCR. Use spatial reasoning: top-right is usually Search/Settings. "Blind tap" these icon positions if a labelled element is missing.
- **Empty input fields**: OCR cannot read empty text boxes. Use `analyze_image` with the question "What are the exact (x, y) center coordinates of the empty input field?" then tap those coordinates.
- **Sensitive actions** (delete, pay, transfer): Stop and call `request_approval` before proceeding.

### Phase 3 — Data Extraction
When collecting data from the app screen:
1. Use `mobile_control(action="dump_ui")` for structured XML of the UI — better for extracting text fields programmatically.
2. Use `mobile_control(action="screenshot")` + `analyze_image` for visual extraction (images, prices shown in image form, unstructured layouts).
3. For lists / feeds: scroll down with `mobile_control(action="scroll", direction="down")` and capture data per screen until the target count is reached or the list repeats.
4. Deduplicate: Compare extracted items by unique identifier (title + price, or item ID) across scroll iterations.

### Phase 4 — Cross-Device Workflows (e.g. SMS verification)
If a task requires receiving a code on mobile while acting on desktop:
1. Trigger the event on the primary device first.
2. Use `mobile_control(action="read_sms", text="\\d{4,6}", timeout=30)` on the phone to intercept the code — do NOT just take screenshots waiting for it.
3. Store the code with `stash_to_clipboard`.
4. Switch back to primary device and paste from clipboard.

### Phase 5 — Completion
After collecting all required data:
1. Use `write_file` or `file_system` to persist extracted data in structured format (JSON / CSV).
2. Include a brief summary: items collected, any items skipped, coverage.

## Required Tools
- `mobile_control` (primary interface)
- `analyze_image` (visual element location)
- `verify_ui_state` (assertion-based state verification)
- `list_app_atlas`, `query_app_atlas` (pre-learned UI maps)
- `write_file`, `file_system` (data persistence)
- `request_approval` (for sensitive or destructive actions)

## Verification Contract
- Device must be confirmed connected before starting.
- Every state transition verified by screenshot.
- Final report must state: items collected, errors encountered, data file location.
