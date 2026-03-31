# EvoLoop 会员订阅集成方案

## 概述

本文档描述 EvoLoop 与 member-center subscription 插件的集成方案，实现会员订阅权限控制和 AI 配额管理。

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      EvoLoop Backend                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │  Agent API  │    │  Chat API   │    │  Code API   │    │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    │
│         │                  │                  │            │
│         └──────────────────┼──────────────────┘            │
│                            │                               │
│              ┌─────────────┴─────────────┐                 │
│              │   Permission/Quota Check  │                 │
│              │   (deps.py)               │                 │
│              └─────────────┬─────────────┘                 │
│                            │                               │
│              ┌─────────────┴─────────────┐                 │
│              │   EvoCloud HTTP Client    │                 │
│              │   (http_client.py)        │                 │
│              └─────────────┬─────────────┘                 │
└────────────────────────────┼────────────────────────────────┘
                             │ HTTP API
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  Member Center (EvoCloud)                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Subscription Plugin                        │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │   │
│  │  │ Plan API    │  │ Subscription│  │ AI Quota  │  │   │
│  │  └─────────────┘  └─────────────┘  └───────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 已完成的工作

### 1. EvoLoop Backend

#### 1.1 HTTP Client 扩展
**文件**: `backend/app/core/evocloud/backends/http_client.py`

新增订阅相关 API 方法：
- `get_subscription_status()` - 获取订阅状态
- `get_subscription_permissions()` - 获取功能权限
- `check_feature_permission()` - 检查特定功能权限
- `get_subscription_plans()` - 获取订阅计划
- `create_subscription_order()` - 创建订阅订单
- `get_ai_quota()` - 获取 AI 配额
- `consume_ai_quota()` - 消耗 AI 配额

#### 1.2 权限检查依赖
**文件**: `backend/app/api/deps.py`

新增依赖函数：
- `check_feature_permission()` - 检查功能权限
- `require_subscription_feature()` - 要求特定订阅功能
- `check_ai_quota()` - 检查 AI 配额
- `require_ai_quota()` - 要求 AI 配额
- `consume_ai_quota_dependency()` - 消耗配额

### 2. Member Center (subscription 插件)

#### 2.1 AI 配额 API
**文件**: `addon/subscription/api/controller/AiQuota.php`

提供接口：
- `GET /subscription/api/aiQuota?type=xxx` - 获取配额
- `GET /subscription/api/aiQuota/all` - 获取所有配额
- `POST /subscription/api/aiQuota/consume` - 消耗配额
- `POST /subscription/api/aiQuota/batchCheck` - 批量检查
- `GET /subscription/api/aiQuota/history` - 使用历史

#### 2.2 数据表
**文件**: `addon/subscription/install.sql`

新增表：
```sql
subscription_ai_quota_usage - AI 配额使用记录
```

## 使用指南

### 基本用法：保护路由

```python
from app.api.deps import require_subscription_feature, require_ai_quota

# 需要特定订阅功能
@router.post("/premium-feature")
async def premium_feature(
    user: CurrentUser = Depends(require_subscription_feature("premium_content"))
):
    return {"message": "您有权限访问此功能"}

# 需要 AI 配额
@router.post("/ai-chat")
async def ai_chat(
    user: CurrentUser = Depends(require_ai_quota("ai_chat"))
):
    return {"message": "AI 响应..."}
```

### 手动检查权限

```python
from app.api.deps import check_feature_permission, check_ai_quota

@router.get("/check")
async def check(
    token: TokenDep,
    feature: str
):
    has_access = await check_feature_permission(feature, token)
    quota_info = await check_ai_quota("ai_chat", token)
    
    return {
        "has_feature_access": has_access,
        "quota": quota_info
    }
```

### 消耗配额

```python
from app.api.deps import consume_ai_quota_dependency

@router.post("/ai-service")
async def ai_service(
    req: ChatRequest,
    user: CurrentUser = Depends(require_ai_quota("ai_chat"))
):
    # 执行业务逻辑
    result = await process_ai_request(req)
    
    # 消耗配额（记录 token 使用量）
    await consume_ai_quota_dependency(
        "ai_chat", 
        count=1, 
        metadata={"tokens": result.token_count, "model": result.model}
    )
    
    return result
```

### 前端集成

```javascript
// 检查用户是否有权限
async function checkPermission(feature) {
    const response = await fetch('/api/subscription/feature/check?feature=' + feature, {
        headers: { 'Authorization': 'Bearer ' + token }
    });
    return await response.json();
}

// 获取配额状态
async function getQuotaStatus() {
    const response = await fetch('/api/subscription/quota/status', {
        headers: { 'Authorization': 'Bearer ' + token }
    });
    return await response.json();
}

// 获取订阅计划
async function getSubscriptionPlans() {
    const response = await fetch('/api/subscription/plans');
    return await response.json();
}
```

## 配置说明

### AI 配额类型

系统采用**统一配额池**设计，不再区分配额类型：

```php
// 统一配额池
[
    'quota' => 100,        // 总额度(-1=无限)
    'quota_used' => 50,    // 已使用额度
    'remaining' => 50,     // 剩余额度
]
```

- `-1` 表示无限配额
- 免费用户默认配额可在配置中调整

### 功能特性

在 `Plan.php` 中定义了可用的功能特性：

```php
[
    'basic_access' => '基础访问权限',
    'premium_content' => '付费内容访问',
    'vip_support' => 'VIP支持',
    'advanced_tools' => '高级工具',
    'personal_coach' => '个人教练',
    // ... 更多
]
```

## 错误处理

### 权限不足 (403)

```json
{
    "detail": {
        "code": "SUBSCRIPTION_REQUIRED",
        "message": "需要订阅功能: premium_content",
        "feature": "premium_content",
        "current_level": "免费用户",
        "upgrade_url": "/subscription/plans",
        "suggestion": "请升级您的订阅以使用该功能"
    }
}
```

### 配额已用完 (429)

```json
{
    "detail": {
        "code": "QUOTA_EXHAUSTED",
        "message": "AI 配额已用完",
        "used": 100,
        "total": 100,
        "upgrade_url": "/subscription/plans",
        "suggestion": "配额将在每日零点重置，或请升级订阅获取更多配额"
    }
}
```

## 部署步骤

### 1. 更新 Member Center

```bash
# 1. 复制新的 subscription 插件文件到 addon/subscription/

# 2. 执行数据库更新
php think migrate:run
# 或手动执行 install.sql 中的新增表创建语句

# 3. 清除缓存
php think cache:clear
```

### 2. 更新 EvoLoop Backend

```bash
# 1. 拉取最新代码

# 2. 重启服务
# Docker 部署
docker-compose restart backend

# 或本地部署
cd backend
uv run uvicorn app.main:app --reload
```

### 3. 配置测试

```bash
# 测试订阅状态接口
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-domain.com/subscription/api/subscription/status

# 测试 AI 配额接口（统一配额池）
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-domain.com/subscription/api/aiQuota
```

## 监控与日志

### 关键日志

```python
# 权限检查失败
logger.warning(f"权限检查失败 [{feature}]: 用户 {user_id}")

# 配额不足
logger.info(f"配额不足: 用户 {user_id}, 已用 {used}/{total}")

# API 调用异常
logger.error(f"调用 Member Center API 失败: {error}")
```

### 监控指标

建议监控以下指标：
- 权限检查成功率
- 配额消耗速率
- API 响应时间
- 错误率（403, 429）

## 后续优化建议

1. **缓存优化**
   - 订阅状态缓存（5-10分钟）
   - 配额信息缓存（1-5分钟）
   - 使用 Redis 分布式缓存

2. **降级策略**
   - Member Center 不可用时允许访问（宽松模式）
   - 配额服务异常时允许访问（容错模式）

3. **实时同步**
   - WebSocket 推送订阅状态变更
   - 支付成功后立即刷新配额

4. **统计分析**
   - 配额使用报表
   - 转化率分析
   - 用户行为分析

## API 端点汇总

### EvoLoop Backend

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/subscription/feature/check` | POST | 检查功能权限 |
| `/api/subscription/quota/status` | GET | 获取配额状态 |
| `/api/subscription/subscription/info` | GET | 获取订阅信息 |
| `/api/subscription/plans` | GET | 获取订阅计划 |


### Member Center

| 端点 | 方法 | 说明 |
|------|------|------|
| `/subscription/api/subscription/status` | GET | 订阅状态 |
| `/subscription/api/subscription/permissions` | GET | 功能权限 |
| `/subscription/api/subscription/checkPermission` | POST | 检查权限 |
| `/subscription/api/subscription/plans` | GET | 订阅计划 |
| `/subscription/api/aiQuota` | GET | 获取 AI 配额 |
| `/subscription/api/aiQuota/consume` | POST | 消耗配额 |

## 参考文档

- [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [Member Center 插件开发文档](https://www.niushop.com/docs)
- [ThinkPHP 6 事件系统](https://www.kancloud.cn/manual/thinkphp6_0/1037489)
