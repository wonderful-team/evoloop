# EvoLoop Scripts 目录分析

## 概述

`scripts/` 目录包含 59+ 个脚本，用于开发、测试、清理、验证和演示。以下按功能分类梳理。

---

## 分类索引

### 1. 开发工具 (Development Tools)

| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `prestart.sh` | 数据库启动前初始化 (检查/迁移/初始数据) | `make db-reset` |
| `start_worker.sh` | 启动 Celery Worker | `make worker` |
| `format.sh` | 代码格式化 (ruff) | `make format` |
| `lint.sh` | 代码检查 (ruff) | `make lint` |
| `check_code.sh` | 全面代码检查 (ruff + pyright) | `make check` |
| `test.sh` | 运行测试并生成覆盖率报告 | `make test-cov` |

### 2. 数据库管理 (Database)

| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `init_test_db.py` | 初始化测试数据库 (删表重建) | `make db-init` |
| `seed_test_data.py` | 填充测试数据 | `make db-seed` |
| `reset_and_rebuild.py` | 清空并重建知识库索引 | `make kb-reset` |
| `reindex_all.py` | 重新索引所有项目 | `make kb-reindex` |
| `reset_vectors.py` | 重置向量数据 | `make reset-vectors` |
| `fix_vector_dims.py` | 修复向量维度问题 | `make fix-vector-dims` |
| `update_vector_dims.py` | 更新向量维度配置 | - |
| `reset_kb.py` | 重置知识库 | - |

**使用建议：**
- 日常开发：`make kb-rebuild` (仅重建索引，不清空)
- 彻底重置：`make kb-reset` (清空+重建)
- 维度问题：`make fix-vector-dims`

### 3. 系统清理 (Cleanup)

| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `cleanup_system.py` | 完整系统清理 (Redis/Neo4j/PostgreSQL/文件) | `make clean-all` |
| `cleanup_runtime.py` | 运行时清理 (Redis/Celery队列) | `make clean` |
| `clear_atlas.py` | 清空 Atlas 数据 | `make atlas-clear` |
| `clear_non_index_graph_data.py` | 清空非索引图数据 | - |

**使用建议：**
- 快速清理：`make clean` (只清缓存)
- 完整重置：`make clean-all` (⚠️ 危险：会删除所有数据)
- 预览模式：`make clean-dry`

### 4. 存储管理 (Storage)

| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `manage_screenshots.py` | 统一管理截图和录制 | `make storage-stats` |

**子命令：**
```bash
# 查看统计
python scripts/manage_screenshots.py stats
python scripts/manage_screenshots.py stats --screenshots
python scripts/manage_screenshots.py stats --recordings

# 清理过期文件
python scripts/manage_screenshots.py cleanup          # 实际清理
python scripts/manage_screenshots.py cleanup --dry-run  # 预览

# 查看配置
python scripts/manage_screenshots.py config

# 测试存储功能
python scripts/manage_screenshots.py test
```

### 5. 测试脚本 (Testing)

#### 5.1 Brain 测试
| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `test_brain_full.py` | Brain 完整测试套件 | `make brain-test` |
| `test_brain_real.py` | Brain 实机测试 | `make brain-real` |
| `test_brain_letta.py` | Brain Letta 集成测试 | `make brain-letta` |
| `brain_full_suite.py` | Brain 全面测试 | - |

#### 5.2 Atlas 测试
| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `test_atlas_e2e.py` | Atlas 端到端测试 | `make atlas-test` |
| `test_atlas_mobile.py` | Atlas 移动端测试 | `make atlas-mobile` |
| `test_atlas_batch_20apps.py` | Atlas 批量应用测试 | - |
| `test_atlas_phase6.py` | Atlas Phase6 测试 | - |

#### 5.3 功能测试
| 脚本 | 功能 |
|------|------|
| `test_element_classification.py` | 元素分类测试 |
| `test_open_app_with_type.py` | 应用类型打开测试 |
| `test_wechat_ui_summary.py` | 微信 UI 摘要测试 |
| `e2e_ai_test.py` | AI 端到端测试 |
| `test_todo_feature.py` | Todo 功能测试 |

### 6. 验证脚本 (Verification)

位于 `verification/` 子目录：

| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `verify_skill_execution.py` | 验证技能执行 | `make verify-skill` |
| `verify_resources.py` | 验证资源管理 | - |
| `verify_synthesis.py` | 验证合成功能 | - |

独立验证脚本：

| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `verify_storage.py` | 验证存储系统 | `make verify-storage` |
| `verify_vector_opt.py` | 验证向量优化 | `make verify-vector` |
| `verify_peekaboo.py` | 验证 Peekaboo | `make verify-peekaboo` |
| `verify_deep_resolution.py` | 验证深度解析 | - |
| `verify_screenshot_fix.py` | 验证截图修复 | - |
| `verify_parameter_fix.py` | 验证参数修复 | - |
| `verify_shortcuts.py` | 验证快捷方式 | - |
| `verify_dynamic_security.py` | 验证动态安全 | - |
| `verify_new_providers.py` | 验证新 Provider | - |
| `verify_wiki_flow.py` | 验证 Wiki 流程 | - |
| `verify_agent_todo.py` | 验证 Agent Todo | - |
| `verify_agent_proactive_todo.py` | 验证主动 Todo | - |

### 7. 演示脚本 (Demo)

| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `demo_final.py` | 最终演示 | `make demo-final` |
| `demo_phase3.py` | 阶段3演示 | `make demo-phase3` |
| `demo_mobile_reactor.py` | 移动端演示 | `make demo-mobile` |
| `demo_resolve_element.py` | 元素解析演示 | - |
| `demo_window_management.py` | 窗口管理演示 | - |
| `demo_semantic_ids.py` | 语义 ID 演示 | - |

### 8. 调试/分析工具 (Debug/Analysis)

| 脚本 | 功能 | Makefile 命令 |
|------|------|--------------|
| `debug_messages.py` | 调试消息 | `make debug` |
| `analyze_loop.py` | 分析循环 | `make analyze` |
| `chat_client.py` | 聊天客户端 | - |
| `query_android_layouts.py` | 查询 Android 布局 | - |
| `compare_ax_ocr.py` | 比较 OCR 结果 | - |
| `extract_llm_config.py` | 提取 LLM 配置 | `make extract-config` |
| `check_skill_params.py` | 检查技能参数 | `make check-skills` |
| `check_embedding_config.py` | 检查嵌入配置 | - |
| `check_imports.py` | 检查导入 | - |
| `reproduce_1214.py` | 重现问题 #1214 | - |
| `simulate_ticket_scenario.py` | 模拟工单场景 | - |

### 9. 数据插入脚本 (Data Seeding)

| 脚本 | 功能 |
|------|------|
| `insert_bt_restart_skill.py` | 插入蓝牙重启技能 |
| `insert_google_search_skill.py` | 插入谷歌搜索技能 |

---

## 使用场景速查

### 场景1：全新环境搭建
```bash
make install      # 安装依赖
make db-init      # 初始化数据库
make db-seed      # 填充测试数据
make kb-reset     # 建立知识库索引
```

### 场景2：日常开发
```bash
make dev          # 启动服务器 (终端1)
make worker       # 启动 Worker (终端2)
make lint         # 代码检查
make format       # 格式化
```

### 场景3：测试验证
```bash
make test         # 运行单元测试
make test-e2e     # 运行端到端测试
make brain-test   # 测试 Brain
make atlas-test   # 测试 Atlas
```

### 场景4：问题排查
```bash
make clean        # 清理运行时缓存
make verify       # 查看可用验证命令
make analyze      # 分析系统状态
make debug        # 调试消息
```

### 场景5：存储清理
```bash
make storage-stats   # 查看存储使用
make storage-clean   # 清理过期文件
make clean-sc        # 快捷清理截图
```

### 场景6：知识库维护
```bash
make kb-clean        # 仅清空索引
make kb-rebuild      # 仅重建索引
make kb-reset        # 清空+重建
```

---

## 命令快速参考卡

```
╔══════════════════════════════════════════════════════════════╗
║                    EvoLoop 常用命令                           ║
╠══════════════════════════════════════════════════════════════╣
║  开发: make dev / make worker / make install                 ║
║  代码: make lint / make format / make check / make fix       ║
║  测试: make test / make test-cov / make test-e2e             ║
║  数据库: make db-reset / make db-seed / make db-migrate      ║
║  知识库: make kb-reset / make kb-clean / make kb-rebuild     ║
║  清理: make clean / make clean-all / make clean-dry          ║
║  存储: make storage-stats / make storage-clean               ║
║  验证: make verify-skill / make verify-storage               ║
╚══════════════════════════════════════════════════════════════╝
```
