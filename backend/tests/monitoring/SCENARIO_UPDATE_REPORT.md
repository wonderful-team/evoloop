# 测试场景更新报告

**更新时间**: 2026-03-22  
**旧场景数**: 172 个 → **新场景数**: 212 个 (+40)

---

## 1. 工具系统变更映射

### 1.1 重命名工具
| 旧名称 | 新名称 | 场景更新 |
|-------|-------|---------|
| `bash` | `execute_command` | ✅ 已更新 |
| `grep_files` | `search_code` | ✅ 已更新 |
| `list_files` | `list_directory` | ✅ 已更新 |
| `file_system` | `manage_directory` | ✅ 已更新 |
| `request_approval` | `ask_confirm` | ✅ 已更新 |
| `request_human_input` | `ask_human` | ✅ 已更新 |

### 1.2 consult_lsp 拆分
**旧**: `consult_lsp` - 通用 LSP 查询工具  
**新**: 6 个语义化工具

| 新工具 | 功能 | 典型场景 |
|-------|------|---------|
| `find_symbol` | 查找符号定义 | "查找 UserService 的定义" |
| `search_code` | 搜索代码模式 | "搜索所有调用 process_data 的地方" |
| `ask_codebase` | 语义化问答 | "解释这个仓库的架构" |
| `analyze_impact` | 变更影响分析 | "分析修改这个类的影响" |
| `check_types` | 类型检查 | "检查这个文件的类型错误" |
| `inspect_symbol` | 符号详情 | "查看这个函数的实现" |

### 1.3 manage_memory 拆分
**新工具**: `search_history`, `save_preference`, `add_concept`, `save_concepts`, `find_related_episodes`

### 1.4 manage_todo 拆分
**新工具**: `create_todo`, `list_todos`

---

## 2. 新增测试类别

### 2.1 code_exploration (23 个场景)
- ✅ 符号查找测试
- ✅ 代码搜索测试
- ✅ 语义查询测试
- ✅ 影响分析测试
- ✅ 类型检查测试

### 2.2 edit_validation (4 个场景)
- ✅ 预览编辑测试 (dry_run)
- ✅ 自动类型检查 (verify_types)
- ✅ 修复类型错误场景
- ✅ 复杂编辑验证

### 2.3 memory_knowledge (5 个场景)
- ✅ 搜索历史测试
- ✅ 保存偏好测试
- ✅ 概念关联测试

### 2.4 task_management (4 个场景)
- ✅ 创建待办测试
- ✅ 列表达成测试

### 2.5 checkpoint (4 个场景)
- ✅ 检查点 CRUD 测试

---

## 3. 多轮对话增强

### 新增 55 轮电商系统构建场景
覆盖从需求分析到部署的完整开发流程：
1. **需求理解**: 分析电商系统需求
2. **系统设计**: 数据库、API、架构设计
3. **开发实现**: 用户、订单、支付模块
4. **测试验证**: 单元测试、集成测试
5. **部署上线**: Docker、CI/CD 配置

---

## 4. 测试框架增强

### 4.1 ErrorCollector 错误收集
```python
error_collector.add_error(
    step_type="code_exploration",
    error_msg="Tool not found: find_symbol",
    severity="HIGH"
)
```

### 4.2 LoopDetector 循环检测
- 检测连续重复节点
- 检测异常高迭代次数
- 自动生成错误报告

### 4.3 Historical Cleanup
```python
clean_historical_burden()
# 清理: checkpoints, task_logs, todo_lists, LanceDB, 缓存
```

### 4.4 Resume Capability
```bash
# 从中断处恢复
python test_with_scenarios.py --start 100
```

---

## 5. 测试统计

| 类别 | 场景数 | 占比 |
|-----|-------|------|
| multi_turn | 66 | 31.1% |
| code_exploration | 23 | 10.8% |
| file_operation | 12 | 5.7% |
| android_control | 12 | 5.7% |
| knowledge_query | 10 | 4.7% |
| code_generation | 8 | 3.8% |
| code_optimization | 8 | 3.8% |
| debugging | 8 | 3.8% |
| browser_automation | 8 | 3.8% |
| desktop_control | 8 | 3.8% |
| ambiguous | 8 | 3.8% |
| edge_case | 8 | 3.8% |
| dangerous_operation | 6 | 2.8% |
| reference_previous | 6 | 2.8% |
| memory_knowledge | 5 | 2.4% |
| complex_task | 4 | 1.9% |
| edit_validation | 4 | 1.9% |
| task_management | 4 | 1.9% |
| checkpoint | 4 | 1.9% |
| **总计** | **212** | **100%** |

---

## 6. 运行指南

```bash
# 完整测试
python tests/monitoring/test_with_scenarios.py

# 仅测试新工具场景
python tests/monitoring/test_with_scenarios.py --category code_exploration
python tests/monitoring/test_with_scenarios.py --category edit_validation
python tests/monitoring/test_with_scenarios.py --category memory_knowledge
python tests/monitoring/test_with_scenarios.py --category task_management
python tests/monitoring/test_with_scenarios.py --category checkpoint

# 快速验证 (每类限制5个)
python tests/monitoring/test_with_scenarios.py --max 5

# 指定起始位置
python tests/monitoring/test_with_scenarios.py --start 50
```

---

## 7. 后续建议

### 7.1 待优化项
- [ ] 为 `verify_types` 场景添加 mock 类型错误数据
- [ ] 为 `find_symbol` 添加 Graph/LSP/Grep 后端选择验证
- [ ] 为 `ask_codebase` 添加多文档引用场景

### 7.2 扩展方向
- [ ] 添加代码重构场景 (refactoring)
- [ ] 添加性能分析场景 (profiling)
- [ ] 添加代码审查场景 (code_review)
- [ ] 添加更多边界条件测试

---

**更新完成**: 测试场景已完整支持新工具系统，涵盖 19 个类别共 212 个测试用例。
