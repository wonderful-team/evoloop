# Checkpoint 工具是否应该 Facade 化？

## 结论：不应该 Facade 化

**当前的原子化设计（4个独立工具）优于 Facade 设计。**

---

## 一、Facade 化方案（不建议）

### 假设的 Facade 设计

```python
@evoloop_tool
async def manage_checkpoint(
    action: Literal["create", "list", "rollback", "delete"],
    # create 参数
    name: str | None = None,
    file_paths: list[str] | None = None,
    description: str | None = None,
    # list 参数
    include_auto: bool = False,
    limit: int = 10,
    # rollback/delete 参数
    checkpoint_id: int | None = None,
    dry_run: bool = True,
    confirm: bool = False,
) -> str:
    """
    Manage checkpoints (create, list, rollback, delete).
    
    Args:
        action: The operation to perform
        name: (create) Checkpoint name
        file_paths: (create) Files to include
        description: (create) Optional description
        include_auto: (list) Include auto-created checkpoints
        limit: (list) Max results
        checkpoint_id: (rollback/delete) Target checkpoint ID
        dry_run: (rollback) Preview only
        confirm: (delete) Confirm deletion
    """
    if action == "create":
        if not name or not file_paths:
            return "Error: name and file_paths required for create"
        # ... create logic
    elif action == "list":
        # ... list logic
    elif action == "rollback":
        if checkpoint_id is None:
            return "Error: checkpoint_id required for rollback"
        # ... rollback logic
    elif action == "delete":
        if checkpoint_id is None:
            return "Error: checkpoint_id required for delete"
        # ... delete logic
```

---

## 二、Facade 化的问题分析

### 2.1 参数混乱（严重）

| action | 需要参数 | 忽略参数 | 问题 |
|--------|----------|----------|------|
| create | name, file_paths | checkpoint_id, dry_run, confirm | 6个无关参数 |
| list | include_auto, limit | name, file_paths, checkpoint_id... | 5个无关参数 |
| rollback | checkpoint_id, dry_run | name, file_paths, confirm... | 5个无关参数 |
| delete | checkpoint_id, confirm | name, file_paths, dry_run... | 5个无关参数 |

**结果：** 每个 action 都带有一堆无用的参数，Agent 困惑。

### 2.2 验证逻辑复杂

```python
if action == "create":
    if not name or not file_paths:
        return "Error..."
elif action == "rollback":
    if checkpoint_id is None:
        return "Error..."
elif action == "delete":
    if not confirm:
        return "Warning..."
```

**结果：** 每个调用都需要复杂的参数验证逻辑。

### 2.3 Agent 认知负担增加

**当前（原子化）：**
```python
# Agent 想创建检查点
create_checkpoint(name="...", file_paths=[...])
# 参数清晰，意图明确
```

**Facade 化后：**
```python
# Agent 想创建检查点
manage_checkpoint(
    action="create",  # 需要记住 action 值
    name="...", 
    file_paths=[...],
    # 还有一堆不需要但必须了解的参数
    checkpoint_id=None,  # 不需要但要了解
    dry_run=True,        # 不需要但要了解
    confirm=False        # 不需要但要了解
)
```

**结果：** Agent 需要理解所有参数，即使大部分用不到。

### 2.4 文档复杂

**当前文档（原子化）：**
```
create_checkpoint(name, file_paths, description)
  - 创建检查点
  - 参数：name（必需）, file_paths（必需）, description（可选）
```

**Facade 化后文档：**
```
manage_checkpoint(action, name, file_paths, description, include_auto, limit, checkpoint_id, dry_run, confirm)
  - action="create": 创建（需要 name, file_paths）
  - action="list": 列出（需要 include_auto, limit）
  - action="rollback": 回滚（需要 checkpoint_id, dry_run）
  - action="delete": 删除（需要 checkpoint_id, confirm）
```

**结果：** 文档长度 4 倍，理解难度 4 倍。

---

## 三、为什么我们之前拆分 Facade？

之前拆分 `explore_codebase` 和 `consult_lsp` 正是因为这些问题：

| 问题 | explore_codebase | checkpoint 假设 Facade |
|------|------------------|------------------------|
| 参数混乱 | ✅ 有 | ✅ 会有 |
| action 记忆负担 | ✅ 有 | ✅ 会有 |
| 验证逻辑复杂 | ✅ 有 | ✅ 会有 |
| 文档复杂 | ✅ 有 | ✅ 会有 |

**我们现在做的优化是消除 Facade，而不是创建 Facade。**

---

## 四、如果真的想减少工具数量

### 4.1 正确的方式：分层暴露

```yaml
# Tier 1: 核心（始终暴露）
create_checkpoint    # 高频：改代码前创建
list_checkpoints     # 高频：查看有哪些

# Tier 2: 场景（按需暴露）
rollback_checkpoint  # 回滚场景才需要
delete_checkpoint    # 清理场景才需要
```

**优势：**
- 保持原子化设计 ✅
- 减少平均暴露工具 ✅
- 不增加认知负担 ✅

### 4.2 错误的方式：Facade 化

```python
manage_checkpoint(action="...")  # ❌ 增加认知负担
```

**劣势：**
- 参数混乱 ❌
- 文档复杂 ❌
- 与我们刚做的优化方向相反 ❌

---

## 五、决策矩阵

| 方案 | 工具数 | 认知负担 | 参数清晰度 | 推荐度 |
|------|--------|----------|------------|--------|
| **当前（4个原子）** | 4 | 低 | ✅ 高 | ⭐⭐⭐⭐⭐ |
| **分层暴露** | 2-4 | 低 | ✅ 高 | ⭐⭐⭐⭐⭐ |
| **Facade 化（1个）** | 1 | 高 | ❌ 低 | ⭐⭐ |

---

## 六、总结

### Checkpoint 工具不应该 Facade 化，因为：

1. **参数结构差异大**
   - create 需要 name/file_paths
   - rollback 需要 checkpoint_id/dry_run
   - delete 需要 checkpoint_id/confirm
   - 合并后参数混乱

2. **增加认知负担**
   - Agent 需要理解 action 参数
   - 需要了解不相关的参数
   - 与我们优化的方向相反

3. **我们刚拆分了 Facade**
   - explore_codebase → 4个原子工具 ✅
   - consult_lsp → 3个原子工具 ✅
   - 现在又把 checkpoint 合并回去？❌

### 如果工具数量过多，正确方案是：

**分层暴露（Tier 1/2/3）**
- Tier 1：create_checkpoint, list_checkpoints（始终暴露）
- Tier 2/3：rollback_checkpoint, delete_checkpoint（按需暴露）

**这样既减少了平均暴露工具数，又保持了良好的原子化设计。**

---

## 最终建议

**不要 Facade 化 checkpoint 工具。**

**当前设计（4个原子工具）是优秀的，如果需要优化，请使用分层暴露而非 Facade 化。**
