# Scripts 目录清理方案

## 分析总结

scripts/ 目录共有 **59+ 个文件**，经过分析，可以安全清理或整合的文件如下：

---

## 一、可安全删除的文件（17个）

### 1. 报告/临时文件（1个）

| 文件 | 原因 | 操作 |
|------|------|------|
| `atlas_batch_test_report.txt` | 临时测试报告，已过期 | **删除** |

### 2. 简单 Shell 脚本（6个）→ 整合到 evo

这些脚本功能简单，已整合到 evo CLI 中：

| 文件 | 功能 | 操作 |
|------|------|------|
| `format.sh` | ruff 格式化 | **删除**，evo 已内建 |
| `lint.sh` | ruff 检查 | **删除**，evo 已内建 |
| `test.sh` | 测试+覆盖率 | **删除**，evo 已内建 |
| `check_code.sh` | 代码检查 | **删除**，evo 已内建 |
| `prestart.sh` | 数据库初始化 | **删除**，evo 已内建 |
| `start_worker.sh` | 启动 worker | **删除**，evo 已内建 |

### 3. 过时/一次性脚本（5个）

| 文件 | 原因 | 操作 |
|------|------|------|
| `check_imports.py` | 一次性导入检查，已完成使命 | **删除** |
| `reproduce_1214.py` | 问题复现脚本（#1214） | **删除**（如问题已修复） |
| `extract_llm_config.py` | 一次性配置提取 | **归档/删除** |
| `check_embedding_config.py` | 配置检查，已过时 | **删除** |
| `update_vector_dims.py` | 向量维度更新（一次性） | **归档/删除** |

### 4. 重复/功能重叠脚本（2个）

| 文件 | 原因 | 操作 |
|------|------|------|
| `reset_kb.py` | 功能被 `reset_and_rebuild.py` 覆盖 | **删除** |
| `tests-start.sh` | 被 `test.sh` 覆盖 | **删除** |

### 5. 调试/临时脚本（3个）

| 文件 | 原因 | 操作 |
|------|------|------|
| `chat_client.py` | 简单 HTTP 客户端，可用 curl/postman 替代 | **删除** |
| `simulate_ticket_scenario.py` | 特定场景模拟 | **归档到 tests/manual/** |
| `debug_messages.py` | 调试脚本 | **保留**（有用）或 **归档** |

---

## 二、需要保留的核心文件（36个）

### 1. 系统清理/维护（8个）✅ 保留

```
cleanup_system.py       # 全能清理工具
cleanup_runtime.py      # 运行时清理
clear_atlas.py          # Atlas 数据清理
clear_non_index_graph_data.py  # 图数据清理
reset_and_rebuild.py    # 知识库重建
reset_vectors.py        # 向量重置
fix_vector_dims.py      # 向量维度修复
manage_screenshots.py   # 存储管理
```

### 2. 测试脚本（15个）✅ 保留

```
test_atlas_*.py         # 4个 Atlas 测试
test_brain_*.py         # 3个 Brain 测试
test_element_classification.py
test_open_app_with_type.py
test_wechat_ui_summary.py
test_todo_feature.py
e2e_ai_test.py
brain_full_suite.py
```

### 3. 演示脚本（6个）✅ 保留

```
demo_*.py               # 6个演示脚本
```

### 4. 验证脚本（10个）✅ 保留

```
verify_*.py             # 10个验证脚本
verification/*.py       # 3个子目录验证脚本
```

### 5. 数据插入（2个）✅ 保留

```
insert_bt_restart_skill.py
insert_google_search_skill.py
```

### 6. 分析工具（2个）✅ 保留

```
analyze_loop.py         # 循环分析
query_android_layouts.py # Android 布局查询
compare_ax_ocr.py       # OCR 比较
```

---

## 三、推荐目录结构

清理后的 scripts/ 目录：

```
scripts/
├── README.md                    # 目录说明
│
├── system/                      # 系统维护
│   ├── cleanup_system.py
│   ├── cleanup_runtime.py
│   ├── clear_atlas.py
│   ├── clear_non_index_graph_data.py
│   ├── reset_and_rebuild.py
│   ├── reset_vectors.py
│   └── fix_vector_dims.py
│
├── storage/                     # 存储管理
│   └── manage_screenshots.py
│
├── tests/                       # 测试脚本
│   ├── test_atlas_*.py
│   ├── test_brain_*.py
│   ├── test_*.py
│   └── e2e_ai_test.py
│
├── demos/                       # 演示脚本
│   └── demo_*.py
│
├── verify/                      # 验证工具
│   ├── verify_*.py
│   └── internal/                # 原 verification/
│       └── *.py
│
├── seed/                        # 数据插入
│   ├── insert_*.py
│   └── seed_test_data.py
│
└── utils/                       # 工具/分析
    ├── analyze_loop.py
    ├── query_android_layouts.py
    └── compare_ax_ocr.py
```

---

## 四、执行步骤

### Step 1: 备份（重要！）
```bash
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
git add -A
git commit -m "backup: before scripts cleanup"
```

### Step 2: 创建归档目录
```bash
mkdir -p scripts/archive
mkdir -p scripts/tests/manual
```

### Step 3: 移动可归档文件
```bash
# 一次性/临时脚本归档
mv scripts/reproduce_1214.py scripts/archive/
mv scripts/extract_llm_config.py scripts/archive/
mv scripts/update_vector_dims.py scripts/archive/
mv scripts/simulate_ticket_scenario.py scripts/tests/manual/
```

### Step 4: 删除冗余文件
```bash
# 报告文件
rm scripts/atlas_batch_test_report.txt

# 简单 shell 脚本（已整合到 evo）
rm scripts/format.sh
rm scripts/lint.sh
rm scripts/test.sh
rm scripts/check_code.sh
rm scripts/prestart.sh
rm scripts/start_worker.sh
rm scripts/tests-start.sh

# 过时脚本
rm scripts/check_imports.py
rm scripts/check_embedding_config.py
rm scripts/reset_kb.py
rm scripts/chat_client.py
```

### Step 5: 可选 - 重组织目录
```bash
# 如果需要更好的组织，可以创建子目录并移动文件
mkdir -p scripts/{system,storage,tests,demos,verify,seed,utils}
# ... 移动文件
```

---

## 五、清理后统计

| 类别 | 当前 | 清理后 | 减少 |
|------|------|--------|------|
| 总文件数 | 59+ | ~42 | ~28% |
| Shell 脚本 | 8 | 0 | 100% |
| Python 脚本 | 51+ | ~42 | ~18% |

---

## 六、注意事项

1. **先备份再操作** - 所有删除操作前确保已 git commit
2. **验证 evo 功能** - 删除 shell 脚本后，验证 evo 命令正常工作
3. **归档而非删除** - 不确定的文件先归档，观察一段时间后再删除
4. **团队协作** - 重大结构调整需团队确认
