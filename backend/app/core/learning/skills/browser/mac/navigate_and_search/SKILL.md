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
Browsers are dynamic environments. Navigation should prioritize the Address Bar (`Cmd+L`) over clicking internal page elements which may shift.

## 2. Contextual Anchors
- **Visual Evidence**: The URL bar should contain the target domain.
- **AX Tree**: Look for `AXTextField` with role "address and search bar".

## 3. Strategic Guidance
- **Phase 1 (Targeting)**: Use `key_press(key="command+l")` to focus the address bar.
- **Phase 2 (Input)**: Type the URL or query and press ENTER.
- **Phase 3 (Observation)**: Use `analyze_image` to wait for the page to stop "spinning" (loading bar completion).

## 4. Recovery
- If the page loads a 404 or error, check network status.
- If the address bar isn't focused, click the top 10% of the window center.
