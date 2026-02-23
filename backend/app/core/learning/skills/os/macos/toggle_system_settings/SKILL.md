---
name: Toggle System Settings (macOS)
description: Navigating System Preferences or Control Center via GUI to toggle hardware or environment settings (Wi-Fi, Bluetooth, Dark Mode).
namespace: os/macos
trigger_patterns:
  - "turn on Wi-Fi"
  - "disable Bluetooth"
  - "toggle dark mode"
  - "switch system language"
  - "change display resolution"
parameters:
  setting_target:
    type: string
    description: The generic name of the setting to toggle (e.g., wifi, bluetooth, dark_mode).
  desired_state:
    type: string
    description: The desired state (on, off, toggle, specific_value).
---

# 🧠 Expert Guide (心法)
This SOP defines how to manipulate native macOS hardware/environment settings via GUI when shell scripts (`networksetup` or `defaults write`) are prohibited or unreliable. 

## Strategy Choice
Determine the fastest route based on the `setting_target`:
- **Fast Track (Control Center)**: If `setting_target` is Wi-Fi, Bluetooth, Airdrop, Do Not Disturb, or Display Brightness.
- **Deep Track (System Settings)**: If `setting_target` is related to Privacy, Notifications, Language, or Displays resolution.

---

## Path A: Fast Track (Control Center)
1. **Focus Desktop**: Ensure no full-screen apps block the top menu bar.
2. **Open Control Center**: Click the Control Center icon (slider icon) in the top-right menu bar.
3. **Verify UI**: Wait for the Control Center popover. Use `verify_ui_state` to confirm generic icons are visible.
4. **Locate Target**: Use visual targeting to locate the specific module (e.g., the Wi-Fi text or Bluetooth icon).
5. **Toggle/Expand**:
   - For simple toggles (On/Off): Click the icon.
   - For specific connections (e.g., Connect to "HomeNet"): Click the ">" arrow next to the icon to expand, read the list, and click the desired network/device.
6. **Dismiss**: Click anywhere outside the popover to close the Control Center.

---

## Path B: Deep Track (System Settings)
1. **Launch App**: Click the Apple Logo  (top-left corner), then click "System Settings..." ("System Preferences..." on macOS ≤ 12).
2. **Search Mechanism**: The sidebar contains categories. Do NOT scroll visually; it's inefficient. Instead, click the Search bar in the top-left of the System Settings window.
3. **Input Query**: Type the `setting_target` into the search box.
4. **Verify UI**: Wait 1 second for the search results to populate in the right-hand panel. Use `verify_ui_state`.
5. **Execute Action**: Locate the radio button, toggle switch, or dropdown matching your `desired_state`. Click to apply the change.
6. **Teardown**: Close the System Settings window (Cmd+W).

## 🛟 Recovery Strategy
- **Control Center Missing**: If the icon is hidden by third-party menu apps (like Bartender), default to Path B (System Settings).
- **Search Failed**: If the localized OS language differs from your search term (e.g., searching "Wi-Fi" on a French Mac), fallback to visual scrolling of the left sidebar categories.
