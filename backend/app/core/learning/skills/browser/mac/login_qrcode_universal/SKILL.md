---
name: Universal QR Code Login/Authorization (Cross-App)
description: Generic cross-device workflow for QR code-based login or authorization across multiple platforms (WeChat, Taobao, Alipay, etc.).
namespace: browser/mac
trigger_patterns:
  - "log in to \\{app_name\\} with QR code"
  - "scan QR code to login"
  - "使用(微信|淘宝|支付宝)扫码登录"
  - "使用(微信|淘宝|支付宝)扫码授权"
  - "QR code login"
  - "扫码登录"
  - "扫码授权"
parameters:
  target_app:
    type: string
    description: The mobile app used for scanning (e.g., "WeChat", "Taobao", "Alipay", "DingTalk"). Detect from context if not specified.
  app_name:
    type: string
    description: The target application or website requiring login (e.g., "kimi.com", "notion", "知乎").
  url:
    type: string
    description: Optional URL of the login page.
---

# 🧠 Expert Guide (心法)
This SOP handles **QR Code-based Authentication** — a universal cross-device pattern used by:
- **WeChat** (微信登录/授权)
- **Taobao** (淘宝登录)
- **Alipay** (支付宝授权)
- **DingTalk** (钉钉登录)
- **Other OAuth providers**

**Cross-Device Architecture**:
- **Primary Device (Mac/PC)**: Displays QR code, monitors auth status
- **Secondary Device (Mobile)**: Scans QR, confirms authorization

**Three-Stage Universal Flow**:
1. **Display**: Browser shows QR code with expiry timer
2. **Scan**: Mobile app scans and processes the code
3. **Confirm**: User authorizes on mobile → Browser completes login

---

## Phase 1: Navigate and Display QR Code

1. **Navigate to Login Page**:
   - Use `browser_control(action="navigate", url=url)` if provided
   - Or click platform-specific login button:
     - "微信登录" / "Login with WeChat"
     - "淘宝登录" / "Login with Taobao"
     - "支付宝登录" / "Login with Alipay"
     - "扫码登录" / "QR Code Login"

2. **Verify QR Code Display**:
   - Screenshot: `browser_control(action="screenshot")`
   - Look for: QR image, countdown timer, refresh button
   - Common selectors: `img[src*="qr"]`, `.qrcode`, `.qr-code`, `[class*="qr"]`, `#qrcode`

3. **Check QR Validity**:
   - Most QR codes expire in 2-5 minutes
   - Look for countdown text (e.g., "120秒后过期")
   - If already expired, click "刷新" / "Refresh" / "换一张"

---

## Phase 2: Cross-Device Scan Attempt (MANDATORY CHECK)

⚠️ **CRITICAL**: Before asking the user for manual scan, you MUST check if an Android device is available for automation.

**Execution Rule**:
```
IF has_android == true:
    → MUST attempt Phase 2 automation first
    → Only fallback to Phase 3 if mobile scan fails after 15 seconds
ELSE:
    → Skip to Phase 3 (Human Fallback)
```

**How to check**:
- Check `has_android` in your environment telemetry
- Or call: `mobile_control(action="list_devices")` to verify connection

**DO NOT skip to Phase 3 without attempting Phase 2 if a device is connected.**

### 2.1 Determine Target App

From user context or QR page text, identify the scanning app:

| App | Package Name | QR Context Clues |
|-----|-------------|------------------|
| **WeChat** | `com.tencent.mm` | 微信图标, "微信扫码", green QR frame |
| **Taobao** | `com.taobao.taobao` | 淘宝图标, 橙色系, "手机淘宝扫码" |
| **Alipay** | `com.eg.android.AlipayGphone` | 支付宝图标, blue系, "支付宝扫码" |
| **DingTalk** | `com.alibaba.android.rimet` | 钉钉图标, blue系 |

### 2.2 Open Scanner on Mobile

```
mobile_control(action="open_app", text="<package_name>")
```
- Wait 3 seconds for app to load

**Navigate to Scanner by App**:

**WeChat (微信)**:
1. Tap **右上角 "+"** (top-right plus)
2. Tap "扫一扫" (Scan)
3. Camera opens

**Taobao (淘宝)**:
1. Tap **首页右上角相机/扫码图标** (top-right camera)
2. Or: "我的淘宝" → 右上角设置 → "扫一扫"

**Alipay (支付宝)**:
1. Tap **首页右上角 "+"** → "扫一扫"
2. Or: Home page → 顶部搜索栏旁的扫码图标

**Alternative if UI unclear**:
- Screenshot mobile with OCR to find "扫一扫", "扫码", "Scan" text
- Or use `analyze_image` to locate scanner icon

### 2.3 Attempt Auto-Scan

- Phone is USB-connected, likely near computer
- Camera activation is key - if pointed generally at screen, auto-scan may occur
- Wait 10-15 seconds

### 2.4 Check Mobile State

Screenshot: `mobile_control(action="screenshot")`

**Expected Post-Scan States**:

| App | Success Indicator | Action Needed |
|-----|------------------|---------------|
| **WeChat** | "确认登录" / "授权" page | Tap confirm button |
| **Taobao** | "确认登录" / 店铺/商品信息 | Tap "确认登录" |
| **Alipay** | "确认授权" / 服务授权页 | Tap "同意" / "确认" |

If still on scanner → Scan failed → Proceed to Phase 3

### 2.5 Confirm Authorization on Mobile

Common confirm button texts:
- "确认登录" / "确认授权" / "同意授权"
- "登录" / "授权" / "确认"
- "同意" / "Allow" / "Confirm"

```
mobile_control(action="click", element_name="确认登录")
# or scan for: "确认", "授权", "登录", "同意"
```

### 2.6 Monitor Browser State

After mobile confirmation, check browser immediately:
```
browser_control(action="screenshot")
```

**Expected Transitions**:
- QR area → "扫码成功" / "Scan successful" → Redirect
- Or: Direct redirect to logged-in dashboard

**If browser still shows QR after 5s**:
- User may have scanned with a **different device**
- Proceed to Phase 3, Scenario C

---

## Phase 3: Human-Mediated Fallback

**When to enter Phase 3**:
1. **No Android device connected** (`has_android` is false) — Jump directly here
2. **Phase 2 automation failed** — Mobile scan did not succeed after 15 seconds

### Scenario A: No Android Device Connected
**Detection**: `has_android` is false OR `list_devices` returns empty
**Action**: Proceed directly to manual instructions (no automation attempted)

### Scenario B: Auto-Scan Failed
**Detection**: Phase 2 attempted but mobile still shows scanner after 15 seconds
**Action**: Provide app-specific instructions for manual scan

### Manual Instructions (App-Specific):

**Generic Template**:
```
request_human_input(
    prompt="Please scan the QR code using {target_app} on your phone:\n"
           "1. Open {target_app} on your mobile device\n"
           "2. Find and tap the 'Scan' / '扫一扫' feature\n"
           "3. Point your camera at the QR code displayed in the browser\n"
           "4. When prompted on your phone, tap 'Confirm' / '登录' to authorize\n"
           "5. Let me know once you've completed the authorization"
)
```

**WeChat-Specific**:
```
"1. Open WeChat → Tap '+' in top-right → '扫一扫' (Scan)\n"
"2. Scan the QR code on your computer screen\n"
"3. Tap '确认登录' (Confirm Login) on your phone\n"
```

**Taobao-Specific**:
```
"1. Open Taobao app → Tap camera icon in top-right\n"
"2. Scan the QR code\n"
"3. Tap '确认登录' on your phone\n"
```

**Alipay-Specific**:
```
"1. Open Alipay → Tap '+' in top-right → '扫一扫'\n"
"2. Scan the QR code\n"
"3. Review permissions and tap '同意' (Agree)\n"
```

### Scenario C: Different Device Used

**Detection**: Browser shows scan success, but mobile control shows no change.

**Interpretation**: User scanned with another phone (not the connected Android device).

**Action**:
- Monitor browser state only (ignore connected mobile)
- Poll every 5 seconds for up to 60 seconds
- Wait for redirect or success indicators

---

## Phase 4: Verification & Completion

### 4.1 Detect Login/Auth Success

**Success Indicators**:
- URL changed to dashboard/main page
- User avatar, username, or "欢迎" message visible
- "Logout" / "退出登录" button present
- "授权成功" / "登录成功" message

### 4.2 Edge Case Handling

| State | Meaning | Action |
|-------|---------|--------|
| "二维码已过期" / "Expired" | QR timed out | Click refresh button, restart Phase 2 |
| "二维码失效" / "Invalid" | QR was used/cancelled | Refresh and retry |
| "用户取消授权" / "Cancelled" | User denied on phone | Ask if they want to retry |
| "请在手机上确认" / "Confirm on phone" | Waiting for mobile confirmation | Continue polling (max 60s) |
| "登录超时" / "Timeout" | Auth window expired | Retry from Phase 1 |
| QR keeps refreshing | Short expiry (e.g., 30s) | Quick scan or use alternative method |

### 4.3 Timeout Handling

If no success after 60 seconds:
1. Screenshot current state
2. Report: "Authentication timed out. QR may have expired or confirmation was not completed."
3. Ask: "Would you like to retry or try a different login method?"

---

## 🛟 Recovery Strategy

- **QR won't load**: Refresh, check network, verify not blocked by extension
- **App won't open**: Force stop and reopen target app
- **Scan successful but no login**: User likely cancelled on phone - ask them to retry
- **"账号已绑定其他用户" / Account bound**: Binding conflict - escalate to user decision
- **"需要验证身份" / Identity verification**: Additional auth required - human fallback
- **Repeated failures**: Offer alternative login (SMS, password, email)

---

## Required Tools (Cross-Device Set)
- `browser_control` - Display QR, monitor auth state
- `mobile_control` - Operate scanning app
- `screenshot` + `analyze_image` - Verify states on both devices
- `wait` - Polling delays
- `request_human_input` - Manual scan coordination

---

## App Reference Quick Guide

| App | Package | Scanner Location | Confirm Button |
|-----|---------|------------------|----------------|
| **WeChat** | `com.tencent.mm` | 右上角 "+" → "扫一扫" | "确认登录" |
| **Taobao** | `com.taobao.taobao` | 首页相机图标 | "确认登录" |
| **Alipay** | `com.eg.android.AlipayGphone` | 首页 "+" → "扫一扫" | "同意授权" |
| **DingTalk** | `com.alibaba.android.rimet` | 右上角 "+" → "扫一扫" | "确认登录" |
| **QQ** | `com.tencent.mobileqq` | 右上角 "+" → "扫一扫" | "登录" |

---

## Key Principles
- **Platform Agnostic**: Same three-stage flow (Display → Scan → Confirm) applies to all QR auth systems
- **Flexible Detection**: Look for universal patterns (QR image, confirm buttons, success messages) rather than hardcoded selectors
- **Graceful Degradation**: If auto-scan fails, immediately fall back to clear human instructions with app-specific details
- **Independent Monitoring**: Always monitor browser state separately from mobile state - user may use any device to scan
- **Timeout Awareness**: QR codes expire; fast action or quick fallback to manual is essential
