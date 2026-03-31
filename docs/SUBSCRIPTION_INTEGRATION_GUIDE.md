# EvoLoop 会员订阅集成指南

## 概述

本文档描述如何在 EvoLoop 中使用 member-center 的会员订阅功能，包括权限检查、AI 配额管理等。

## 前置条件

1. member-center 已安装并启用 subscription 插件
2. 数据库表已创建（执行 install.sql）
3. evoloop 已配置正确的 EVOCLOUD_API_URL

## 快速开始

### 1. 保护 API 路由（最简用法）

```python
from fastapi import APIRouter, Depends
from app.api.deps import require_subscription_feature, require_ai_quota

router = APIRouter()

# 需要特定订阅功能
@router.post("/premium-feature")
async def premium_feature(
    user: CurrentUser = Depends(require_subscription_feature("premium_content"))
):
    """只有 premium_content 权限的用户才能访问"""
    return {"message": "您有权限访问此功能"}

# 需要 AI 配额
@router.post("/ai/chat")
async def ai_chat(
    user: CurrentUser = Depends(require_ai_quota("ai_chat"))
):
    """检查 ai_chat 配额，无配额返回 429"""
    return {"message": "AI 响应..."}
```

### 2. 手动检查权限（灵活场景）

```python
from app.api.deps import check_feature_permission, check_ai_quota

@router.get("/check-permission")
async def check_permission(
    feature: str,
    token: TokenDep,
):
    has_access = await check_feature_permission(feature, token)
    quota_info = await check_ai_quota("ai_chat", token)
    
    return {
        "has_feature_access": has_access,
        "quota": quota_info
    }
```

### 3. 消耗配额

```python
from app.core.evocloud import evocloud_manager

@router.post("/ai-service")
async def ai_service(
    req: ChatRequest,
    user: CurrentUser = Depends(require_ai_quota("ai_chat"))
):
    # 执行业务逻辑
    result = await process_ai_request(req)
    
    # 消耗配额（记录 token 使用量）
    await evocloud_manager.api.consume_ai_quota(
        "ai_chat", 
        count=1, 
        metadata={"tokens": result.token_count, "model": result.model}
    )
    
    return result
```

### 4. 获取订阅信息

```python
from app.core.evocloud import evocloud_manager

@router.get("/subscription/info")
async def get_subscription_info(user: CurrentUser):
    """获取当前用户的订阅详情"""
    result = await evocloud_manager.api.get_subscription_detail()
    return result

@router.get("/subscription/plans")
async def get_plans():
    """获取可用订阅计划"""
    result = await evocloud_manager.api.get_subscription_plans()
    return result
```

## 功能特性列表

subscription 插件支持以下功能特性：

```python
FEATURES = [
    "basic_access",           # 基础访问
    "community_basic",        # 社区基础功能
    "content_free",           # 免费内容
    "premium_content",        # 付费内容
    "priority_support",       # 优先支持
    "vip_support",            # VIP支持
    "advanced_tools",         # 高级工具
    "personal_coach",         # 个人教练
    "custom_study_plan",      # 定制学习计划
    "1v1_consultation",       # 一对一咨询
    "exam_guarantee",         # 考试保障
]
```

## AI 配额（统一配额池）

系统采用**统一配额池**设计，不再区分配额类型。所有 AI 功能共享同一个额度池。

```json
{
    "quota": 100,        // 总额度(-1=无限)
    "quota_used": 50,    // 已使用
    "remaining": 50      // 剩余
}
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
        "upgrade_url": "/subscription/plans"
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
        "upgrade_url": "/subscription/plans"
    }
}
```

## 前端集成示例

```javascript
// 检查权限
async function checkPermission(feature) {
    const response = await fetch(`/subscription/api/subscription/checkPermission`, {
        method: 'POST',
        headers: {
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ feature })
    });
    return await response.json();
}

// 获取配额（统一配额池）
async function getQuota() {
    const response = await fetch(`/subscription/api/aiQuota`, {
        headers: { 'Authorization': 'Bearer ' + token }
    });
    return await response.json();
}

// 获取订阅计划
async function getSubscriptionPlans() {
    const response = await fetch(`/subscription/api/subscription/plans`, {
        headers: { 'Authorization': 'Bearer ' + token }
    });
    return await response.json();
}
```

## 部署检查清单

### member-center 端

```bash
# 1. 执行数据库安装
php think migrate:run
# 或手动执行:
mysql -u root -p < addon/subscription/data/install.sql

# 2. 安装插件（如果尚未安装）
php think addon:install subscription

# 3. 启用插件
php think addon:enable subscription

# 4. 清除缓存
php think cache:clear
```

### evoloop 端

```bash
# 1. 确保 .env 配置正确
EVOCLOUD_API_URL=https://your-member-center.com

# 2. 重启服务
docker-compose restart backend
# 或
uv run uvicorn app.main:app --reload
```

## 测试验证

```bash
# 1. 测试订阅状态接口
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-domain.com/subscription/api/subscription/status

# 2. 测试 AI 配额接口
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-domain.com/subscription/api/aiQuota?type=ai_chat"

# 3. 测试权限检查
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"feature": "ai_chat"}' \
  https://your-domain.com/subscription/api/subscription/checkPermission
```

## 注意事项

1. **配额缓存**: AI 配额有 5 分钟缓存，实际消耗后可能略有延迟
2. **降级策略**: 如果 member-center 不可访问，默认允许访问（避免服务中断）
3. **权限继承**: 高等级会员自动拥有低等级的所有权限
4. **配额重置**: 每日零点重置配额

## 故障排查

### 问题：权限检查总是返回 false

检查：
1. 用户是否已登录（token 是否有效）
2. member-center 中该用户是否有对应的订阅等级
3. 订阅等级是否设置了相应的功能特性

### 问题：配额检查返回 0

检查：
1. 用户是否是付费会员
2. subscription_member 表是否有记录
3. AI 配额使用记录是否正确

### 问题：支付后权限未更新

检查：
1. 支付回调是否正确触发
2. MemberLevelOrderPayNotify 事件是否执行
3. 会员等级是否正确更新
