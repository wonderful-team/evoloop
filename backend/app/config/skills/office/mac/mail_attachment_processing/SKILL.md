---
name: Mail Attachment Processing (macOS)
description: Scanning Mail.app to download and categorize attachments into Finder based on keywords.
namespace: office/mac
trigger_patterns:
  - "process attachments from my emails"
  - "download invoices from Apple Mail"
  - "sort my email attachments"
parameters:
  keyword:
    type: string
    description: Keyword to search in email subjects or bodies.
---

# 🧠 Expert Guide (心法)
Automates the workflow of harvesting data from the macOS native Mail.app.

## Execution
1. **Focus Mail**: Open and focus "Mail" application.
2. **Search**: Click the search box (top right) and enter `keyword`.
3. **Select Message**: Click the most recent unread email in the results.
4. **Identify Attachment**: Look for the paperclip icon or a block in the body representing a file.
5. **Download**: Right-click the attachment -> "Save Attachment...". In the dialog, type the target directory name and hit Enter.
6. **Verify**: Use `execute_command` `ls` to ensure the file now exists in the local directory.

## 🛟 Recovery Strategy
- **Mail Not Synced**: If no emails appear, click the "Get Mail" icon (top left).
- **Multiple Attachments**: If the email has a "Save All" option, use it to batch process.
