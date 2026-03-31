# Checkpoint 工具澄清：它们从来就不是 Facade

## 重要澄清

**checkpoint_tools（create_checkpoint, list_checkpoints, rollback_checkpoint, delete_checkpoint）从来就不是 Facade 模式，它们一直都是原子化的好设计。**

---

## 当前状态

```python
# backend/app/domain/tools/checkpoint_tools.py

@evoloop_tool
async def create_checkpoint(name, file_paths, description):
    """Create a checkpoint."""
    # 单一职责：创建

@evoloop_tool
async def list_checkpoints(include_auto, limit):
    """List checkpoints."""
    # 单一职责：列出

@evoloop_tool
async def rollback_checkpoint(checkpoint_id, dry_run):
    """Rollback to a checkpoint."""
    # 单一职责：回滚

@evoloop_tool
async def delete_checkpoint(checkpoint_id, confirm):
    """Delete a checkpoint."""
    # 单一职责：删除
```

**这些工具：**
- ✅ 没有 `action` 参数
- ✅ 每个工具只做一件事
- ✅ 从来就是原子化设计

---

## 可能的误解来源

用户可能混淆了以下概念：

### 1. 四个相关工具 ≠ Facade

```python
# 这是4个独立的原子工具（好设计）
create_checkpoint(...)
list_checkpoints(...)
rollback_checkpoint(...)
delete_checkpoint(...)

# 如果这是 Facade，会是这样（坏设计）
manage_checkpoint(
    action: Literal["create", "list", "rollback", "delete"],
    ...
)
```

**实际上从来没有 `manage_checkpoint` 这个 Facade 工具。**

### 2. 与 explore_codebase 的对比

| 工具 | 设计模式 | 状态 |
|------|----------|------|
| **checkpoint_tools** | ✅ 从来就是原子化 | 不需要改动 |
| **explore_codebase** | ❌ 曾经是 Facade | 已拆分 |
| **consult_lsp** | ❌ 曾经是 Facade | 已拆分 |

---

## 检查方法

### 如何判断是不是 Facade？

**Facade 的标志：**
```python
@evoloop_tool
async def tool_name(
    action: Literal["action_a", "action_b", "action_c"],  # ← 有 action 参数
    ...
)
```

**原子化工具的标志：**
```python
@evoloop_tool
async def tool_name(...):  # ← 没有 action 参数，名字即职责
    ...
```

### checkpoint_tools 验证

```bash
# 检查是否有 action 参数
$ grep -n "action.*Literal" backend/app/domain/tools/checkpoint_tools.py
# 结果：无匹配

# 检查工具装饰器
$ grep -n "@evoloop_tool" backend/app/domain/tools/checkpoint_tools.py
# 结果：4个独立装饰器，对应4个独立函数
```

**结论：checkpoint_tools 是原子化设计，不是 Facade。**

---

## 历史验证

### Git 历史检查

```bash
# 检查是否曾经存在 manage_checkpoint
$ git log --all --source --full-history -S "manage_checkpoint"
# 结果：无匹配

# 检查 checkpoint_tools.py 历史
$ git log --oneline backend/app/domain/tools/checkpoint_tools.py | head -5
# 结果：一直存在的是4个独立函数
```

**历史上从来没有 `manage_checkpoint` Facade。**

---

## 正确的认知

### 系统内实际存在的 Facade（已处理）

| Facade | 状态 | 处理 |
|--------|------|------|
| `explore_codebase` | ❌ 有害 Facade | ✅ 已拆分 |
| `consult_lsp` | ❌ 有害 Facade | ✅ 已拆分 |

### 系统内看起来像 Facade 但实际不是的工具

| 工具 | 实际设计 | 评价 |
|------|----------|------|
| `checkpoint_tools` (4个) | ✅ 原子化 | 好设计，保持 |
| `file_tools` (3个) | ✅ 原子化 | 好设计，保持 |
| `manage_directory` | ⚠️ 有 list action | 可能与 list_directory 重复 |
| `desktop/mobile/browser_control` | ⚠️ 可能是 Facade | 需要验证 |

---

## 总结

### 关键澄清

1. **checkpoint_tools 从来就不是 Facade**
   - 没有 action 参数
   - 4个独立的原子工具
   - 好设计，不需要改动

2. **之前拆分的 Facade 是 explore_codebase 和 consult_lsp**
   - 这两个有 action 参数
   - 已被拆分为原子工具

3. **manage_checkpoint 从未存在**
   - 历史上没有这样的 Facade
   - 当前就是原子化设计

### 最终状态

| 工具/工具组 | 是否是 Facade | 是否需要改动 |
|-------------|---------------|--------------|
| checkpoint_tools (4个) | ❌ 不是 | ✅ 不需要 |
| explore_codebase | ❌ 曾是，已拆分 | ✅ 已完成 |
| consult_lsp | ❌ 曾是，已拆分 | ✅ 已完成 |
| file_tools (3个) | ❌ 不是 | ✅ 不需要 |
| manage_directory | ⚠️ 可能是 | 需要验证 |

**checkpoint_tools 是系统的优秀设计范例，从来就不是 Facade，不需要任何改动。**
