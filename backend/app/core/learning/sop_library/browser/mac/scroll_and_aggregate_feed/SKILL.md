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
This SOP defines the optimal strategy for interacting with infinite-scroll feeds. These interfaces are notoriously difficult for automated scripts because they reuse DOM elements and lazy-load data. You must rely on visual parsing.

## Setup & Preconditions
1. Ensure the browser is open and focused on the target feed (`platform`).
2. Establish a `seen_posts` (List or Set) in your memory or `workspace_clipboard` to prevent deduplication errors.

## Phase 1: Establish Baseline
1.  **Analyze View**: Use `take_screenshot` of the current viewport. Identify individual "posts", "cards", or "tweets".
2.  **Define End Condition**: Determine what signifies the "end of the feed" (e.g., a "No more posts" message, or no new content loading after 3 seconds).

## Phase 2: Execution Loop (Scroll & Extract)
This loop is critical to prevent infinite recursion and duplicated content.
1.  **Take Snapshot**: Use `take_screenshot`.
2.  **Extract Post Data**: Use the VLM (`analyze_image`) to transcribe all completely visible posts in the current snapshot into structured JSON.
3.  **Filter & De-duplicate**:
    *   Iterate through the extracted posts.
    *   If a `keyword` is provided, discard posts that do not contain it.
    *   Compare the remaining posts against your `seen_posts` list. Add only novel posts.
4.  **Identify Overlap Marker**: Identify the content of the *last completely visible post* in the current snapshot.
5.  **Execute Scroll**: Execute a `keyboard` action: `Page Down`. Do NOT use `Spacebar` as it might scroll multiple items out of view.
6.  **Verify New State**: Wait 1-2 seconds for lazy-loading. Call `verify_ui_state` to confirm the viewport changed and the overlap marker has moved UP the screen.
7.  **Loop Tracking**: Increment your scroll counter. If `max_scrolls` is reached, BREAK the loop.

## 🛟 Recovery Strategy
- **Video Autoplay Distraction**: If a video automatically plays or expands and breaks your visual parsing layout, use the `keyboard` tool to press `Escape` or `M` (mute) and attempt to scroll past it quickly.
- **Login Modal Blocks Feed**: Platforms often throw a "Sign in to see more" modal after 3-4 scrolls. You MUST use the `browser/mac/login_standard_form` SOP to clear the modal, or locate and click the "Not Now / X" button before continuing the scroll loop.
