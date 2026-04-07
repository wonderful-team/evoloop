# Memory Tools 测试文档

## 测试结构

```
tests/
├── unit/engine/tools/test_memory_tools.py    # 单元测试
├── integration/test_memory_tools.py           # 集成测试
└── integration/conftest.py                    # 集成测试配置
```

## 单元测试

测试内存工具的独立功能，使用 Mock 隔离依赖。

### 运行单元测试

```bash
cd evoloop/backend
python -m pytest tests/unit/engine/tools/test_memory_tools.py -v
```

### 单元测试覆盖

1. **TestRememberTool** - remember 工具测试
   - `test_remember_user_preference` - 用户偏好（PRIVATE/USER）
   - `test_remember_project_knowledge` - 项目知识（TEAM/PROJECT）
   - `test_remember_without_context` - 无上下文场景
   - `test_remember_with_long_content` - 长内容截断
   - `test_remember_error_handling` - 错误处理

2. **TestRecallTool** - recall 工具测试
   - `test_recall_with_results` - 正常召回
   - `test_recall_no_results_fallback_to_history` - 回退到对话历史
   - `test_recall_no_results_at_all` - 无结果场景
   - `test_recall_filters_private_memories` - 隐私过滤
   - `test_recall_error_handling` - 错误处理

3. **TestSearchHistoryTool** - search_history 工具测试
   - `test_search_history_with_results` - 正常搜索
   - `test_search_history_no_results` - 无结果
   - `test_search_history_no_thread` - 无活跃对话
   - `test_search_history_limits_results` - 结果限制

4. **TestMemoryToolsEdgeCases** - 边界情况
   - `test_remember_empty_content` - 空内容
   - `test_recall_with_special_characters` - 特殊字符
   - `test_preference_keywords_detection` - 偏好关键词检测

## 集成测试

测试工具与真实内存后端的集成（SQLite + 文件存储）。

### 运行集成测试

```bash
cd evoloop/backend
python -m pytest tests/integration/test_memory_tools.py -v --tb=short
```

### 集成测试覆盖

1. **TestRememberRecallIntegration** - 完整工作流
   - `test_full_remember_recall_cycle` - 记住→召回完整流程
   - `test_multiple_memories_recall` - 多条记忆过滤
   - `test_recall_across_users_privacy` - 跨用户隐私

2. **TestSearchHistoryIntegration** - 历史搜索集成
   - `test_search_history_with_stored_messages` - 存储后搜索
   - `test_search_history_no_matches` - 无匹配

3. **TestMemoryPersistence** - 持久化测试
   - `test_memory_persisted_to_file` - 文件持久化

4. **TestMemoryToolsErrorHandling** - 错误场景
   - `test_remember_with_invalid_context` - 无效上下文
   - `test_recall_with_database_error` - 数据库错误

5. **TestMemoryToolsSmoke** - 快速冒烟测试
   - `test_tools_are_callable` - 函数可调用
   - `test_input_models_are_valid` - 输入模型有效

## 运行所有测试

```bash
# 所有内存工具测试
python -m pytest tests/unit/engine/tools/test_memory_tools.py tests/integration/test_memory_tools.py -v

# 仅单元测试
python -m pytest tests/unit/engine/tools/test_memory_tools.py -v

# 仅集成测试
python -m pytest tests/integration/test_memory_tools.py -v

# 生成覆盖率报告
python -m pytest tests/unit/engine/tools/test_memory_tools.py --cov=app.core.engine.tools.memory_tools --cov-report=html
```

## 测试数据

- 单元测试：使用 Mock 对象，不依赖外部资源
- 集成测试：使用临时目录和 SQLite 内存/文件数据库，自动清理

## 注意事项

1. 集成测试需要完整的环境配置（但不会连接真实外部服务）
2. 测试使用临时目录，不会污染开发环境
3. 某些测试可能需要安装 pytest-asyncio: `pip install pytest-asyncio`
