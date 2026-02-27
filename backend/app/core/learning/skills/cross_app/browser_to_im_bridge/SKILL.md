---
name: Browser to IM Bridge (Cross-App)
description: Scraping a browser alert/summary and immediately forwarding it to a contact in an IM application (e.g., WeChat, Lark, Slack).
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
The ultimate "Assistant" SOP for bridging data siloes using high-precision browser and OS tools.

## Execution
1. **Scrape Source**:
    *   Navigate to `url` via `browser_control(action="navigate")`.
    *   Capture critical data using `browser_control(action="get_text", selector="...")` or `browser_control(action="screenshot")` with OCR.
2. **Switch Context**: Use `desktop_control(action="open_app", app_name=im_app)` to bring the IM app to the foreground.
3. **Find Contact**:
    - Locate the Search/Filter bar in the IM app.
    - If the app uses a **Custom UI (e.g., WeChat)**, use `desktop_control(action="screenshot", ocr=True)` to find the search bar coordinates.
    - Type `contact_name` and Press `Enter`.
4. **Compose & Send**:
    - Type a concise summary: "Found alert on [URL]: [Captured Text]."
    - If a screenshot was taken, use `Cmd+V` (the tool ensures it's in the clipboard) or drag-and-drop.
    - Press `Enter` to send.

## 🛟 Recovery Strategy
- **Search Failed**: If multiple contacts match `contact_name`, ask the user for clarification.
- **Privacy Barrier**: If the IM app requires a login/QR, call `request_human_input`.
