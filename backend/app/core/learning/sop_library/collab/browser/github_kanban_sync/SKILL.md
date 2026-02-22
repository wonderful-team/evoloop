---
name: GitHub Kanban Sync (Browser)
description: Drag-and-dropping issue cards across GitHub Project Kanban columns (In Progress -> Review).
namespace: collab/browser
trigger_patterns:
  - "move issue \\{issue_id\\} to \\{target_column\\} on GitHub"
  - "update the kanban board for \\{project_name\\}"
  - "drag issue \\{issue_id\\} to done"
parameters:
  issue_id:
    type: string
    description: The ID or title of the issue card to move.
    required: true
  target_column:
    type: string
    description: The name of the destination column (e.g., Review, Done).
    required: true
---

# 🧠 Expert Guide (心法)
Automates project management hygiene by visually moving cards.

## Execution
1. **Navigate**: Open the GitHub Projects board URL.
2. **Find Card**: Locate the card matching `issue_id`.
3. **Find Destination**: Identify the top area of the `target_column`.
4. **Execute Drag**:
   - Use `mouse_drag` from the center of the `issue_id` card to the empty space in `target_column`.
   - **Verify**: Call `verify_ui_state` to ensure the card's `(x, y)` coordinate has shifted to the new column's bounding box.

## 🛟 Recovery Strategy
- **Card Not Found**: Use the board's internal search/filter bar to isolate the card first.
- **Drag Failed**: If the card snaps back, wait for the page to finish loading (yellow bar at the top) and retry once. If it fails again, use the card's "..." menu to manually select "Move to column...".
