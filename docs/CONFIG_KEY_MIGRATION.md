# SystemConfig Key 命名迁移指南

## 变更概述

本次优化修复了 SystemConfig 表中的 key 命名不一致问题：

### 1. 设备名称 Key 修复
- **旧 Key**: `EVOLOOP_DEVICE_NAME` (前端之前使用)
- **新 Key**: `EVOCLOUD_DEVICE_NAME` (与后端保持一致)

### 2. Vision Model Key 统一
- **旧 Key**: `LLM_VISION_MODEL` (之前 initial_data.py 使用)
- **新 Key**: `VISION_MODEL` (现已统一)

### 3. 新增的 Key
- `EMBEDDING_DIMENSIONS` - Embedding 向量维度配置

## 数据库迁移步骤

如果你的数据库中已经存在旧 Key，需要执行以下 SQL 迁移：

```sql
-- 1. 迁移设备名称配置（如果存在旧 key）
UPDATE systemconfig
SET key = 'EVOCLOUD_DEVICE_NAME'
WHERE key = 'EVOLOOP_DEVICE_NAME';

-- 2. 迁移 Vision Model 配置（如果存在旧 key）
UPDATE systemconfig
SET key = 'VISION_MODEL'
WHERE key = 'LLM_VISION_MODEL';

-- 3. 添加 Embedding Dimensions 配置（如果不存在）
INSERT INTO systemconfig (key, value, description)
SELECT 'EMBEDDING_DIMENSIONS', '768', 'Embedding vector dimensions'
WHERE NOT EXISTS (SELECT 1 FROM systemconfig WHERE key = 'EMBEDDING_DIMENSIONS');
```

## 当前 SystemConfig Key 清单

| Key | 用途 | 设置页面 |
|-----|------|---------|
| `WORKSPACE_ROOT` | 工作区根目录 | General Settings |
| `EVOCLOUD_DEVICE_NAME` | 设备名称 | General Settings |
| `LANGUAGE` | 界面语言 | General Settings |
| `INTENT_MIN_CONFIDENCE` | 意图识别阈值 | General Settings |
| `REQUIRE_PLAN_APPROVAL` | 计划审批开关 | General Settings |
| `LLM_PROVIDER` | LLM 提供商 | LLM Settings |
| `LLM_BASE_URL` | LLM API 地址 | LLM Settings |
| `LLM_MODEL` | LLM 模型名 | LLM Settings |
| `LLM_API_KEY` | LLM API 密钥 | LLM Settings |
| `VISION_MODEL` | 视觉模型名 | LLM Settings |
| `EMBEDDING_PROVIDER` | Embedding 提供商 | Embedding Settings |
| `EMBEDDING_BASE_URL` | Embedding API 地址 | Embedding Settings |
| `EMBEDDING_MODEL` | Embedding 模型名 | Embedding Settings |
| `EMBEDDING_API_KEY` | Embedding API 密钥 | Embedding Settings |
| `EMBEDDING_DIMENSIONS` | Embedding 向量维度 | Embedding Settings |

## 验证迁移

执行迁移后，可以通过以下 SQL 验证：

```sql
-- 检查所有现有的 key
SELECT key, value, description FROM systemconfig ORDER BY key;

-- 确保没有旧 key 残留
SELECT * FROM systemconfig WHERE key IN ('EVOLOOP_DEVICE_NAME', 'LLM_VISION_MODEL');
```

如果第二条查询返回空结果，说明迁移成功。
