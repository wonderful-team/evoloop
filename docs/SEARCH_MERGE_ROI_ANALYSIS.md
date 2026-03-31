# search_skills + search_native_tools 合并 ROI 分析

## 诚实评估：收益 < 成本，不建议合并

---

## 一、预期收益分析

### 1.1 表面收益（微不足道）

| 指标 | 当前 | 合并后 | 实际影响 |
|------|------|--------|----------|
| 工具总数 | 51 | 50 | -1 (2% ↓) |
| 搜索类工具 | 7 | 6 | -1 (14% ↓) |
| Agent 选择困惑 | 高 | 仍然高 | 边际改善 |

**现实：** 从 7 个搜索工具减到 6 个，Agent 仍然面临选择困难。

### 1.2 命名一致性收益（有限）

**当前：**
```python
search_skills(query="python")        # ✅ 动词_名词
search_native_tools(query="git")     # ✅ 动词_名词（已符合规范）
```

**合并后：**
```python
search_knowledge(query="python", source="skills")   # 需要额外参数
search_knowledge(query="git", source="tools")       # 需要额外参数
```

**问题：** 
- 当前命名已经规范（都是 search_*）
- 合并后增加了 `source` 参数，复杂度反而上升

---

## 二、实际成本分析

### 2.1 代码修改成本（中等）

**需要修改的文件：**
```
1. 工具实现（新建 search_knowledge）
2. agent_main.yaml（删除2个，添加1个）
3. Prompts（所有提到 search_skills/native_tools 的地方）
4. 可能的前端代码（如果有硬编码）
```

**工作量：** 半天到一天

### 2.2 Agent 学习成本（被忽视的重要成本）

**当前使用方式（简单）：**
```python
# Agent 想搜索技能
search_skills(query="数据库操作")

# Agent 想搜索工具
search_native_tools(query="文件操作")
```

**合并后使用方式（复杂）：**
```python
# Agent 需要决定 source 参数
search_knowledge(query="数据库操作", source="skills")  # 还是 "tools"?

# 如果不确定，可能用 "both"
search_knowledge(query="数据库操作", source="both")
```

**新增认知负担：**
- Agent 需要理解 "skills" 和 "tools" 的区别
- Agent 需要决定使用哪个 source
- 如果不确定，需要选择 "both"

### 2.3 功能语义混淆成本（严重）

**根本问题：skills 和 tools 是完全不同的概念**

| 维度 | Skills | Native Tools |
|------|--------|--------------|
| **定义** | 学习的技能/经验 | 系统原生工具 |
| **来源** | 从执行轨迹学习 | 系统预定义 |
| **内容** | 多步骤流程 | 单一功能 |
| **示例** | "如何部署到 AWS" | "read_file", "write_file" |
| **使用场景** | 复杂任务指导 | 原子操作 |

**合并后的问题：**
```python
search_knowledge(query="如何读取文件")
# 返回结果混合了：
# - Skill: "文件操作最佳实践"（多步骤教程）
# - Tool: "read_file 工具文档"（单一步骤）

# Agent 困惑：我该用哪个？
```

---

## 三、替代方案分析

### 方案 A：保持现状（推荐）

**现状：**
```python
search_skills(query="...")      # 专用于技能搜索
search_native_tools(query="...") # 专用于工具搜索
```

**优势：**
- ✅ 语义清晰（skills ≠ tools）
- ✅ 使用简单（无额外参数）
- ✅ 结果类型一致（不混合）
- ✅ 无需修改代码

### 方案 B：删除 search_native_tools（更合理的简化）

**问题：** `search_native_tools` 真的有用吗？

**使用场景分析：**
```
Agent: 我需要搜索原生工具
       → search_native_tools(query="文件操作")
       → 返回: ["read_file", "write_file", "edit_file"]
       
Agent: 但这些工具我在 prompt 里已经看到了...
```

**现实：**
- Agent 的 prompt 已经包含可用工具列表
- `search_native_tools` 低频使用（几乎不用）
- 删除它，保留 `search_skills` 更有意义

**删除收益：**
- 工具数 -1
- 不增加复杂度
- 不影响核心功能

### 方案 C：合并为智能路由（过度设计）

```python
async def search_knowledge(query: str):
    # 自动判断是技能还是工具查询
    # 同时搜索两者，根据相关性排序
    pass
```

**问题：**
- 实现复杂
- 结果混合，Agent 仍需区分
- 收益有限

---

## 四、对比总结

| 方案 | 工具数变化 | 复杂度 | 语义清晰度 | 推荐度 |
|------|-----------|--------|------------|--------|
| A. 保持现状 | 0 | 低 | ✅ 高 | ⭐⭐⭐⭐⭐ |
| B. 删除 search_native_tools | -1 | 低 | ✅ 高 | ⭐⭐⭐⭐ |
| C. 简单合并（带 source 参数） | -1 | 中 | ❌ 低 | ⭐⭐ |
| D. 智能路由合并 | -1 | 高 | ⚠️ 中 | ⭐ |

---

## 五、最终建议

### 不建议合并的原因

1. **收益微小** - 工具数 -1，但认知负担不变
2. **概念混淆** - skills 和 tools 是不同概念
3. **增加复杂度** - source 参数引入新决策点
4. **修改成本高** - 涉及多处代码和 prompts

### 建议方案

**方案 1：保持现状（推荐）**
- `search_skills` 和 `search_native_tools` 保持独立
- 命名已规范，语义清晰

**方案 2：删除 search_native_tools（可选）**
- 如果确认低频使用，可直接删除
- 比合并更简单、更干净

### 应该关注的真正问题

工具系统的大问题不是这 1-2 个工具，而是：

1. **Worker 47个工具一次性暴露** → 需要分层
2. **代码探索工具刚重构完** → 需要观察效果
3. **环境控制工具可能是 Facade** → 需要验证

**结论：放弃合并，将精力投入真正高 ROI 的优化。**
