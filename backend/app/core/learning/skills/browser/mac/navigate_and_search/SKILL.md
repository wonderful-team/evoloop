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

# Browser Navigation & Search

This SOP outlines the protocol for efficient page navigation or keyword searching.

## 🎯 Core Principles

1.  **Engine Priority**: Always prefer `browser_control(action="navigate")`. It interacts directly with the browser engine, handling network events and loading states more reliably than simulating keyboard input.
2.  **Precise Searching**:
    *   Navigate directly to the target search engine (e.g., `google.com`).
    *   Use `type_text` with precise selectors (e.g., `[name='q']`) for your query.
    *   Submit via `key_press("Enter")`.
3.  **State Verification**: Use `screenshot` or `visual_perception` to confirm that the results page has fully loaded.
4.  **Recovery**:
    *   If `navigate` timeouts, attempt a `reload`.
    *   If selectors fail, fallback to coordinate-based `click` using OCR spatial data from a previous screenshot.
