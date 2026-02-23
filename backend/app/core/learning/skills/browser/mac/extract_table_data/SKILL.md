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
This SOP dictates how to reliably extract structured data (tables, grids, lists) from web pages when DOM parsing (BeautifulSoup) or API calls fail, relying purely on visual scrolling and OCR/VLM extraction.

## Setup & Preconditions
1. Ensure the browser is open and focused on the target page.
2. Ensure the table header is clearly visible.

## Phase 1: Establish Baseline
1.  **Locate Table**: Use `analyze_image` to find the main data table. Identify the column headers.
2.  **Define Pagination/Scroll**: Determine if the table uses discrete pagination (Page 1, 2, 3...) or infinite scrolling / "Load More" buttons.

## Phase 2: Execution Loop (Scroll & Extract)
This loop is critical to prevent data loss or duplication.
1.  **Take Snapshot**: Use `take_screenshot` of the current visible table view.
2.  **Extract Row Data**: Use the VLM to transcribe the visible rows into structured JSON or CSV format.
3.  **Identify Overlap Marker**: Identify the content of the *last completely visible row* in the current snapshot. This is your overlap marker.
4.  **Execute Scroll**:
    *   **Paginated**: Click the "Next Page" button.
    *   **Infinite Scroll**: Execute a `keyboard` action: `Page Down` (do NOT use `Spacebar` as it might scroll too far). Or, execute a `mouse_scroll` action downwards by roughly 80% viewport height.
5.  **Verify New State**: Call `verify_ui_state` to confirm the viewport changed.
6.  **De-duplicate**: In the new snapshot, find your overlap marker. Only extract rows *below* the marker to append to your dataset.
7.  **Loop**: Repeat steps 1-6 until the end is reached (no more pages, or the overlap marker remains at the bottom of the screen after a scroll attempt).

## 🛟 Recovery Strategy
- **Sticky Headers Blocking View**: If a sticky header or footer obscures the top/bottom table rows after scrolling, you must adjust your scroll amount (e.g., use smaller `mouse_scroll` increments instead of `Page Down`) or temporarily attempt to hide the sticky element via browser developer tools (if authorized).
- **Data Not Rendering Fast Enough (Lazy Loading)**: Wait 1-2 seconds between the scroll action and the next snapshot to allow lazy-loaded table rows to render fully.
