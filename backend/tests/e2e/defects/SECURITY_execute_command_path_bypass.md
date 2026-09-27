# 安全缺陷记录：execute_command 可绕过文件路径边界

## 发现时间
2026-08-15 06:20（值守模式 HITL 自动拒绝功能验证时实测确认）

## 问题描述

值守模式下，Agent 越界访问工作目录外路径（如 `~/www/mall-backend`）时，
`authorization_gate` 会拦截 `list_dir` 等文件工具（本次新增的 duty 自动拒绝
分支生效）。但 Agent 可**改用 `execute_command` 执行 shell 命令绕过**：

```
execute_command | Args: {"command": "ls -la /Users/huangjinhuan/www/mall-backend 2>&1 | head -50"}
```

实测：`list_dir ~/www/mall-backend` 被自动拒绝（list_dir 未执行），但
`execute_command: ls -la ~/www/mall-backend` **成功执行并返回目录内容**。

## 根因

1. `authorization_gate._extract_path_from_input`（app/core/engine/hooks/authorization.py:45-65）
   只从工具参数中提取 `path` / `TargetFile` / `AbsolutePath` / `SearchPath` /
   `DirectoryPath` / `TargetDirectory` 等 key，**不解析 `command` 文本中的路径**。
2. `is_dangerous_command`（app/domain/tools/execution/security.py）只拦截危险命令
   （rm -rf / 等），**不检查命令访问的路径是否在工作目录内**。
3. `execute_command`（app/domain/tools/execution/execute.py）无路径边界校验，
   cwd 限制（background.py 的 working_dir）不阻止显式绝对路径访问。

## 影响

- 值守模式自动拒绝只拦文件工具，Agent 可用 shell 命令读取越界路径内容。
- 安全边界存在绕过缺口，工作目录外的文件可被 Agent 通过命令工具访问。

## 建议修复方向（待处理）

1. **解析命令路径**：authorization_gate 对 `execute_command` 解析 command 中的
   路径参数（如 `ls/cat/read/head` 后的路径），越界则同样拦截（duty 自动拒绝，
   非 duty 弹 HITL）。
2. **限制 cwd 边界**：execute_command 校验命令访问路径必须在项目工作目录内。
3. **不处理危险命令清单**：is_dangerous_command 已有安全基础，扩展路径校验即可。

## 状态
- [x] 已修复（2026-09-15）

### 修复内容

1. **命令路径提取**（`app/core/security/path.py::extract_command_paths`）：
   authorization_gate 对 execute_command 命令文本提取路径参数（绝对路径 /
   ~/ 相对路径 / 重定向目标 / flag=值），与结构化 path 参数套用同一边界；
   越界 → HITL 授权（值守线程同样走 HITL，docker 模式沙箱兜底自动批准）。
   启发式尽力而为：命令字（含绝对路径二进制）、sudo/env 前缀、flag、
   VAR=val 赋值跳过；引号路径、多段 &&/;/| 命令支持。
2. **项目作用域边界**（`app/core/security/path.py::get_allowed_roots`）：
   project_path 激活（线程绑定项目）时 WORKSPACE_ROOT / ALLOWED_PATH_PREFIXES
   不再整体放行，边界收敛为 working_dir + project_path + ~/.evoloop；
   跨项目/工作区访问必须经 authorized_paths 授权。全局模式行为不变。
3. **执行层同源收窄**（`runner.py::_resolve_working_dir`）：项目会话下
   has_workspace_escape 的 cd 逃逸检查同样按项目作用域边界判定。

测试：`tests/unit/core/security/test_path.py::TestExtractCommandPaths`、
`TestGetAllowedRoots::test_project_scope_excludes_workspace_root`、
`TestIsPathSafe::test_project_scope_blocks_workspace_sibling`、
`tests/unit/core/engine/hooks/test_authorization_hooks.py::TestAuthorizationGateCommandPaths`。
