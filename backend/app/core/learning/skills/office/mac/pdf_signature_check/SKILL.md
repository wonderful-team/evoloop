---
name: PDF Signature Check (macOS)
description: Verifying the presence of red physical/digital stamps or signatures in specific PDF regions.
namespace: office/mac
trigger_patterns:
  - "check if the PDF \\{filename\\} is signed"
  - "verify signature on page \\{page_number\\}"
  - "look for the red stamp"
parameters:
  filename:
    type: string
    description: Name of the PDF file.
  page_number:
    type: integer
    description: "The page to check. Default: 1."
---

# 🧠 Expert Guide (心法)
This SOP defines the visual audit protocol for verifying signatures and stamps on PDF documents (contracts, invoices).

## Execution
1. **Open PDF**: Launch Preview or Adobe Reader with `filename`.
2. **Navigate**: Scroll to `page_number`.
3. **Visual Audit**:
   - Capture a high-resolution screenshot of the bottom-right or "Signature" block.
   - Use `analyze_image` to look for **Chromatic Contrast**: Specifically identify circular or square "Red" or "Blue" patterns that contrast with black text.
   - Identify the presence of "Handwritten" script textures that differ from standard typeface.
4. **Conclusion**: If a stamp/signature is found, verify its location relative to the "Seal" or "Signature" label.

## 🛟 Recovery Strategy
- **Low Resolution**: If the signature is blurry, use `Cmd + Plus` to zoom in before capturing the final screenshot for VLM analysis.
