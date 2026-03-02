# Scripts 目录清理完成报告

## 执行时间
2026-03-03

## 清理统计

| 类别 | 清理前 | 清理后 | 变化 |
|------|--------|--------|------|
| Python 脚本 | ~53 | 50 | -3 |
| Shell 脚本 | 8 | 0 | -8 |
| 临时文件 | 1 | 0 | -1 |
| **总计** | **~63** | **50** | **-13** |

## 已删除文件（18个）

### 根目录脚本
- `run_tests.sh` - 过时测试脚本（引用不存在文件）

### 临时文件
- `atlas_batch_test_report.txt`

### Shell 脚本（已整合到 evo）
- `format.sh` → `evo format`
- `lint.sh` → `evo lint`
- `test.sh` → `evo test cov`
- `check_code.sh` → `evo check`
- `prestart.sh` → `evo db reset` (逻辑内联)
- `start_worker.sh` → `evo worker`
- `tests-start.sh` → `evo test`

### 过时/重复脚本
- `check_imports.py` - 一次性导入检查
- `check_embedding_config.py` - 过时配置检查
- `reset_kb.py` - 功能被 `reset_and_rebuild.py` 覆盖
- `chat_client.py` - 简单 HTTP 客户端

## 已归档文件（4个）

移动到 `scripts/archive/`:
- `reproduce_1214.py` - 问题复现脚本
- `extract_llm_config.py` - 配置提取工具
- `update_vector_dims.py` - 向量维度更新

移动到 `scripts/tests/manual/`:
- `simulate_ticket_scenario.py` - 场景模拟脚本

## 目录结构

```
scripts/
├── README.md                    # 目录说明
├── archive/                     # 归档文件
│   ├── extract_llm_config.py
│   ├── reproduce_1214.py
│   └── update_vector_dims.py
├── tests/
│   └── manual/
│       └── simulate_ticket_scenario.py
└── [50个核心脚本保留]
```

## 更新内容

1. **evo CLI** (`bin/evo`)
   - 移动到 `bin/evo`
   - 更新 `evo db reset` 命令，内联 prestart.sh 逻辑
   - 所有 shell 脚本功能已内建

2. **文档**
   - `docs/EVO_CLI.md` - 更新安装路径
   - `docs/SCRIPTS_CLEANUP_PLAN.md` - 清理计划
   - `docs/SCRIPTS_CLEANUP_DONE.md` - 本报告

## 验证

```bash
# 测试 evo CLI 正常工作
bin/evo help

# 验证清理结果
ls scripts/*.sh          # 应该无结果
ls scripts/archive/      # 显示归档文件
```

## Git 提交

```
commit 1888187
cleanup: reorganize scripts directory

- Move evo CLI to bin/evo
- Remove redundant shell scripts
- Remove obsolete Python scripts
- Remove duplicate scripts
- Archive temporary scripts
- Update evo CLI to inline prestart.sh logic
- Update documentation
```

## 后续建议

如需进一步精简，可考虑：
1. 将 `scripts/verification/` 整合到 `evo verify` 命令
2. 将常用演示脚本整合到 `evo demo` 命令
3. 定期清理 `scripts/archive/` 中确认不再需要的文件
