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
This SOP defines the robust procedure for authenticating into standard web applications via visual interaction, bypassing traditional selenium scripting issues like dynamic element IDs or hidden iframes.

## Setup & Preconditions
1.  **Locate Credentials**: Ensure you have access to the required credentials (username/email, password). Check the `workspace_clipboard` or ask the user if they are not provided initially. Ensure you do not expose passwords in plaintext logs.
2.  **Navigate to Login**: If a `url` is provided, use the `browser/mac/navigate_and_search` SOP to open the page. Otherwise, search for the `app_name` login page.

## Phase 1: Establish Baseline
1.  **Analyze Page**: Wait 3 seconds for the page to fully load. Take a screenshot and analyze it (`analyze_image`).
2.  **Identify Form Type**:
    *   **Single-Step**: Username and Password fields are on the same screen along with a Submit/Sign In button.
    *   **Multi-Step (SSO style)**: A "Continue with Email" or similar workflow requiring inserting Username first, clicking Next, then Password.
    *   **OAuth**: "Login with Google/GitHub/etc." buttons.

## Phase 2: Execution (Single-Step Example)
1.  **Locate Username**: Identify the input field for the Username/Email.
2.  **Input Username**: Click the field. Wait 0.5s. Use the `keyboard` tool to type the username.
3.  **Locate Password**: Identify the input field for the Password.
4.  **Input Password**: Click the field. Wait 0.5s. Type the password.
5.  **Submit**: Click the "Sign In" or "Log In" button. Alternatively, press `Enter` while focused on the password field.

## Phase 3: Verification & Handling Mfa
1.  **Wait for Transition**: Wait 3-5 seconds for network requests to complete.
2.  **Verify New State**: Take a new screenshot. Call `verify_ui_state`.
    *   **Success**: The user avatar, dashboard, or "Log Out" button is visible.
    *   **Failure (Invalid Credentials)**: Look for red error text (e.g., "Invalid username or password").
    *   **MFA / Verification**: Look for prompts like "Enter code sent to..." or "Two-Factor Authentication".
3.  **Handle MFA (If Required)**:
    *   If a code is requested via email/SMS, you must pause the current login flow.
    *   If you have access to the user's email client (e.g., via `os/macos`), open it, wait for the new email, extract the code, and return to the browser.
    *   If you cannot access the code autonomously, you MUST call `request_human_input` and ask the user to provide the code.

## 🛟 Recovery Strategy
- **Captcha Encountered**: If a slider, puzzle, or reCAPTCHA appears, immediately transition to the `browser/mac/bypass_captcha_login` SOP. Do NOT attempt to brute-force text inputs if a captcha is present.
- **Hidden Password Manager**: If a system password manager (like 1Password or iCloud Keychain) covers the input fields, click an empty area of the page to dismiss the popup before proceeding.
