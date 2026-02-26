---
name: Extract Table Data (Browser)
description: Standardized workflow for scrolling and visually extracting large data tables without missing rows.
namespace: browser/mac
trigger_patterns:
  - "extract the table from \\{url\\}"
  - "get all the rows from \\{url\\}"
  - "download the grid data containing \\{target_data\\}"
  - "scrape tabular data on \\{app_name\\}"
parameters:
  url:
    type: string
    description: Optional URL if starting from a new tab.
  target_data:
    type: string
    description: Optional specific column or row data to look for.
  app_name:
    type: string
    description: Optional target application.
---

# 🧠 Expert Guide (心法)
This SOP dictates how to reliably extract structured data (tables, grids, lists) using `browser_control`, which offers direct access to the page structure and precise scrolling.

## Setup & Preconditions
1. Ensure the browser is open and navigated to the target page.

## Phase 1: Establish Baseline
1.  **Locate Table**: Use `browser_control(action="find_element", selector="table, .grid, [role='grid']")`.
2.  **Define Strategy**: Identify if data is paginated or infinite-scrolling.

## Phase 2: Execution Loop (Scroll & Extract)
1.  **Extract Data**:
    *   Use `browser_control(action="get_text", selector="...")` to extract visible row text.
    *   Alternatively, use `browser_control(action="run_js", script="return Array.from(document.querySelectorAll('tr')).map(r => r.innerText)")` for high-speed batch extraction.
2.  **Execute Scroll/Next**:
    *   **Paginated**: `browser_control(action="click", selector=".next-button")`.
    *   **Infinite Scroll**: `browser_control(action="scroll", direction="down", amount=800)`.
3.  **Wait for Load**: Use `browser_control(action="network_wait")` or `browser_control(action="wait_for", state="attached")` for new rows.
4.  **Loop**: Repeat until no new data is detected or the end of the list is reached.

## 🛟 Recovery Strategy
- **Lazy Loading**: Use `browser_control(action="scroll", direction="down", amount=200)` incrementally to trigger loading events.
- **Dynamic Content**: Use `browser_control(action="screenshot")` with OCR if the DOM structure is highly obfuscated or shadow-DOM wrapped.
