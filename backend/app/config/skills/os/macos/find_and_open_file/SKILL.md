---
name: Find and Open File (macOS)
description: Locate and open specific files or applications using macOS Spotlight or Finder via GUI, verifying success via window title.
namespace: os/macos
trigger_patterns:
  - "open file \\{filename\\}"
  - "find and open \\{filename\\}"
  - "search for \\{filename\\} and open it"
  - "launch \\{app_name\\}"
parameters:
  filename:
    type: string
    description: The name of the file or application to find and open.
    required: true
---

# 🧠 Expert Guide (心法)
This SOP dictates how to reliably open local files or applications when bash or `open` commands are unavailable or fail. You must act as a visual user interacting with macOS.

## Setup & Preconditions
1. You must be on the macro macOS desktop level (`namespace_context: os/macos`).

## Phase 1: Search Execution
1.  **Invoke Spotlight**: EITHER click the magnifying glass in the top right menu bar, OR execute a `keyboard` action pushing `Cmd+Space`.
2.  **Input Query**: Type the exact `filename` into the Spotlight search bar.
3.  **Wait for Index**: Wait 1-2 seconds for Spotlight to display search results.
4.  **Verify UI State**: Call `verify_ui_state` to ensure the Spotlight window is visible and populated.

## Phase 2: Selection
1.  **Identify Top Hit**: Use `analyze_image` (or Atlas if available) to locate the first result matching the `filename`.
2.  **Execute Open**: EITHER hit the `Enter` key, OR click the highlighted Top Hit result.

## Phase 3: Verification (Critical)
1.  Wait 2-3 seconds for the application to launch or file to render.
2.  Use `verify_ui_state` to inspect the newly appeared active window.
3.  Check if the title or contents match the targeted `filename`.
4.  If the file opened in a background window, click its icon in the Dock to bring it to focus.

## 🛟 Recovery Strategy
- **Spotlight Missed**: If Spotlight fails to find the file, open Finder (click the smiley face icon in the Dock), click the Search bar (top right), type the `filename`, and look for results under "This Mac".
- **Wrong File Opened**: If the wrong file opens, immediately execute `Cmd+Q` to quit the app or `Cmd+W` to close the window, and retry Phase 1 with a more specific query.
