---
name: Notion Database Enrichment (Browser)
description: Using GUI to update complex Notion database properties (Selects, Multi-selects, Dates).
namespace: collab/browser
trigger_patterns:
  - "update the Notion database for \\{page_title\\}"
  - "change the status of \\{item_name\\} in Notion"
  - "tag the notion item \\{item_name\\} as \\{tag\\}"
parameters:
  item_name:
    type: string
    description: The name/title of the database row to update.
    required: true
  property_name:
    type: string
    description: The column name to update (e.g., Status, Priority, Tags).
  target_value:
    type: string
    description: The new value to select or type.
---

# 🧠 Expert Guide (心法)
Notion's API is often restricted or complex for fine-grained property updates. This SOP guides the Agent through visual manipulation of the Notion UI.

## Execution
1. **Navigate**: Use `browser/mac/navigate_and_search` to open your workspace.
2. **Locate Row**: Search for `item_name` in the database view.
3. **Open Cell**: Locate the intersection of `item_name` and `property_name`. Click the cell.
4. **Select Value**:
   - **For Select/Multi-select**: A dropdown will appear. Type `target_value` in the internal search box of the dropdown, then press `Enter` or click the matching option.
   - **For Date**: A calendar widget will appear. Type the date manually or use visual cues to click the day.
5. **Verify**: Wait 1s. Ensure the cell now displays `target_value` without any error tooltips.

## 🛟 Recovery Strategy
- **Cell Not Editable**: If you cannot click the cell, ensure you are not in "Locked" mode (check the top right "..." menu).
- **Search Failed**: If the dropdown doesn't find `target_value`, double-check spelling or ask the user if the option needs to be created first.
