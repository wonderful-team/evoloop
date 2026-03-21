---
name: Responsive Layout Audit (QA)
description: Resizing the browser window to mobile/tablet breakpoints and visually hunting for UI clipping/overflow bugs.
namespace: qa/testing
trigger_patterns:
  - "test responsiveness on \\{url\\}"
  - "check mobile layout for \\{page_name\\}"
  - "audit the CSS breakpoints"
  - "verify it works on phone and tablet"
parameters:
  url:
    type: string
    description: Optional target URL.
  page_name:
    type: string
    description: Optional target page to audit.
---

# 🧠 Expert Guide (心法)
This SOP defines the automated visual auditing process across standard device breakpoints (Mobile, Tablet, Desktop) to identify CSS regressions, overflows, and missing responsive elements (like Hamburger menus).

## Setup & Preconditions
1. Navigate to the target `url` or `page_name` in a Chromium-based browser (Chrome, Edge, etc.) or Safari.
2. Define the Target Breakpoints:
   - **Mobile**: 375x812 (iPhone 12/13/14)
   - **Tablet**: 768x1024 (iPad Mini/Air)
   - **Desktop**: 1920x1080 (Standard 1080p)

## Execution Loop (Per Breakpoint)
Execute the following steps for **each** target breakpoint defined above.

1.  **Resize Viewport**:
    *   **Method A (Preferred - Browser DevTools)**: Use `keyboard` shortcut to open DevTools (`Cmd+Option+I` on Mac), click the "Device Toolbar" toggle (`Cmd+Shift+M`), and select the target device from the dropdown, OR manually input the dimensions.
    *   **Method B (System Level - AppleScript)**: Use the `bash` tool to execute AppleScript to forcefully resize the active application window. Example for Chrome to Mobile:
        ```bash
        osascript -e 'tell application "Google Chrome" to set bounds of window 1 to {0, 0, 375, 812}'
        ```
2.  **Wait for Reflow**: Wait 2 seconds for CSS Media Queries to apply and animations to settle.
3.  **Visual Sweep (The Audit)**:
    *   Take a `desktop_control(action="screenshot")` of the top of the page.
    *   Execute a `keyboard` `Page Down` scroll.
    *   Take another screenshot. Repeat 2-3 times to cover the main content.
4.  **VLM Analysis (`analyze_image`)**: Instruct the VLM to scrutinize the screenshots for the following specific defects:
    *   **Overflow/Clipping**: Text or images spilling out of their container boxes or off the edge of the screen.
    *   **Overlap**: Buttons or text illegibly overlapping each other.
    *   **Missing Navigation**: The main desktop navigation bar disappeared, but NO Hamburger menu (☰) appeared to replace it.
    *   **Tiny Tap Targets**: Buttons or links that appear too small or too close together for a human finger to tap accurately.
5.  **Log Results**: For each breakpoint, record PASS or FAIL and a brief description of any layout issues found.

## Final Reporting
1. Compile the results for all breakpoints into a Markdown table.
2. Output the report, highlighting which specific resolution (`375px`, `768px`, etc.) broke the layout.

## 🛟 Recovery Strategy
- **Cannot Resize Window**: If macOS prevents resizing the window below a certain minimum width (some apps enforce a min-width of ~500px), you MUST use Method A (Browser DevTools Device Emulation) instead of System Level window resizing.
