---
name: Browser to IM Bridge (Cross-App)
description: Scraping a browser alert/summary and immediately forwarding it to a contact in WeChat, Lark, or Slack.
namespace: cross_app
trigger_patterns:
  - "forward the status of \\{url\\} to \\{contact_name\\}"
  - "alert \\{contact_name\\} about the error on \\{app_name\\}"
  - "share this screenshot on Slack"
parameters:
  url:
    type: string
    description: URL to scrape for info.
  contact_name:
    type: string
    description: The person or group to send the message to.
    required: true
  im_app:
    type: string
    description: "Target app (WeChat, Lark, Slack). Default: WeChat."
---

# 🧠 Expert Guide (心法)
The ultimate "Assistant" SOP for bridging data siloes.

## Execution
1. **Scrape Source**: Navigate to `url`. Capture the critical failure/status message via `desktop_control(action="screenshot")` + OCR.
2. **Switch Context**: Use `desktop_control(action="open_app", app_name=im_app)`.
3. **Find Contact**:
   - Locate the Search/Filter bar in the IM app.
   - Type `contact_name` and Press `Enter`.
4. **Compose & Send**:
   - Type a concise summary: "Found alert on [URL]: [Captured Text]."
   - Paste the screenshot (`Cmd+V` if screenshot was taken to clipboard, otherwise drag from Desktop).
   - Press `Enter` to send.

## 🛟 Recovery Strategy
- **Search Failed**: If multiple contacts match `contact_name`, pick the one with the closest match or ask the user for clarification.
- **Privacy Barrier**: If the IM app requires a login or QR code, immediately call `request_human_input`.
