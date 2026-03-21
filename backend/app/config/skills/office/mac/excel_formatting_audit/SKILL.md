---
name: Excel Formatting Audit (macOS)
description: Visual inspection of Excel/Numbers sheets for styling compliance (colors, bold headers, frozen panes).
namespace: office/mac
trigger_patterns:
  - "audit the formatting of \\{filename\\}"
  - "check excel styles for \\{filename\\}"
  - "verify spreadsheet compliance"
parameters:
  filename:
    type: string
    description: The name of the Excel or Numbers file to audit.
    required: true
---

# 🧠 Expert Guide (心法)
This SOP dictates how to perform visual quality assurance on spreadsheet styling. Since software libraries often miss formatting metadata (like background colors or frozen status), you must use the native application GUI.

## Phase 1: Setup
1. **Focus App**: Use `os/macos/find_and_open_file` to open the target `filename`.
2. **Standardize View**: Ensure the window is focused and resized to a clear desktop view (`window_management`).
3. **Wait for Load**: Wait 3 seconds for heavy files to render grid lines and styling.

## Phase 2: Visual Checklist
Perform the following checks via `analyze_image`:

1. **Header Recognition**:
   - Are the top row headers **Bold**?
   - Is there a specific background color (e.g., standard corporate blue #003366)?
2. **Frozen Panes**:
   - Scroll the mouse downwards slightly using `mouse_scroll`.
   - **Verification**: Does the first row remain visible while the data flows under it?
3. **Data Alignment**:
   - Are numeric columns right-aligned?
   - Are text columns left-aligned?
4. **Conditional Formatting**:
   - Search for "Red" cells. If found, do they correspond to negative numbers or "Fail" statuses as per the project rules?

## Phase 3: Reporting
1. Compile a list of non-compliant coordinates (e.g., "Cell B1 background is White, expected Blue").
2. Save the report and close the application (`Cmd+Q`).

## 🛟 Recovery Strategy
- **Password Protected**: If the file opens to a Password prompt, call `request_human_input`.
- **Wrong Sheet**: If the file has multiple tabs, look at the bottom tab bar. Use `visual_click` on the tab name matching your audit target.
