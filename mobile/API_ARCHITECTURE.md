# EvoLoop Mobile API 架构文档

## 系统架构链路

根据 PRD 文档，Mobile 端的 API 调用遵循以下架构：

```
┌─────────────────────────────────────────────────────────────────┐
│                     EvoLoop Mobile (React Native)                │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  API Client                                             │   │
│   │  - services/api/conversations.ts                       │   │
│   │  - services/api/skills.ts                              │   │
│   │  - services/api/artifacts.ts                           │   │
│   │  - services/api/subscription.ts                        │   │
│   └─────────────────────────┬───────────────────────────────┘   │
│                             │                                    │
│                             ▼                                    │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  HTTP Client (axios)                                    │   │
│   │  Base URL: https://evoloop.develop-assistant.cn        │   │
│   └─────────────────────────┬───────────────────────────────┘   │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              │ HTTPS / WSS
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Gateway (evoloop/backend)                     │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  路由分发                                                │   │
│   │                                                         │   │
│   │  /gateway/ws          → WebSocket 服务                  │   │
│   │  /gateway/api/v1/*    → 内部服务路由                    │   │
│   │  /member/*            → member-center/backend          │   │
│   └─────────────────────────┬───────────────────────────────┘   │
│                             │                                    │
│                             │ EvoCloudHTTPClient                 │
│                             │ (@ http_client.py:428-522)         │
│                             ▼                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ 会话/对话服务    │  │  Skill/MCP 服务  │  │ member-center   │
│                 │  │                 │  │ /backend        │
│ • Conversations │  │ • Skills        │  │                 │
│ • Artifacts     │  │ • MCP Servers   │  │ • Subscription  │
│ • Rewind/Retry  │  │ • Execution     │  │ • Auth          │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## 路由前缀规则

| 功能模块 | 路径前缀 | 说明 |
|----------|----------|------|
| **聊天对话** (WebSocket) | `/gateway/ws` | ASR + LLM 实时对话 |
| **会话管理** | `/gateway/api/v1` | 对话历史、Rewind/Retry |
| **Artifacts** | `/gateway/api/v1` | 生成的文件/报告 |
| **Skills** | `/gateway/api/v1` | 技能/MCP 管理 |
| **模型管理** | `/gateway/api/v1` | 模型选择、Token 统计 |
| **设备管理** | `/gateway/api/v1` | 设备列表、绑定、指令 |
| **项目管理** | `/gateway/api/v1` | 项目列表、切换 |
| **订阅管理** | `/member` | 套餐、订单、权益 (通过 Gateway 转发) |
| **用户认证** | `/member` | 登录、注册 (通过 Gateway 转发) |

## API 客户端文件说明

### 1. `conversations.ts` - 会话管理
```typescript
// 通过 Gateway 访问
GET    /gateway/api/v1/conversations
POST   /gateway/api/v1/conversations
GET    /gateway/api/v1/conversations/:id/history
POST   /gateway/api/v1/conversations/:id/rewind
POST   /gateway/api/v1/conversations/:id/retry
```

### 2. `skills.ts` - 技能系统
```typescript
// 通过 Gateway 访问
GET    /gateway/api/v1/skills
POST   /gateway/api/v1/skills/execute
GET    /gateway/api/v1/mcp/servers
```

### 3. `artifacts.ts` - Artifacts
```typescript
// 通过 Gateway 访问
GET    /gateway/api/v1/conversations/:id/artifacts
GET    /gateway/api/v1/artifacts/:id
GET    /gateway/api/v1/artifacts/:id/download
```

### 4. `models.ts` - 模型管理
```typescript
// 通过 Gateway 访问
GET    /gateway/api/v1/models
GET    /gateway/api/v1/usage/quota
GET    /gateway/api/v1/usage/tokens
```

### 5. `subscription.ts` - 订阅和权益
```typescript
// 通过 Gateway 转发到 member-center
GET    /member/subscription/api/subscription/status
GET    /member/subscription/api/subscription/benefits
POST   /member/subscription/api/order/create
```

### 6. `auth.ts` - 用户认证
```typescript
// 通过 Gateway 转发到 member-center
POST   /member/api/login/mobile
POST   /member/api/login/login
GET    /member/api/member/info
```

### 7. `devices.ts` - 设备管理
```typescript
// 通过 Gateway 访问
GET    /gateway/api/v1/devices
POST   /gateway/api/v1/devices/bind
POST   /gateway/api/v1/commands/send
```

### 8. `projects.ts` - 项目管理
```typescript
// 通过 Gateway 访问
GET    /gateway/api/v1/projects
POST   /gateway/api/v1/projects/switch
```

## WebSocket 连接

```typescript
// WebSocket URL
const WS_URL = 'wss://evoloop.develop-assistant.cn/gateway/ws';

// 连接流程
1. 建立 WebSocket 连接
2. 发送认证消息 (JWT Token)
3. 开始语音/文本对话
4. 接收实时响应
```

## 权益检查流程

```typescript
// 1. 获取会员权益
const benefits = await subscriptionApi.getMemberBenefits();

// 2. 检查特定权益
const hasVoice = benefits.benefits.voice;
const aiQuota = benefits.benefits.ai_quota;

// 3. 或单独检查某项权益
const result = await subscriptionApi.checkBenefit('voice');
```

## 支付流程

```typescript
// 1. 创建订单 (指定 app_type: 'app')
const order = await subscriptionApi.createOrder({
  level_id: 3,
  auto_renew: 0,
  app_type: 'app',  // 关键：使用 APP 支付
});

// 2. 调起微信支付 (react-native-wechat-lib)
const payResult = await WeChat.pay({
  partnerId: order.pay_data.partnerid,
  prepayId: order.pay_data.prepayid,
  nonceStr: order.pay_data.noncestr,
  timeStamp: order.pay_data.timestamp,
  package: order.pay_data.package,
  sign: order.pay_data.sign,
});

// 3. 检查订单状态
const status = await subscriptionApi.checkOrderStatus(order.order_id);
```

## 重要配置

### Base URL
```typescript
const BASE_URL = 'https://evoloop.develop-assistant.cn';
```

### 请求头
```typescript
headers: {
  'Authorization': 'Bearer {jwt_token}',
  'Content-Type': 'application/json',
}
```

### 错误处理
```typescript
// 401 - Token 过期/无效 → 跳转登录
// 403 - 无权限 → 显示升级提示
// 429 - 配额耗尽 → 显示购买提示
// 500 - 服务器错误 → 重试或提示
```

## 与 Desktop 的差异

| 功能 | Desktop | Mobile |
|------|---------|--------|
| 支付 | `app_type: 'pc'` (扫码) | `app_type: 'app'` (微信 SDK) |
| 语音 | Desktop 控制 | Mobile 原生 ASR |
| 浏览器控制 | ✅ 支持 | ❌ 不支持 (权益检查) |
| MCP 配置 | ✅ 完整功能 | ⚠️ 仅查看/触发 |

## 调试建议

1. **使用 Charles/Fiddler** 抓包检查请求路径
2. **检查 Gateway 日志** 确认路由转发正常
3. **验证 JWT Token** 是否过期
4. **检查会员权益** 是否有权限访问功能

## 参考文档

- PRD: `/docs/PRD_Mobile_ReactNative_v1.0.md`
- Gateway HTTP Client: `@evoloop/backend/app/core/evocloud/backends/http_client.py`
- Subscription Service: `@member-center/backend/addon/subscription/`
