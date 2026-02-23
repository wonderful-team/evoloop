---
name: Skeleton Screen Verification (QA)
description: Capturing mid-render states to ensure skeleton screens or loading spinners are displayed during network latency.
namespace: qa/audit
trigger_patterns:
  - "verify the loading state for \\{url\\}"
  - "check if the skeleton screen appears"
  - "audit page load experience"
parameters:
  url:
    type: string
    description: URL of the page to test.
---

# 🧠 Expert Guide (心法)
Tests perceived performance by catching the application "in the act" of loading.

## Execution
1. **Prepare Browser**: Clear browser cache to ensure a "cold" start.
2. **Execute Navigation**: Enter the `url`.
3. **High-Frequency Snapshot**:
   - Immediately after hitting Enter, take 3 screenshots in rapid succession (0.5s intervals).
4. **VLM Analysis**:
   - Use `analyze_image` on the *first* and *second* snapshots.
   - Specifically look for grey placeholders, pulsing boxes, or circular spinners in the area where content eventually appears.
5. **Score**: If snapshots 1 or 2 show white blank screens instead of skeletons, mark as "UX FAIL: White Flash detected".

## 🛟 Recovery Strategy
- **Load too fast**: If the page loads too fast to capture, use Chrome DevTools "Network" tab to set "Slow 3G" throttling and retry.
