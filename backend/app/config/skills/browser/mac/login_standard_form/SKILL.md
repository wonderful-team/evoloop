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
2.  **Handle Entry Barriers** (Before Login):
    *   **Privacy Policy / Terms of Service**: Look for buttons like "同意", "Accept", "I Agree", "Continue". These MUST be clicked before accessing the login form.
    *   **Age Verification / GDPR**: Handle cookie consent banners by clicking "Accept All" or dismissing them.
    *   **Region Selection**: Some sites require selecting a country/region first.
3.  **Identify Form Type**:
    *   **Single-Step**: `input[type="text"]`, `input[type="password"]`, and a submit button are present.
    *   **Multi-Step**: Only the identifier field is visible initially.
    *   **Captcha-Protected**: Look for captcha widgets (滑块/拼图验证、数字验证码、图形验证码). If present, follow Phase 1.5 below.

### Phase 1.5: Handle Captcha (If Detected)
⚠️ **Do NOT proceed to login until captcha is solved or handled.**

**Detection Checklist:**
- Slider puzzle: Elements like `.slider`, `.drag`, `.puzzle`, 滑块
- Numeric captcha: 4-6 digit input fields labeled "验证码" (NOT SMS verification)
- Image captcha: "Click all images with...", "Select matching images"
- reCAPTCHA: "I'm not a robot" checkbox

**Handling Strategy:**
1. **Slider/Puzzle Captcha** (拖拽验证码):
   - **Detection**: Look for yidun (网易易盾), geetest (极验), or similar commercial captcha systems
   - **First Attempt - Browser Level**:
     - Use `browser_control(action="screenshot")` to capture the puzzle area
     - Use `analyze_image` to identify slider thumb position and target gap
     - Try: `browser_control(action="drag_drop", source_selector=".slider-thumb", target_selector=".slider-track-end")`
   - **⚠️ If Browser Level Fails** (infinite loop, iframe protection, complex anti-bot):
     - **SWITCH TO OS-Level Control**: Use `desktop_control` instead
     - Take screenshot: `desktop_control(action="screenshot")`
     - Use `analyze_image` to get exact coordinates of slider thumb and target position
     - Execute precise drag: `desktop_control(action="drag_drop", x=<thumb_x>, y=<thumb_y>, x2=<target_x>, y2=<thumb_y>)`
     - **Why**: `desktop_control` operates at OS level, bypassing iframe restrictions and anti-bot detection that `browser_control` cannot handle
   - **If still failing after 2 attempts**: Transition to `browser/mac/bypass_captcha_login` SOP

2. **Numeric/Image Captcha**:
   - Transition to `browser/mac/bypass_captcha_login` SOP immediately
   - These require VLM (Vision Language Model) analysis or human intervention

3. **reCAPTCHA Checkbox**:
   - Try clicking: `browser_control(action="click", selector=".recaptcha-checkbox-border")`
   - If challenged with images, transition to `browser/mac/bypass_captcha_login`

## Phase 2: Execution (DOM-First)
1.  **Input Identifier**:
    *   Use `browser_control(action="type_text", selector="input[name='login'], #username, ...", text=username)`.
2.  **Transition (If Multi-Step)**:
    *   Click "Next" or press Enter. Wait for the password field to appear via `browser_control(action="wait_for", selector="input[type='password']")`.
3.  **Input Password**:
    *   Use `browser_control(action="type_text", selector="input[type='password']", text=password)`.
4.  **Submit**:
    *   Use `browser_control(action="click", selector="button[type='submit']")` or `browser_control(action="key_press", key="Enter")`.

## Phase 3: Verification & Handling MFA

### 3.1 Detect MFA Type
After submitting credentials, analyze the page to identify the MFA mechanism:
- **SMS Code**: Input field labeled "验证码", "SMS Code", "Verification Code" with a "Send Code" button
- **Email Code**: Similar input with mention of email delivery
- **TOTP/Authenticator**: Input field for 6-digit code from authenticator app
- **None**: Direct redirect to dashboard (login successful)

### 3.2 SMS Verification Code (Cross-Device Workflow)
⚠️ **CRITICAL**: If SMS verification is required and an Android device is available, you MUST attempt auto-retrieval BEFORE asking the user.

**Step-by-Step:**

1. **Check Environment**: Verify `has_android` is true in your environment telemetry. If false, skip to human fallback.

2. **Record Timestamp & Trigger Code Sending**:
   ```python
   import time
   start_time_ms = int(time.time() * 1000)  # Record timestamp BEFORE clicking send
   ```
   - Click the "Send Code" / "获取验证码" button using `browser_control(action="click", selector="...")`
   - Wait 2-3 seconds for the SMS to be sent

3. **Auto-Retrieve from Phone** (Primary Strategy):
   ```
   Use mobile_control(action="read_sms", text="\\d{4,6}", timeout=30, after_timestamp=<start_time_ms>)
   ```
   - The `text` parameter is a regex pattern to match 4-6 digit codes
   - `timeout=30` means it will poll for up to 30 seconds
   - `after_timestamp` is CRITICAL - it ensures you only receive SMS sent AFTER the timestamp, ignoring old messages
   - **Polling Strategy**: The tool waits 3 seconds before first query (SMS takes time to arrive), then polls with intervals: 2s → 3s → 5s
   - On success, it returns the matched code(s) immediately
   - **⚠️ Timeout behavior**: If no matching SMS arrives within 30 seconds, the tool returns empty

4. **Handle Read SMS Result**:
   - **Success**: Code retrieved → Store with `stash_to_clipboard(content="<code>")` → Continue to step 5
   - **Timeout/Empty**: **This is NORMAL** — The SMS was likely sent to a different phone (not the one connected to the computer). Do NOT retry multiple times. Proceed directly to Human Fallback (step 6).

5. **Bridge and Complete** (if code was retrieved):
   - Input the code: `browser_control(action="type_text", selector="input[placeholder*='code'], input[name*='verify']", text="<code>")`
   - Click "Verify" / "Login" / "Submit" button

6. **Handle Rate Limiting / Frequency Errors**:
   - If the site displays "发送过于频繁" / "操作太频繁" / "请稍后再试" / "Too many attempts" / "Rate limited":
     - **Do NOT click "Send Code" again** — this will worsen the rate limit
     - The code may have already been sent in a previous attempt — ask the user to check their phone
     - Inform the user: `request_human_input(prompt="The site shows 'sending too frequent'. The verification code may have been sent earlier. Please check your SMS and provide the code:")`
     - If user hasn't received it, advise waiting 1-2 minutes before retrying

7. **Human Fallback** (Correct Behavior When):
   - ✅ **No Android device connected** (`has_android` is false or `list_devices` returns empty) — **COMMON CASE**. Simply ask the user for the code.
   - ✅ **`read_sms` timed out or returned empty** — **COMMON CASE**. The SMS was likely sent to the user's actual phone, not the connected device. This is expected behavior. Ask the user directly.
   - ✅ **Rate limiting triggered** — see step 6 above
   - ✅ The code is from a non-SMS source (e.g., voice call, email)
   - Then: `request_human_input(prompt="Please provide the SMS verification code:")`

### 3.3 Email Verification Code
If email verification is detected:
- Request human input OR
- If email client is accessible via automation tools, retrieve from there

### 3.4 TOTP/Authenticator Codes
- Always request human input for TOTP codes (cannot be auto-retrieved)

### 3.5 Final Verification
1. **Wait for Transition**: Use `browser_control`'s `network_wait` to monitor for dashboard API calls.
2. **Confirm Success**: Take a screenshot and verify presence of success indicators:
   - "Logout" button
   - User avatar/profile icon
   - Dashboard elements specific to the app
3. **Handle Failure**: If still on login page, check for error messages and retry or escalate.

## 🛟 Recovery Strategy
- **Captcha Encountered**: Transition to the `browser/mac/bypass_captcha_login` SOP.
- **Selector Change**: If fixed selectors fail, use `browser_control(action="click", x=..., y=...)` using coordinates from the OCR result.
- **Hidden Password Manager**: Click a neutral area of the page if a system popup obscures the UI.
