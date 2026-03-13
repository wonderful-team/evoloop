# 微信扫码登录实现文档

## 概述

EvoLoop 的微信扫码登录功能直接复用 `member-center`（即 EvoCloud）已有的微信登录能力。EvoLoop 作为代理层，将前端请求转发到 Member Center 的微信登录 API。

## 架构

```
┌─────────────┐     1. 请求二维码     ┌─────────────┐     2. 调用微信API    ┌─────────────┐
│   Desktop   │ ───────────────────→ │   EvoLoop   │ ───────────────────→ │ Member      │
│   登录页    │                      │   Backend   │                      │  Center     │
└─────────────┘                      └─────────────┘                      └─────────────┘
       │                                   │                                   │
       │ 3. 显示二维码                       │ 4. 轮询检查状态                     │
       │                                   │ ←─────────────────────────────────
       │                                   │ 5. 返回扫码状态                     │
       │                                   │ ←─────────────────────────────────
       │                                   │ 6. 扫码成功返回token                │
       │ ←─────────────────────────────────                                    │
       │   7. 生成本地JWT并返回                                                   │
       ▼
   登录成功
```

## 接口映射

EvoLoop 代理以下 Member Center 接口：

| EvoLoop 接口 | Member Center 接口 | 说明 |
|-------------|-------------------|------|
| `GET /auth/wechat/config` | `GET /wechat/api/wechat/verificationWx` | 检查微信配置 |
| `POST /auth/wechat/qrcode` | `POST /wechat/api/wechat/loginCode` | 获取二维码 |
| `GET /auth/wechat/status` | `POST /api/login/checkLogin` | 检查登录状态 |
| `POST /auth/wechat/login-direct` | `POST /api/login/checkLogin` | 完成登录 |

## 实现文件

### 后端

- `backend/app/api/routes/wechat_auth.py` - 微信登录路由（代理到 Member Center）

### 前端

- `frontend/packages/desktop/src/client/services/WechatAuthService.ts` - API 客户端
- `frontend/packages/desktop/src/components/Auth/WechatLogin.tsx` - 微信登录组件
- `frontend/packages/desktop/src/routes/login.tsx` - 登录页面（已集成微信登录）

## 配置

无需额外配置！微信登录配置完全在 Member Center 中管理。

### Member Center 微信配置

在 Member Center 后台配置微信公众账号：
1. 登录 Member Center 后台
2. 进入「应用」→「微信公众号」
3. 配置 AppID、AppSecret、Token、EncodingAESKey
4. 在微信公众平台设置服务器 URL 为 Member Center 的回调地址

## 登录流程

1. **获取二维码**
   - 前端调用 `POST /api/v1/auth/wechat/qrcode`
   - EvoLoop 转发到 Member Center `/wechat/api/wechat/loginCode`
   - 返回二维码图片 URL 和 key

2. **轮询检查状态**
   - 前端每 2 秒调用 `GET /api/v1/auth/wechat/status?key=xxx`
   - EvoLoop 转发到 Member Center `/api/login/checkLogin`
   - 返回状态：pending / confirmed / expired

3. **完成登录**
   - 用户扫码确认后，Member Center 返回 token
   - EvoLoop 使用 Member Center token 生成本地 JWT
   - 返回给前端，完成登录

## 与原始实现的区别

### 之前的实现
- EvoLoop 自己维护微信配置
- EvoLoop 直接调用微信 API
- EvoLoop 处理微信回调

### 现在的实现
- 微信配置完全在 Member Center
- EvoLoop 只作为代理转发请求
- Member Center 处理微信回调
- 更简洁，无需重复配置

## 注意事项

1. **回调地址**：微信回调由 Member Center 直接处理，不需要配置 EvoLoop 的回调地址
2. **用户数据**：微信用户数据存储在 Member Center，EvoLoop 通过标准登录流程获取用户信息
3. **绑定逻辑**：用户绑定/解绑微信需要在 Member Center 完成

## 调试

检查 Member Center 微信配置是否正常：
```bash
curl https://mall.imagicbox.cn/wechat/api/wechat/verificationWx
```

返回 `code: 0` 表示配置正常。
