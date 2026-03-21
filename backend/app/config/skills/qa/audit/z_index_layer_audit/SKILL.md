---
name: Z-Index Layer Audit (QA)
description: Identifying overlapping element bugs (dropdowns hidden by videos, buttons buried under overlays) via visual analysis.
namespace: qa/audit
trigger_patterns:
  - "audit the UI layering for \\{page_name\\}"
  - "check for z-index issues"
  - "can you see the dropdown menu over the video?"
parameters:
  page_name:
    type: string
    description: Name/URL of the page.
---

# 🧠 Expert Guide (心法)
Finds "impossible to click" UI bugs caused by CSS stacking context errors.

## Execution
1. **Navigate**: Open `page_name`.
2. **Trigger Overlap**: Locate an element that spawns a floating layer (hover a dropdown, open a modal).
3. **Visual Audit**:
   - Use `analyze_image` specifically focused on the edges of the floating layer.
   - **Check**: Is the layer cut off by the container? Is it rendering *behind* another element (like a sticky header or a YouTube iframe)?
4. **Verification**: Try to click a button *inside* the floating layer. If the click lands on a background element instead, you have a Z-Index failure.

## 🛟 Recovery Strategy
- **Transparency**: If an overlay is semi-transparent, ensure the VLM doesn't misidentify it as "hidden". Focus on the clickability of child elements.
