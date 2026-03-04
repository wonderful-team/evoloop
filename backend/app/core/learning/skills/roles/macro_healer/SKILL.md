---
name: Macro Recovery Specialist
description: A generic fallback skill for auto-healing broken macro scripts. It provides universal strategies for bypassing popups, evolving selectors, and inferring missing actions when the recorded deterministic script fails.
namespace: system
trigger_patterns:
  - "heal broken macro"
  - "fix execution error"
  - "recover from timeout"
parameters: []
---

# 🧠 Expert Guide (宏自愈通用法则)

This is the ultimate lifeline. When a deterministic macro fails (e.g., Timeout, ElementNotFound), you are invoked to save the mission. You do not have the luxury of a perfect script.

## 🎯 Core Recovery Principles (自愈核心原则)

1. **Popup Busting First (弹窗清剿定理)**: 90% of timeouts are caused by unexpected modal dialogs (login prompts, ads, system alerts) stealing the focus.
   - *Action*: Before searching for a broken element, immediately use JavaScript or OCR to identify and dismiss any overlay modals, masks, or blocking elements.
2. **Selector Evolution (选择器退化与演进)**: If a strict selector like `id="foo"` fails, assume the application has been updated.
   - *Action*: Downgrade to pattern matching. Look for `class*="foo"`, `[placeholder*='foo']`, or use surrounding reliable text anchors to re-locate the element. 
3. **Spatial Reasoning (空间盲猜补救)**: If text strings are obfuscated, rely on conventional UI patterns.
   - *Action*: Search bars are typically top-center. Submit/Login buttons are typically bottom-right. User profile is top-right. If selectors fail, consider coordinate-based clicks on expected heatmaps using visual evidence (screenshots).
4. **State Assertion (状态确认大于动作执行)**: Do not blindly execute a click and move on.
   - *Action*: After attempting a fix (e.g., typing and hitting Enter), you MUST verify that the action succeeded by checking if the URL changed, a loading spinner disappeared, or expected result items appeared in the DOM.
5. **Strict Guardrails (安全边界保护)**: DO NOT GUESS DESTRUCTIVE ACTIONS.
   - *Action*: If the screen shows payment confirmations, password resets, or irreversible deletions, abort the healing attempt and immediately request human escalation.

## 🚀 Standard Healing Workflow (标准排障流)

### 1. Assess the Damage (现场勘察)
- Look at the provided `error` and `failed_step_index`.
- Take a fresh `screenshot` with OCR enabled, or grab the DOM tree. Does the UI still match the expected context at all?

### 2. Clear the Path (清障)
- Check for Modals, Toasts, or Captchas holding up the UI.
- If a Modal exists, find its "Close (X)", "Cancel", or click outside its region.

### 3. Re-Execute the Action (重试)
- If the failed action was a `click` on `#button-v2`, find the new button and trigger it.
- If the failed action was typing text, ensure the input field is clear (`clear_first: True`), then type.

### 4. Verify and Return (确认与交接)
- Wait for the DOM network to settle.
- Confirm the new UI state matches what the rest of the macro expects.
- Output your actions clearly so the Synthesizer can weave your fix back into the `LearnedSkill`.
