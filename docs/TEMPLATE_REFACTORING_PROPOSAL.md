# 模板文件模块分类评估与重构方案

## 📊 现状分析

### 当前模板分布
```
templates/
├── [15个主模板在根目录，未分类]
├── domain/          (28个模板 - 过于庞大)
├── fragments/       (17个模板)
├── report/          (5个模板)
├── macro/           (5个模板)
├── tool/            (4个模板)
├── wiki/            (2个模板)
├── requirements/    (2个模板)
├── lsp/             (2个模板)
├── vision/          (1个模板)
├── memory/          (1个模板)
└── environment/     (1个模板)
```

### 存在的问题

1. **根目录杂乱** - 15个主模板散落在根目录，没有统一分类
2. **domain目录膨胀** - 28个模板混在一起，职责不清晰
3. **分类边界模糊** - vision、multimodal、events等分散在不同地方
4. **难以维护** - 新模板不知道应该放在哪里

---

## ✅ 重构方案

### 建议的新目录结构

```
templates/
├── agents/              # 🤖 Agent系统核心提示词
│   ├── worker.prompt.j2
│   ├── supervisor.prompt.j2
│   ├── chat.prompt.j2
│   ├── finish.prompt.j2
│   └── awakening.prompt.j2
│
├── learning/            # 📚 学习/技能合成
│   ├── skill_synthesis.prompt.j2
│   ├── skill_discovery.prompt.j2
│   ├── multimodal_synthesis.prompt.j2
│   ├── multimodal_task_context.j2
│   ├── smart_replay_macro.prompt.j2
│   ├── smart_replay_metadata.prompt.j2
│   ├── smart_replay_phases.prompt.j2
│   └── synthesis_human.prompt.j2
│
├── codebase/            # 💻 代码库相关 (从domain迁移)
│   ├── code_audit.prompt.j2
│   ├── codebase_indexing.prompt.j2
│   ├── codebase_retrieval.prompt.j2
│   ├── codebase_tree.prompt.j2
│   └── directory_summary.prompt.j2
│
├── vision/              # 👁️ 视觉/多模态相关
│   ├── vision.prompt.j2
│   ├── vision_analysis.prompt.j2
│   ├── vision_context.prompt.j2
│   ├── elements_list.prompt.j2
│   ├── multimodal_frames.prompt.j2
│   ├── ocr_results.prompt.j2
│   └── perceptions.prompt.j2
│
├── events/              # 📋 事件/Trace相关 (从domain迁移)
│   ├── action_summary.prompt.j2
│   ├── event_context.prompt.j2
│   └── trace_narrative.prompt.j2
│
├── memory/              # 🧠 记忆相关
│   ├── episodes_summary.prompt.j2
│   ├── memory_consolidation.prompt.j2
│   └── atlas_detail.prompt.j2
│
├── planning/            # 📋 规划/分析/分类
│   ├── feasibility_analysis.prompt.j2
│   ├── dynamic_app_triage.prompt.j2
│   ├── explorer_triage.prompt.j2
│   ├── expert_roles.prompt.j2
│   └── query_rewrite.prompt.j2
│
├── project/             # 📁 项目管理
│   ├── project_management.prompt.j2
│   ├── project_state.prompt.j2
│   ├── project_summary.prompt.j2
│   └── document_content.prompt.j2
│
├── wiki/                # 📖 Wiki相关
│   ├── wiki.prompt.j2
│   ├── wiki_context.prompt.j2
│   └── file_tree.prompt.j2
│
├── lsp/                 # 🔧 LSP相关
│   ├── diagnostics.prompt.j2
│   └── definitions.prompt.j2
│
├── macro/               # ⚙️ 宏执行相关
│   ├── analyze_results.prompt.j2
│   ├── check_redundancy.prompt.j2
│   ├── decide_next_step.prompt.j2
│   ├── is_failure_terminal.prompt.j2
│   └── verify_outcome.prompt.j2
│
├── tool/                # 🛠️ 工具提示词
│   ├── git_harvest.prompt.j2
│   ├── cypher_generation.prompt.j2
│   ├── orchestration_aggregate.prompt.j2
│   └── orchestration_decompose.prompt.j2
│
├── report/              # 📊 报告类
│   ├── response.prompt.j2
│   ├── batch_summary.prompt.j2
│   ├── tool_outputs.prompt.j2
│   ├── comparison.md.j2
│   └── verification.md.j2
│
├── requirements/        # 📝 需求分析
│   ├── analysis_prompt.j2
│   └── breakdown_prompt.j2
│
├── environment/         # 🌍 环境感知
│   └── capability_boundaries.prompt.j2
│
├── autonomous/          # 🤖 自治任务
│   └── autonomous_task.prompt.j2
│
└── fragments/           # 🧩 可复用片段
    ├── common/          # 通用组件
    │   ├── macros.j2
    │   ├── list_items.j2
    │   ├── action_docs.j2
    │   └── error_details.j2
    ├── blackboard.j2
    ├── knowledge_block.j2
    ├── memory_section.j2
    ├── mission_ticket.j2
    ├── skill_catalog.j2
    ├── summaries.j2
    ├── system_rules.j2
    ├── env_awareness.j2
    ├── spatial_awareness.j2
    ├── memory_replay.j2
    ├── applescript_protocol.j2
    └── list_renderer.j2
```

---

## 📁 迁移映射表

| 原位置 | 新位置 | 说明 |
|--------|--------|------|
| `worker.prompt.j2` | `agents/worker.prompt.j2` | Agent核心 |
| `supervisor.prompt.j2` | `agents/supervisor.prompt.j2` | Agent核心 |
| `chat.prompt.j2` | `agents/chat.prompt.j2` | Agent核心 |
| `finish.prompt.j2` | `agents/finish.prompt.j2` | Agent核心 |
| `awakening.prompt.j2` | `agents/awakening.prompt.j2` | Agent核心 |
| `skill_synthesis.prompt.j2` | `learning/skill_synthesis.prompt.j2` | 学习模块 |
| `skill_discovery.prompt.j2` | `learning/skill_discovery.prompt.j2` | 学习模块 |
| `multimodal_synthesis.prompt.j2` | `learning/multimodal_synthesis.prompt.j2` | 学习模块 |
| `smart_replay_*.prompt.j2` | `learning/` | 学习模块 |
| `domain/code_*.prompt.j2` | `codebase/` | 代码库相关 |
| `domain/codebase_*.prompt.j2` | `codebase/` | 代码库相关 |
| `domain/directory_summary.prompt.j2` | `codebase/` | 代码库相关 |
| `domain/vision_*.prompt.j2` | `vision/` | 视觉相关 |
| `domain/multimodal_frames.prompt.j2` | `vision/` | 视觉相关 |
| `domain/ocr_results.prompt.j2` | `vision/` | 视觉相关 |
| `domain/perceptions.prompt.j2` | `vision/` | 视觉相关 |
| `domain/action_summary.prompt.j2` | `events/` | 事件相关 |
| `domain/event_context.prompt.j2` | `events/` | 事件相关 |
| `domain/trace_narrative.prompt.j2` | `events/` | 事件相关 |
| `domain/memory_consolidation.prompt.j2` | `memory/` | 记忆相关 |
| `domain/atlas_detail.prompt.j2` | `memory/` | 记忆/Atlas相关 |
| `domain/project_*.prompt.j2` | `project/` | 项目管理 |
| `domain/document_content.prompt.j2` | `project/` | 项目管理 |
| `domain/feasibility_analysis.prompt.j2` | `planning/` | 规划分析 |
| `domain/dynamic_app_triage.prompt.j2` | `planning/` | 规划分析 |
| `domain/explorer_triage.prompt.j2` | `planning/` | 规划分析 |
| `domain/expert_roles.prompt.j2` | `planning/` | 规划分析 |
| `domain/query_rewrite.prompt.j2` | `planning/` | 规划分析 |
| `domain/retrieval_results.prompt.j2` | `planning/` | 规划分析 |
| `autonomous_task.prompt.j2` | `autonomous/autonomous_task.prompt.j2` | 自治任务 |

---

## 🎯 分类原则

### 1. 按功能模块分类
- **agents/** - 系统核心Agent（Worker, Supervisor, Chat, Finish）
- **learning/** - 技能学习、合成、发现
- **codebase/** - 代码库分析、索引、检索
- **vision/** - 视觉理解、多模态处理
- **events/** - 事件追踪、Trace记录
- **memory/** - 长期记忆、知识图谱

### 2. 按使用场景分类
- **planning/** - 任务规划、可行性分析、角色分配
- **project/** - 项目管理、文档处理
- **report/** - 结果报告、响应格式化
- **requirements/** - 需求分析、任务拆解

### 3. 按技术领域分类
- **macro/** - 宏执行、自动化脚本
- **lsp/** - 语言服务器协议
- **tool/** - 通用工具调用
- **wiki/** - 知识库管理

---

## 💡 实施建议

### 阶段一：核心Agent迁移（低风险）
1. 创建 `agents/` 目录
2. 迁移 worker, supervisor, chat, finish, awakening

### 阶段二：功能模块迁移（中风险）
1. 创建 `learning/`, `codebase/`, `vision/`, `events/`, `memory/`
2. 从 domain/ 迁移相关模板
3. 更新 Python 代码中的模板引用路径

### 阶段三：场景分类迁移（中风险）
1. 创建 `planning/`, `project/`
2. 迁移剩余 domain/ 模板

### 阶段四：清理优化（低风险）
1. 检查并删除 domain/ 目录
2. 更新文档
3. 验证所有模板引用正确

---

## ⚠️ 注意事项

1. **引用路径更新** - 每个模板迁移后，需要更新 Python 代码中的 `render_template()` 调用
2. **模板间引用** - 检查模板内部的 `{% include %}` 和 `{% from ... import %}` 语句
3. **向后兼容** - 考虑是否需要保留旧路径的别名（软链接）过渡一段时间
4. **测试覆盖** - 迁移后需要全面测试相关功能

---

## 📊 收益评估

| 指标 | 当前 | 重构后 | 收益 |
|------|------|--------|------|
| 根目录模板数 | 15 | 0 | ✅ 清晰 |
| 最大目录模板数 | 28 (domain) | ~8 (learning/vision) | ✅ 均衡 |
| 分类清晰度 | 低 | 高 | ✅ 易维护 |
| 新模板定位 | 困难 | 明确 | ✅ 易扩展 |
| 模板复用性 | 中 | 高 | ✅ 组件化 |

---

## 🚀 下一步行动

需要我执行这个重构方案吗？我可以：

1. 按阶段创建新目录并迁移模板
2. 更新所有 Python 代码中的模板引用路径
3. 验证模板间的引用关系
4. 提供完整的变更清单
