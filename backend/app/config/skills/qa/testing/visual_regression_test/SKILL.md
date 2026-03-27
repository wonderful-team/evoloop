---
name: Visual Regression Test (QA)
description: Comparing current UI states against a baseline description (colors, padding, truncations).
namespace: qa/testing
trigger_patterns:
  - "run a visual regression test on \\{url\\}"
  - "check if the UI is broken on \\{page_name\\}"
  - "verify styling for \\{component\\}"
  - "audit the visual design"
parameters:
  url:
    type: string
    description: Optional target URL.
  component:
    type: string
    description: Optional specific component to audit (e.g., 'header', 'checkout_button').
  baseline_criteria:
    type: string
    description: Optional text describing the expected styling (e.g., "The button should be bright green (#00FF00) and have 16px padding with no text truncation").
---

# 🧠 Expert Guide (心法)
This SOP defines how an Agent performs automated Visual QA, a traditionally brittle task for Selenium but a core strength for Vision-Language Models.

## Setup & Preconditions
1. Navigate to the target `url` or `page_name`.
2. Ensure the page has fully loaded (wait 2-3 seconds for fonts and images to stop shifting).
3. If `baseline_criteria` is not provided, you must ask for it or look in your `workspace_clipboard` for a "Design Spec".

## Phase 1: Baseline Capture
1.  **Take Screenshot**: Execute `desktop_control(action="screenshot")` of the entire viewport or the specific `component` area.
2.  **Define Assertions**: Parse the `baseline_criteria` into 3-5 distinct visual assertions. For example:
    *   *Assertion 1*: Button background color is green.
    *   *Assertion 2*: Text says "Buy Now".
    *   *Assertion 3*: Text is horizontally centered.
    *   *Assertion 4*: No UI clipping or overflow exists.

## Phase 2: Execution (VLM Audit)
1.  **Analyze Image**: Pass the screenshot and your list of assertions to the `analyze_image` tool.
2.  **Force Binary Output**: Command the VLM to return a strict PASS/FAIL matrix for each assertion, alongside a one-sentence justification.

## Phase 3: Reporting
1.  **Compile Matrix**: Aggregate the PASS/FAIL results into a markdown table.
2.  **Highlight Failures**: If any assertion FAILs, you MUST use the `execute_command` tool to draw a red bounding box around the failing component (using ImageMagick or similar, if a local reference image was saved) OR simply describe its `(x, y)` location clearly in the final QA Report.
3.  **Finalize**: Save the QA report to a local `.md` file or output it directly to the user conversation.

## 🛟 Recovery Strategy
- **False Positives (Dynamic Content)**: If an assertion fails because a carousel image changed or a user avatar is different, but the *layout* is correct, you should mark it as a "WARNING (Dynamic Content)" rather than a hard FAIL. Instruct the VLM to ignore specific bounding boxes if they contain known dynamic data (ads, rotating banners).
