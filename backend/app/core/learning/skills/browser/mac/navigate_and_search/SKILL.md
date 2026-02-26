---
name: browser_navigate_and_search
description: Standard procedure for navigating to a URL or searching in Chrome/Safari.
namespace: browser/mac
trigger_patterns:
  - "Go to {{url}}"
  - "Search for {{query}} in browser"
parameters:
  - name: url
    type: string
    description: Full URL or domain name
    required: false
  - name: query
    type: string
    description: Search query
    required: false
preconditions:
  - "Browser (Safari or Chrome) is open"
---

# Expert Skill Guide: Browser Navigation & Search

## 1. Mental Model
Prefer `browser_control` for navigation as it interacts directly with the browser's engine, handling network events and loading states more reliably than coordinate-based or keyboard-simulated interaction.

## 2. Contextual Anchors
- **API Mode**: `browser_control` is active (CDP or Auto-Launch).
- **Execution State**: Browser is ready to receive navigation commands.

## 3. Strategic Guidance
- **Phase 1 (Navigation)**: If a `url` is provided, use `browser_control(action="navigate", url=url)`. This automatically waits for the page to reach `networkidle` state.
- **Phase 2 (Searching)**: If a `query` is provided (and no URL or just a search engine URL):
    1. Navigate to the search engine (e.g., `google.com`).
    2. Use `browser_control(action="type_text", selector="textarea[name='q']", text=query)` (or appropriate search selector).
    3. Use `browser_control(action="key_press", key="Enter")`.
- **Phase 3 (Perception)**: Use `browser_control(action="screenshot")` to verify the search results page has loaded.

## 4. Recovery
- If `navigate` fails due to timeout, try manual reload via `browser_control(action="reload")`.
- If selectors fail, fall back to `browser_control(action="click", x=..., y=...)` using coordinates from the OCR result of a previous screenshot.
