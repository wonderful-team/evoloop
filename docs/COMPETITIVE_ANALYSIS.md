# EvoLoop vs OpenCode / Claude Code / Kimi Code 对比分析

## 📊 功能对比总览

| 功能维度 | OpenCode | Claude Code | Kimi Code | **EvoLoop** | 差距评估 |
|----------|----------|-------------|-----------|-------------|----------|
| **交互模式** | TUI (Terminal UI) | TUI + 编辑器集成 | Web IDE | **Desktop/Web/Mobile** | ✅ 领先 |
| **智能体架构** | 单 Agent | 单 Agent | 单 Agent | **Multi-Agent (LangGraph)** | ✅ 领先 |
| **代码索引** | 基础语义搜索 | 文件级上下文 | 文件级上下文 | **Graph-RAG + Tree-sitter** | ✅ 领先 |
| **多平台控制** | ❌ | ❌ | ❌ | **Web/Desktop/Mobile** | ✅ 独有 |
| **实时流式输出** | ✅ | ✅ | ✅ | ✅ | 持平 |
| **Ghost Text** | ✅ | ✅ | ✅ | ❌ | ⚠️ 缺失 |
| **智能 Apply** | ✅ (Inline Edit) | ✅ | ✅ | ❌ (全量替换) | ⚠️ 缺失 |
| **Checkpoint/Undo** | ✅ | ✅ | ✅ | ⚠️ (部分) | ⚠️ 弱于 |
| **权限控制** | ✅ 细粒度 | ✅ 细粒度 | ✅ 细粒度 | ✅ 可切换 | 持平 |
| **MCP 扩展** | ✅ | ✅ | ❌ | ✅ | 持平 |
| **工具自创建** | ❌ | ❌ | ❌ | ✅ Runtime Tool | ✅ 独有 |
| **记忆系统** | 短期 | 短期 | 短期 | **图谱情节记忆** | ✅ 领先 |

---

## 🔍 详细差距分析

### 1. ❌ 缺失：Ghost Text / Inline Completion

**对标产品:**
- OpenCode: 编辑器中实时显示 AI 建议的灰色文本
- Claude Code: Cursor-style 的 inline suggestion
- Kimi Code: Web IDE 中的实时代码补全

**EvoLoop 现状:**
- 仅支持通过 `edit_file` / `write_file` 工具进行全量替换
- 没有编辑器集成的 ghost text 体验
- 用户无法直观地看到 AI 将要修改的内容预览

**影响:** ⭐⭐⭐⭐ (高)
- 打断开发流 (Flow)
- 无法快速预览和接受/拒绝小修改

**建议实现:**
```python
# 需要新增工具或扩展 LSP 协议
async def suggest_ghost_text(
    file_path: str,
    cursor_position: int,
    context_lines: int = 5
) -> str:
    """返回 Ghost Text 建议，不实际修改文件"""
```

---

### 2. ❌ 缺失：Smart Apply / Intelligent Edit

**对标产品:**
- OpenCode: `oc apply` - 智能匹配并应用代码变更
- Claude Code: 直接显示 diff，用户确认后应用
- Kimi Code: 内联 diff，一键应用

**EvoLoop 现状:**
- `edit_file`: 必须提供精确的 `target` 字符串匹配
- `write_file`: 全量覆盖，风险高
- 没有 fuzzy match + intelligent merge 能力

**影响:** ⭐⭐⭐⭐⭐ (极高)
- 编辑体验生硬
- 容易因文本不匹配导致编辑失败
- 缺乏"智能修复"能力

**EvoLoop 已有基础:**
```python
# app/domain/tools/utils/editing/engine.py 已有 EditEngine
class EditEngine:
    @staticmethod
    def apply_replacement(content, old, new, replace_all=False):
        # 有 fuzzy matching 能力
```

**建议:** 将 EditEngine 提升到工具层，支持智能 apply。

---

### 3. ⚠️ 弱于：Checkpoint / Session Management

**对标产品:**
- OpenCode: 完整的 session history，可随时回滚到任意检查点
- Claude Code: `/clear` + 隐式的上下文管理
- Kimi Code: 多版本文件历史

**EvoLoop 现状:**
- ✅ 有 `content_hash` 验证（防止并发修改）
- ✅ 有会话历史存储（SQLite）
- ❌ 没有显式的 checkpoint / rollback 机制
- ❌ 没有 session branch/fork 能力

**影响:** ⭐⭐⭐ (中)
- 用户无法安全地"尝试"修改
- 错误恢复成本高

**建议实现:**
```python
# 新增 Checkpoint 系统
class CheckpointManager:
    async def create_checkpoint(self, project_id: int) -> str:
        """创建项目级检查点"""
        
    async def rollback(self, checkpoint_id: str):
        """回滚到指定检查点"""
```

---

### 4. ⚠️ 弱于：Stream Output 实时性

**对标产品:**
- OpenCode: 实时显示思考过程和工具调用
- Claude Code: 流式输出 + tool use 可视化
- Kimi Code: 实时流式输出

**EvoLoop 现状:**
- ✅ 支持 SSE 流式输出
- ✅ 有 `AgentProcess` 组件显示执行步骤
- ❌ 思考过程 (thinking) 展示不够直观
- ❌ 工具调用链的实时可视化较弱

**影响:** ⭐⭐⭐ (中)
- 用户等待时不知道系统在做什么
- 缺乏透明度和可解释性

---

### 5. ✅ 独有优势：Multi-Agent 编排

**EvoLoop 领先:**
- Supervisor-Worker 架构（LangGraph）
- 无限层级任务委派
- 动态工具授权

**对标产品差距:**
- OpenCode/Claude Code/Kimi Code: 基本都是单 Agent 架构
- 复杂任务缺乏分工协作

---

### 6. ✅ 独有优势：全平台控制

**EvoLoop 独有:**
- Browser (Playwright)
- Desktop (PyAutoGUI + AppleScript)
- Mobile (ADB + UIAutomator2)

**对标产品:**
- 纯代码工具，无跨平台控制能力

---

### 7. ✅ 独有优势：Graph-RAG 记忆

**EvoLoop 领先:**
- Neo4j 知识图谱存储任务经验
- 自动回忆相似历史任务
- 避免重复错误

**对标产品:**
- 基本都只有短期上下文记忆

---

## 📈 优先级建议

### P0 ( urgently needed )
1. **Smart Apply / Intelligent Edit**
   - 提升 `edit_file` 的 fuzzy match 能力
   - 支持 diff preview + confirm/reject 流程

2. **Checkpoint / Session Rollback**
   - 文件级版本控制
   - 一键回滚能力

### P1 ( high impact )
3. **Ghost Text / Inline Suggestion**
   - 需要前端编辑器深度集成
   - LSP 协议扩展

4. **Stream Output 优化**
   - 思考过程可视化
   - 工具调用链实时展示

### P2 ( nice to have )
5. **IDE 插件**
   - VS Code / JetBrains 插件
   - 补齐与主流 IDE 的集成差距

---

## 🎯 竞争定位建议

### 当前定位
EvoLoop 是一个 **"通用智能体系统"**，强调：
- 跨平台自动化
- 多智能体协作
- 长期记忆

### 差距补足后的定位
**"企业级自主智能体平台"**
- 保留全平台控制能力
- 补齐开发体验（Ghost Text、Smart Apply）
- 强化企业特性（Checkpoint、审计日志）

---

## 📋 功能实现检查清单

| 功能 | 状态 | 相关文件 | 预计工作量 |
|------|------|----------|-----------|
| Ghost Text | ❌ 未实现 | 需新增 LSP 扩展 | 2-3 周 |
| Smart Apply | ⚠️ 部分 | `utils/editing/engine.py` | 1 周 |
| Checkpoint | ❌ 未实现 | 需新增 checkpoint 模块 | 1-2 周 |
| Stream 优化 | ⚠️ 可改进 | `AgentProcess.tsx` | 3-5 天 |
| IDE 插件 | ❌ 未实现 | 需新建 VS Code 扩展 | 3-4 周 |

---

*分析时间: 2026-03-20*
*分析师: Code Review Assistant*
