# 模板文件目录结构

```
backend/app/config/templates/
├── agents/              # 🤖 Agent系统核心提示词 (5个)
│   ├── awakening.prompt.j2
│   ├── chat.prompt.j2
│   ├── finish.prompt.j2
│   ├── supervisor.prompt.j2
│   └── worker.prompt.j2
├── autonomous/          # 🤖 自治任务 (1个)
│   └── autonomous_task.prompt.j2
├── codebase/            # 💻 代码库相关 (5个)
│   ├── code_audit.prompt.j2
│   ├── codebase_indexing.prompt.j2
│   ├── codebase_retrieval.prompt.j2
│   ├── codebase_tree.prompt.j2
│   └── directory_summary.prompt.j2
├── environment/         # 🌍 环境感知 (1个)
│   └── capability_boundaries.prompt.j2
├── events/              # 📋 事件/Trace相关 (5个)
│   ├── action_summary.prompt.j2
│   ├── event_context.prompt.j2
│   ├── skill_error_details.prompt.j2
│   ├── system_tools.prompt.j2
│   └── trace_narrative.prompt.j2
├── fragments/           # 🧩 可复用片段 (17个)
│   ├── common/          # 通用组件
│   │   ├── action_docs.j2
│   │   ├── error_details.j2
│   │   ├── list_items.j2
│   │   └── macros.j2
│   ├── applescript_protocol.j2
│   ├── blackboard.j2
│   ├── env_awareness.j2
│   ├── knowledge_block.j2
│   ├── list_renderer.j2
│   ├── memory_replay.j2
│   ├── memory_section.j2
│   ├── mission_ticket.j2
│   ├── skill_catalog.j2
│   ├── spatial_awareness.j2
│   ├── summaries.j2
│   ├── system_rules.j2
│   └── user_preferences.j2
├── learning/            # 📚 学习/技能合成 (8个)
│   ├── multimodal_synthesis.prompt.j2
│   ├── multimodal_task_context.j2
│   ├── skill_discovery.prompt.j2
│   ├── skill_synthesis.prompt.j2
│   ├── smart_replay_macro.prompt.j2
│   ├── smart_replay_metadata.prompt.j2
│   ├── smart_replay_phases.prompt.j2
│   └── synthesis_human.prompt.j2
├── lsp/                 # 🔧 LSP相关 (2个)
│   ├── definitions.prompt.j2
│   └── diagnostics.prompt.j2
├── macro/               # ⚙️ 宏执行相关 (5个)
│   ├── analyze_results.prompt.j2
│   ├── check_redundancy.prompt.j2
│   ├── decide_next_step.prompt.j2
│   ├── is_failure_terminal.prompt.j2
│   └── verify_outcome.prompt.j2
├── memory/              # 🧠 记忆相关 (3个)
│   ├── atlas_detail.prompt.j2
│   ├── episodes_summary.prompt.j2
│   └── memory_consolidation.prompt.j2
├── planning/            # 📋 规划/分析 (6个)
│   ├── dynamic_app_triage.prompt.j2
│   ├── expert_roles.prompt.j2
│   ├── explorer_triage.prompt.j2
│   ├── feasibility_analysis.prompt.j2
│   ├── query_rewrite.prompt.j2
│   └── retrieval_results.prompt.j2
├── project/             # 📁 项目管理 (4个)
│   ├── document_content.prompt.j2
│   ├── project_management.prompt.j2
│   ├── project_state.prompt.j2
│   └── project_summary.prompt.j2
├── report/              # 📊 报告类 (5个)
│   ├── batch_summary.prompt.j2
│   ├── comparison.md.j2
│   ├── response.prompt.j2
│   ├── tool_outputs.prompt.j2
│   └── verification.md.j2
├── requirements/        # 📝 需求分析 (2个)
│   ├── analysis_prompt.j2
│   └── breakdown_prompt.j2
├── tool/                # 🛠️ 工具提示词 (4个)
│   ├── cypher_generation.prompt.j2
│   ├── git_harvest.prompt.j2
│   ├── orchestration_aggregate.prompt.j2
│   └── orchestration_decompose.prompt.j2
├── vision/              # 👁️ 视觉/多模态 (7个)
│   ├── elements_list.prompt.j2
│   ├── multimodal_frames.prompt.j2
│   ├── ocr_results.prompt.j2
│   ├── perceptions.prompt.j2
│   ├── vision.prompt.j2
│   ├── vision_analysis.prompt.j2
│   └── vision_context.prompt.j2
└── wiki/                # 📖 Wiki相关 (3个)
    ├── file_tree.prompt.j2
    ├── wiki.prompt.j2
    └── wiki_context.prompt.j2
```

## 统计

| 目录 | 模板数量 | 说明 |
|------|----------|------|
| agents | 5 | 核心Agent系统 |
| learning | 8 | 技能学习与合成 |
| vision | 7 | 视觉与多模态 |
| fragments | 17 | 可复用组件 |
| planning | 6 | 规划与分析 |
| codebase | 5 | 代码库分析 |
| events | 5 | 事件追踪 |
| report | 5 | 报告生成 |
| macro | 5 | 宏执行 |
| project | 4 | 项目管理 |
| tool | 4 | 工具调用 |
| wiki | 3 | 知识库 |
| memory | 3 | 记忆系统 |
| lsp | 2 | 语言服务器 |
| requirements | 2 | 需求分析 |
| autonomous | 1 | 自治任务 |
| environment | 1 | 环境感知 |

**总计: 17个目录，90个模板文件**
