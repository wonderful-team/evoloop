---
name: Scroll and Aggregate Feed (Browser)
description: Paginating through infinite scroll platforms (Twitter, Reddit, Instagram) safely, avoiding duplicate entries and excessive DOM memory usage.
namespace: browser/mac
trigger_patterns:
  - "read the feed on \\{platform\\}"
  - "scroll and collect posts containing \\{keyword\\}"
  - "what are the latest posts on \\{platform\\}"
  - "aggregate timelines"
parameters:
  platform:
    type: string
    description: Optional target social media or news platform.
  keyword:
    type: string
    description: Optional filter keyword. Only collect posts containing this string.
  max_scrolls:
    type: integer
    description: "Optional. The maximum number of paginations to perform before stopping. Default: 5."
---

# 🧠 Expert Guide (心法)
This SOP defines the optimal strategy for interacting with infinite-scroll feeds using `browser_control`, which provides direct scrolling and DOM monitoring.

## Setup & Preconditions
1. Ensure the browser is open and focused on the target feed (`platform`).

## Phase 1: Establish Baseline
1.  **Analyze View**: Use `browser_control(action="screenshot")` or `browser_control(action="get_links")` to identify individual post containers.
2.  **Define End Condition**: Determine if the feed has a "No more posts" indicator or if `browser_control(action="scroll")` stops increasing the page height.

## Phase 2: Execution Loop (Scroll & Extract)
1.  **Take Snapshot**: Use `browser_control(action="screenshot")` with OCR.
2.  **Extract Data**:
    *   Use `browser_control(action="get_text", selector=".post-content")` or similar to pull novel data.
    *   Alternatively, use `browser_control(action="run_js")` to scrape multiple posts into JSON directly.
3.  **Execute Scroll**:
    *   Use `browser_control(action="scroll", direction="down", amount=1200)`.
4.  **Verify New State**:
    *   Use `browser_control(action="wait_for", state="attached")` or `network_wait` for lazy-loaded assets.
5.  **Loop Tracking**: Increment scroll counter. Break if `max_scrolls` is reached or no new posts are found.

## 🛟 Recovery Strategy
- **Video Autoplay**: If a video disrupts the flow, ignore it and continue scrolling or use `browser_control(action="key_press", key="Escape")`.
- **Login Modals**: If a modal appears, use the `browser/mac/login_standard_form` SOP or `browser_control(action="click", selector=".close-button")`.
