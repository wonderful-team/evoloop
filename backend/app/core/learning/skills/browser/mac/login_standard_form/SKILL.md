---
name: Standardized Form Login (Browser)
description: Handling multi-step login flows, waiting for DOM/Network stability between page transitions, and handling verification emails/texts.
namespace: browser/mac
trigger_patterns:
  - "log in to \\{app_name\\}"
  - "authenticate on \\{url\\}"
  - "sign into my \\{app_name\\} account"
parameters:
  app_name:
    type: string
    description: Optional target application or website.
  url:
    type: string
    description: Optional URL of the login page.
---

# 🧠 Expert Guide (心法)
This SOP defines the robust procedure for authenticating into standard web applications via `browser_control`, leveraging DOM selectors for precision and using visual analysis only as a fallback.

## Setup & Preconditions
1.  **Locate Credentials**: Ensure credentials (username/email, password) are handled securely.
2.  **Navigate to Login**: Use `browser_control(action="navigate", url=url)` to reach the login page.

## Phase 1: Establish Baseline
1.  **Analyze DOM**: Use `browser_control(action="get_html")` or `browser_control(action="screenshot")` (with OCR) to identify input field selectors.
2.  **Identify Form Type**:
    *   **Single-Step**: `input[type="text"]`, `input[type="password"]`, and a submit button are present.
    *   **Multi-Step**: Only the identifier field is visible initially.

## Phase 2: Execution (DOM-First)
1.  **Input Identifier**:
    *   Use `browser_control(action="type_text", selector="input[name='login'], #username, ...", text=username)`.
2.  **Transition (If Multi-Step)**:
    *   Click "Next" or press Enter. Wait for the password field to appear via `browser_control(action="wait_for", selector="input[type='password']")`.
3.  **Input Password**:
    *   Use `browser_control(action="type_text", selector="input[type='password']", text=password)`.
4.  **Submit**:
    *   Use `browser_control(action="click", selector="button[type='submit']")` or `browser_control(action="key_press", key="Enter")`.

## Phase 3: Verification & Handling Mfa
1.  **Wait for Transition**: `browser_control`'s `network_wait` can be used to monitor for dashboard API calls.
2.  **Verify New State**: Use `browser_control(action="screenshot")` to confirm successful login (e.g., presence of "Logout" button).
3.  **Handle MFA**: If prompted, request human input or access the MFA source via appropriate tools.

## 🛟 Recovery Strategy
- **Captcha Encountered**: Transition to the `browser/mac/bypass_captcha_login` SOP.
- **Selector Change**: If fixed selectors fail, use `browser_control(action="click", x=..., y=...)` using coordinates from the OCR result.
- **Hidden Password Manager**: Click a neutral area of the page if a system popup obscures the UI.
