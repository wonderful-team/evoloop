---
name: Accessibility Tab Navigation Audit (QA)
description: Testing keyboard-only (Tab) navigation focusing on focus-ring visibility and tab traps.
namespace: qa/testing
trigger_patterns:
  - "run an accessibility audit on \\{url\\}"
  - "test tab navigation for \\{page_name\\}"
  - "verify keyboard accessibility"
  - "check if a11y focus rings are visible"
parameters:
  url:
    type: string
    description: Optional target URL.
  page_name:
    type: string
    description: Optional target page to audit.
---

# 🧠 Expert Guide (心法)
This SOP defines the rigorous process of testing a web page purely via keyboard navigation. It ensures visually impaired users or power users can interact with all form elements without a mouse.

## Setup & Preconditions
1. Navigate to the target `url` or `page_name`.
2. Ensure the page has fully loaded (wait 2-3 seconds).
3. **CRITICAL**: From this point forward, you are FORBIDDEN from using the `mouse_click`, `mouse_drag`, or `mouse_scroll` tools until the audit is complete.

## Execution Loop (The Tab Traversal)
Execute the following loop iteratively. You must carefully track the visual state of the page.

1.  **Initial Focus**: Execute a `keyboard` action: `Tab`.
2.  **Visual Sweep & VLM Assertion**:
    *   Take a `desktop_control(action="screenshot")`.
    *   Use `analyze_image` to explicitly find the *Focus Ring* (an outline, underline, or highlight indicating the currently active element).
    *   **Pass**: A clear focus ring is visible around an interactive element (link, button, input).
    *   **Fail (Hidden Focus)**: No focus ring is visible anywhere on the page, meaning the user is "lost".
    *   **Fail (Tab Trap)**: The focus ring is trapped inside a modal or iframe and subsequent Tabs cannot escape it.
3.  **Action Iteration**: Press `Tab` again to move to the next semantic element. Repeat steps 2-3 at least 15 times to cover the main navigation and content area.
4.  **Interactive Elements (Optional)**: If you focus on a critical button (e.g., "Submit" or a dropdown menu), execute an `Enter` or `Spacebar` keypress to verify it can be activated via keyboard. Close any resulting modals using the `Escape` key before continuing the traversal.

## Final Reporting
1. Compile the results of the traversal into a Markdown table indicating the order of elements focused and any failures.
2. If a "Hidden Focus" or "Tab Trap" error occurred, output the exact sequence of Tabs that led to the dead end.

## 🛟 Recovery Strategy
- **Stuck in the Browser URL Bar**: Sometimes the first `Tab` highlights the browser's address bar or extension icons instead of the webpage DOM. You must press `Tab` 2-3 more times until you see an element *inside* the webpage content highlighted. If the first 5 Tabs yield no internal focus rings, note this as an extreme accessibility failure.
