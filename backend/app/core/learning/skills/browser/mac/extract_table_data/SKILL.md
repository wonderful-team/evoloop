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

# Extract Table Data

This SOP dictates how to reliably extract structured data (tables, grids, lists) using `browser_control`.

## 🎯 Core Principles

1.  **Direct Localization**: Use `find_element` with selectors like `table, .grid, [role='grid']` to identify the data source.
2.  **High-Speed Extraction**:
    *   Prefer `run_js` for batch row fetching (e.g., `return Array.from(document.querySelectorAll('tr')).map(r => r.innerText)`).
    *   Fallback to `get_text` if the DOM is too complex or obfuscated.
3.  **Navigation Strategy**:
    *   **Paginated**: Click the "Next" button.
    *   **Infinite Scroll**: Use `scroll(direction="down", amount=800)`.
4.  **State Verification**: After each extraction cycle, use `network_wait` or `wait_for` to ensure new data is rendered before repeating.

## 🛠 Recovery Strategy
- **Lazy Loading**: Use incremental scrolls (e.g., 200px) to trigger data loading events.
- **Shadow-DOM**: Use `/deep/` selectors or screenshot plus OCR if the structure is inaccessible.
