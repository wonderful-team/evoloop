# Agent Engine 改进计划

## 目标

1. **支持匹配多个 Skills** - 复杂任务需要多个 SOP 协同
2. **支持多轮对话** - Worker 保留对话历史，实现渐进式任务执行

---

## 改进1：多 Skill 匹配支持

### 当前问题

- `exact_search` 只返回单个 match
- Supervisor 主要使用单个 `skill_id`
- 复杂任务（如"搜索网页并发送到微信"）需要多个 skills

### 改进方案

1. **增强 Discovery** - 添加 `match_multiple` 方法
2. **修改 Supervisor** - 支持识别多步骤任务并匹配多个 skills
3. **改进 Prompt** - 指导 Supervisor 何时使用多 skill 工作流

---

## 改进2：多轮对话支持

### 当前问题

```python
# worker.py:154
messages = [HumanMessage(content=mission_msg)]  # ❌ 完全重置
```

Worker 看不到之前的对话，无法处理：
- "修改刚才的代码"
- "用刚才的方式处理这个文件"
- "回到第3轮的方案"

### 改进方案

1. **保留 Message History** - Worker 继承对话历史
2. **智能窗口管理** - 控制上下文大小，避免 token 爆炸
3. **添加对话摘要** - 长对话自动压缩历史
4. **显式上下文引用** - 支持 `[Context: xxx]` 标记

---

## 实施步骤

### Phase 1: 多 Skill 匹配
- [ ] 修改 `discovery.py` - 添加 `match_multiple` 方法
- [ ] 修改 `supervisor.prompt.j2` - 多 skill 识别指导
- [ ] 修改 `SkillHydrator` - 支持加载多个 skills

### Phase 2: 多轮对话
- [ ] 修改 `worker.py` - 保留 message history
- [ ] 修改 `worker.prompt.j2` - 对话上下文感知
- [ ] 添加 `ConversationManager` - 对话历史管理

### Phase 3: 集成测试
- [ ] 验证多 skill 工作流
- [ ] 验证多轮对话场景
