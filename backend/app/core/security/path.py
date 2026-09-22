"""Centralized path safety helpers for tools and hooks.

This module provides a single source of truth for "which paths an Agent tool is
allowed to touch". The allowed roots are:

- the current thread/project working directory
- ``WORKSPACE_ROOT``（仅全局模式；项目会话激活时收窄，见下）
- the EvoLoop app data directory (``~/.evoloop``)
- any prefix configured in ``settings.ALLOWED_PATH_PREFIXES``（仅全局模式）

项目边界（2026-09-15 安全修复）：调用方提供 ``project_path``（即线程绑定了
具体项目）时，进入**项目作用域**——WORKSPACE_ROOT / ALLOWED_PATH_PREFIXES
不再整体放行，allowed roots 收敛为 ``working_dir + project_path + ~/.evoloop``。
跨项目/工作区访问必须经 authorization_gate 的 ``authorized_paths`` 授权
（HITL 批准后落盘 grant）方可放行。全局模式（未提供 project_path）保持
宿主运维语义不变。

Anything under ``~/.evoloop`` is treated as safe application data. Only
``.evoloop`` directories that live inside a project workspace are considered
project metadata and remain protected.
"""

from __future__ import annotations

import os
import re
import shlex

from app.core.config import settings
from app.core.project.utils import get_workspace_root


def _normalize_path(path: str) -> str:
    """Return a clean absolute path, expanding ``~`` and resolving symlinks."""
    try:
        return os.path.realpath(os.path.expanduser(path))
    except OSError:
        return os.path.abspath(os.path.expanduser(path))


def get_allowed_roots(
    working_dir: str | None = None,
    project_path: str | None = None,
    member_id: int | None = None,
) -> list[str]:
    """Build the list of directories tools are allowed to access.

    Only directories that actually exist on disk are returned, so callers don't
    accidentally whitelist a non-existent path.

    项目作用域：``project_path`` 非空（线程绑定项目）时，单用户模式**不再**
    放行全局 WORKSPACE_ROOT / ALLOWED_PATH_PREFIXES——它们是宿主运维语义；
    项目会话的边界收敛为 working_dir + project_path + ~/.evoloop，跨项目
    访问走 authorized_paths 授权。全局模式（project_path 为空）保持旧行为。

    多租户（MULTI_TENANT_MODE=true）下按用户隔离：
    - 工作根只允许 ``workspace/<member_id>``（A 用户看不到 B 的目录）；
    - 不再放行全局 WORKSPACE_ROOT / 全局 APP_DATA_DIR / ALLOWED_PATH_PREFIXES
      （宿主运维白名单是单用户运维模式语义，多租户下成员一律不具宿主权限）；
    - 覆盖面：member 根、member 上传目录、（指定/解析出的）project path。
    调用方传递 member_id 时优先，否则从执行上下文兜底；未知 member → 仅
    project path 与 working_dir 白名单有效（保守降级，禁全局根）。
    """
    from app.core.config import settings as _settings
    from app.core.project.utils import (
        current_member_id,
        resolve_member_workspace_root,
    )

    multi_tenant = _settings.MULTI_TENANT_MODE
    roots: set[str] = set()

    if working_dir and working_dir != ".":
        roots.add(_normalize_path(working_dir))

    if project_path:
        roots.add(_normalize_path(project_path))

    if not multi_tenant:
        roots.add(_normalize_path(settings.APP_DATA_DIR))

        # 项目作用域：项目会话激活时不放行全局宿主白名单（安全修复 2026-09-15）。
        # 全局模式（无 project_path）维持宿主运维语义。
        if not project_path:
            workspace_root = get_workspace_root()
            if workspace_root:
                roots.add(_normalize_path(workspace_root))

            for prefix in settings.ALLOWED_PATH_PREFIXES:
                roots.add(_normalize_path(prefix))
    else:
        member = member_id if member_id else current_member_id()
        member_root = resolve_member_workspace_root(member) if member else ""
        if member_root:
            roots.add(_normalize_path(member_root))
            # member 级上传目录（不存在则不加，返回值只含真实目录）
            upload_dir = os.path.join(member_root, "uploads")
            if os.path.isdir(upload_dir):
                roots.add(_normalize_path(upload_dir))

    return sorted(r for r in roots if os.path.isdir(r))


def is_under_allowed_root(
    path: str,
    *,
    allowed_roots: list[str] | None = None,
    working_dir: str | None = None,
) -> bool:
    """Return ``True`` if ``path`` lies within one of the allowed roots."""
    roots = (
        allowed_roots if allowed_roots is not None else get_allowed_roots(working_dir)
    )
    if not roots:
        return False

    resolved = _normalize_path(path)
    for root in roots:
        if resolved == root or resolved.startswith(root + os.sep):
            return True
    return False


def is_path_safe(
    path: str,
    *,
    working_dir: str | None = None,
    project_path: str | None = None,
    allowed_roots: list[str] | None = None,
) -> bool:
    """Check whether ``path`` is safe to access.

    Relative paths are resolved against ``working_dir`` first, matching the
    behavior of file tools and the authorization gate.
    """
    if not path:
        return False

    if working_dir and not os.path.isabs(path):
        candidate = os.path.join(_normalize_path(working_dir), os.path.expanduser(path))
    else:
        candidate = os.path.expanduser(path)

    roots = allowed_roots
    if roots is None:
        roots = get_allowed_roots(working_dir=working_dir, project_path=project_path)

    return is_under_allowed_root(candidate, allowed_roots=roots)


def is_project_metadata_path(path: str) -> bool:
    """Return ``True`` if ``path`` points to project-local metadata (``.evoloop``).

    The global app data directory ``~/.evoloop`` is explicitly **not** project
    metadata and returns ``False``.
    """
    if ".evoloop" not in path.lower():
        return False

    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        # A relative ``.evoloop`` reference is assumed to be inside the current
        # project/workspace and therefore protected.
        return True

    resolved = _normalize_path(expanded)
    app_data = _normalize_path(settings.APP_DATA_DIR)
    if resolved == app_data or resolved.startswith(app_data + os.sep):
        return False

    return True


def command_touches_project_metadata(command: str) -> bool:
    """Return ``True`` if shell ``command`` text references project-local metadata.

    ``execute_command`` carries paths as free-form text rather than structured
    fields, so tokens containing ``.evoloop`` are extracted (case-insensitive),
    shell metacharacters are stripped, and only path-like tokens are sent to
    :func:`is_project_metadata_path` for a verdict. The global app data directory
    ``~/.evoloop`` stays exempt via the shared predicate.
    """
    if not command or ".evoloop" not in command.lower():
        return False

    for token in re.findall(r"(?i)\S*\.evoloop\S*", command):
        cleaned = token.strip("'\"\\`;|&()[]{}<>$ \t\n")
        if _is_path_like_token(cleaned) and is_project_metadata_path(cleaned):
            return True
    return False


def _is_path_like_token(token: str) -> bool:
    """Return ``True`` if ``token`` looks like a filesystem path reference.

    避免把 ``echo foo.evoloop.bar`` 这类只是含 ``.evoloop`` 子串的普通词误判为路径。
    """
    if not token:
        return False
    if token.startswith(("/", "./", "../", "~/", "\\")):
        return True
    if "/" in token or "\\" in token:
        return True
    if token.startswith("."):
        return token.startswith(".evoloop") or token.startswith("..")
    return False


# ── 命令路径提取（authorization_gate 用）─────────────────────────────
# 缺陷背景：tests/e2e/defects/SECURITY_execute_command_path_bypass.md ——
# authorization_gate 只提取结构化 path 参数，Agent 可用 execute_command 的
# shell 命令（grep/ls/cat + 绝对路径）绕过文件工具边界读取任意目录。
# 此提取器把命令文本里"看起来像路径的参数"抽出来交回 gate 检查。
# 启发式、尽力而为：解析失败/不确定时宁可漏检也不误伤（安全兜底另有
# runner 层 has_workspace_escape 的 cd 硬拦与 is_dangerous_command）。

_COMMAND_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|&()`]")
_COMMAND_WORD_PRELUDE = frozenset(
    {"sudo", "env", "nohup", "time", "nice", "exec", "command", "builtin",
     "xargs", "timeout", "stdbuf"}
)
_REDIRECT_OPS = frozenset({">", ">>", "1>", "2>", "&>"})
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_TRAILING_SHELL_CHARS = ";&|"

# 段级写动词：这些命令（或经 xargs/sudo 透传）的路径参数是写/删语义，
# 不能再按 read 门控——否则 `rm /outside/x` 的审批卡显示"读取"，
# 用户按只读批准后实际执行删除（审批语义倒挂）。
_WRITE_VERB_COMMANDS = frozenset(
    {"rm", "mv", "cp", "rmdir", "chmod", "chown", "chgrp", "dd", "tee",
     "truncate", "shred", "unlink", "ln", "install", "mkdir", "touch"}
)


def _segment_effective_verb(tokens: list[str]) -> str:
    """取分段的有效命令动词：跳过 prelude（sudo/env/…）与 VAR=val 赋值。

    xargs 归入 prelude 但透传动词：``find … | xargs rm -rf /x`` 的有效动词
    是 rm（xargs 仅转发参数），因此 prelude 跳过后第一个真实命令字生效。
    """
    for tok in tokens:
        if tok in _COMMAND_WORD_PRELUDE:
            continue
        if _ENV_ASSIGN_RE.match(tok):
            continue
        return tok
    return ""


def _segment_writes(verb: str, tokens: list[str]) -> bool:
    """该分段是否为写/删语义（决定其路径参数的 action）。"""
    if not verb:
        return False
    if verb in _WRITE_VERB_COMMANDS:
        return True
    # sed 原地修改（-i / -i.bak）是写；普通 sed 是读。
    if verb == "sed":
        return any(t == "-i" or (t.startswith("-i") and len(t) > 2) for t in tokens)
    return False


def _clean_command_token(token: str) -> str:
    """剥除 token 两侧引号与尾部 shell 分隔符。"""
    return token.strip("\"'`").rstrip(_TRAILING_SHELL_CHARS).strip()


def _resolve_command_path(token: str, base_dir: str | None) -> str | None:
    """把命令 token 解析成绝对路径；无法安全解析时返回 None。

    与 ``_resolve_cd_target`` 同语义：相对路径必须有 base_dir 才可解析。
    """
    if not token:
        return None
    expanded = os.path.expanduser(token)
    if os.path.isabs(expanded):
        return _normalize_path(expanded)
    if base_dir:
        return _normalize_path(os.path.join(base_dir, expanded))
    return None


def extract_command_paths(
    command: str, base_dir: str | None = None
) -> list[tuple[str, str]]:
    """Extract filesystem paths referenced by a shell ``command`` string.

    Returns ordered, deduplicated ``(absolute_path, action)`` pairs where
    ``action`` is ``"read"`` for path arguments and ``"write"`` for redirect
    targets (``>`` / ``>>``). Used by the authorization gate to apply the same
    path boundary to shell commands as to structured file tools.

    尽力而为（best-effort）：无法解析的构造直接跳过，不抛异常——安全兜底
    由 runner 层 cd 硬拦与 is_dangerous_command 承担，此处只收增量覆盖。
    """
    if not command or not command.strip():
        return []

    candidates: list[tuple[str, str]] = []
    actions: dict[str, str] = {}

    def _add(raw_token: str, action: str) -> None:
        cleaned = _clean_command_token(raw_token)
        if not cleaned:
            return
        resolved = _resolve_command_path(cleaned, base_dir)
        if resolved is None:
            return
        existing = actions.get(resolved)
        if existing is None:
            actions[resolved] = action
            candidates.append((resolved, action))
        elif existing == "read" and action == "write":
            # 同一路径先读后写（cat /x && rm /x）：取更严格的 write，
            # 不得把已有的 write 降级回 read。
            actions[resolved] = "write"
            for idx, (path, _) in enumerate(candidates):
                if path == resolved:
                    candidates[idx] = (resolved, "write")
                    break

    for segment in _COMMAND_SEGMENT_SPLIT_RE.split(command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        if not tokens:
            continue

        # 段级读写判定：破坏性命令（rm/cp/sed -i/…）的路径参数按 write 门控。
        segment_verb = _segment_effective_verb(tokens)
        segment_writes = _segment_writes(segment_verb, tokens)
        # 有效命令动词的位置（VAR=val 仅在其之前视为环境赋值——
        # dd 的 if=/of= 操作数出现在动词之后，是路径而非赋值）。
        verb_index = next(
            (
                i
                for i, tok in enumerate(tokens)
                if tok not in _COMMAND_WORD_PRELUDE
                and not _ENV_ASSIGN_RE.match(tok)
            ),
            len(tokens),
        )

        skip_next_as_command = False
        after_double_dash = False
        for index, token in enumerate(tokens):
            if skip_next_as_command:
                skip_next_as_command = False
                continue
            # 段首与 prelude（sudo/env/…）后的 token 视为命令字，跳过
            if index == 0 or tokens[index - 1] in _COMMAND_WORD_PRELUDE:
                continue
            # 动词之前的 VAR=val 是环境赋值，不是路径
            if _ENV_ASSIGN_RE.match(token) and index < verb_index:
                continue

            # 重定向：独立操作符取下一个 token；粘连形式取剩余部分
            if token in _REDIRECT_OPS:
                if index + 1 < len(tokens):
                    _add(tokens[index + 1], "write")
                    skip_next_as_command = False
                continue
            if token.startswith(">>") and len(token) > 2:
                _add(token[2:], "write")
                continue
            if token.startswith(">") and len(token) > 1:
                _add(token[1:], "write")
                continue

            if token == "--":
                after_double_dash = True
                continue

            # flag：跳过本身；--opt=path 取 = 后的值参与检查
            if token.startswith("-") and not after_double_dash:
                if "=" in token:
                    _add(token.split("=", 1)[1], "write" if segment_writes else "read")
                continue

            # KEY=value 操作数（dd if=/a of=/b 风格）：取 = 后的绝对路径值。
            # 仅绝对/波浪线路径参与检查，避免普通词被误当相对路径。
            if "=" in token and not token.startswith("-"):
                val = token.split("=", 1)[1]
                if val.startswith("/") or val.startswith("~"):
                    _add(val, "write" if segment_writes else "read")
                continue

            cleaned = _clean_command_token(token)
            if not cleaned:
                continue
            if cleaned.startswith("/") or cleaned.startswith("~"):
                _add(cleaned, "write" if segment_writes else "read")
            elif "/" in cleaned:
                # 相对路径参数：有 base_dir 才能安全定位
                _add(cleaned, "write" if segment_writes else "read")

    return candidates
