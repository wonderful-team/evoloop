# Scripts 目录说明

**注意：此目录为 EvoLoop 内部实现，请使用 `evo` CLI 工具调用，不要直接执行这些脚本。**

---

## 目录结构

```
scripts/
├── *.sh              # Shell 脚本（将被 evo 整合）
├── *.py              # Python 工具脚本
├── test_*.py         # 测试脚本
├── demo_*.py         # 演示脚本
├── verify_*.py       # 验证脚本
└── verification/     # 验证工具子目录
```

---

## 为什么不直接删除 scripts/

scripts/ 目录包含 59+ 个功能脚本，是 evo CLI 的底层实现：

| 脚本类型 | 数量 | 说明 |
|---------|------|------|
| Python 工具 | 25+ | 核心功能实现（清理、重建、验证等）|
| 测试脚本 | 15+ | 各模块测试 |
| 演示脚本 | 6+ | 功能演示 |
| Shell 脚本 | 6 | 简单包装脚本 |
| 验证工具 | 10+ | 各类验证 |

**evo CLI 直接依赖这些脚本**，删除会导致功能失效。

---

## 使用方式

### ❌ 不要这样做

```bash
# 不要直接调用 scripts/ 中的脚本
python scripts/cleanup_system.py --all
python scripts/test_brain_full.py
bash scripts/start_worker.sh
```

### ✅ 正确做法

```bash
# 使用 evo CLI
bin/evo clean all
bin/evo brain test
bin/evo worker
```

---

## 可选优化方案

### 方案1：保持现状（推荐）

- scripts/ 作为底层实现保留
- evo CLI 统一调用
- 简单直接，无需改动

### 方案2：整合 Shell 脚本

将 `.sh` 脚本的功能整合到 evo 中：

| 当前 | 整合后 |
|------|--------|
| `start_worker.sh` | evo worker（直接调用 celery） |
| `format.sh` | evo format（直接调用 ruff） |
| `lint.sh` | evo lint（直接调用 ruff） |
| `prestart.sh` | evo db reset（内建逻辑） |
| `test.sh` | evo test cov（内建逻辑） |
| `check_code.sh` | evo check（内建逻辑） |

**优势**：
- 减少文件数量
- 逻辑更集中
- 更易维护

### 方案3：Python 包化

将常用功能整理为 Python 包：

```python
# evo/commands/cleanup.py
evo/commands/db.py
evo/commands/test.py
```

**优势**：
- 更好的代码组织
- 可测试性
- 可扩展性

---

## 结论

**不建议删除 scripts/ 目录**，因为：

1. evo CLI 依赖其中的 Python 脚本
2. 这些脚本包含复杂逻辑，不适合全部内建到 evo bash 脚本中
3. 保留可以方便高级用户自定义

**建议操作**：
- ✅ 使用 `evo` CLI 作为统一入口
- ⚠️ 可选：整合简单的 `.sh` 脚本到 evo
- ❌ 不要删除 scripts/ 目录
