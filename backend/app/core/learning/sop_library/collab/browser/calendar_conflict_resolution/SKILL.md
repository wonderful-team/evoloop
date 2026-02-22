---
name: Calendar Conflict Resolution (Browser/macOS)
description: Identifying overlapping color blocks in Calendars and flagging/resolving them.
namespace: collab/browser
trigger_patterns:
  - "check my calendar for conflicts"
  - "scan my schedule for overlaps"
  - "are there any meeting conflicts today?"
parameters:
  date_target:
    type: string
    description: The date to check (e.g., today, tomorrow, 2026-03-01).
---

# 🧠 Expert Guide (心法)
Focuses on visual detection of schedule density.

## Execution
1. **Open Calendar**: Open Google Calendar (browser) or Apple Calendar (macOS).
2. **Set View**: Ensure view is set to "Day" or "Week".
3. **Visual Scan**:
   - Use `analyze_image` to look for **narrow or overlapping rectangles**. 
   - Identify regions where two or more event blocks share the same horizontal space (time slot).
4. **Flagging**: 
   - Extract the titles of the conflicting meetings.
   - Report the conflict to the user.

## 🛟 Recovery Strategy
- **Multiple Calendars**: Ensure the sidebar has the relevant calendars checked (Work, Personal, etc.).
- **Hidden Events**: If "All-day" events are collapsed, click the arrow to expand them.
