"""
Authorization gate hook.

Replaces the hard-coded sensitive_file_protection_gate with a project-configurable
policy engine that escalates to HITL approval instead of blindly blocking.

EXECUTION_MODE=docker 时，工作区外文件访问由沙箱容器隔离兜底，不再发起 HITL
（项目 .evoloop 元数据与 project.json 策略仍强制生效）。
"""

import logging
import os
from datetime import datetime, timezone

from app.core.context.thread_store import thread_context_store
from app.core.engine.hooks.core import HookContext, HookEvent, HookResult, hook_system
from app.core.engine.hooks.schemas import ToolInput
from app.core.hitl.authorization import AuthorizationDecision, AuthorizationService
from app.core.hitl.core import hitl_enabled
from app.core.hitl.orchestrator import HITLOrchestrator
from app.core.hitl.policies import AuthorizationPolicy
from app.core.project.utils import get_project_path
from app.core.security.path import extract_command_paths, is_path_safe
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


def _extract_path_from_input(
    tool_name: str, tool_input: ToolInput | None
) -> tuple[str, str] | None:
    if tool_input is None:
        return None
    path = tool_input.path
    action = "write" if "write" in tool_name or "replace" in tool_name else "read"
    if path:
        return str(path), action
    if tool_input.args:
        for key in (
            "TargetFile",
            "AbsolutePath",
            "SearchPath",
            "DirectoryPath",
            "TargetDirectory",
            "path",
        ):
            val = tool_input.args.get(key)
            if val and isinstance(val, str):
                return val, action
    return None


def _is_path_safe(
    path_str: str, project_path: str | None, working_directory: str | None = None
) -> bool:
    """Delegate to the centralized path safety helper."""
    return is_path_safe(
        path_str,
        working_dir=working_directory,
        project_path=project_path,
    )


@hook_system.register(HookEvent.PRE_TOOL_USE, matcher=".*", priority=1)
async def authorization_gate(context: HookContext) -> HookResult:
    """
    Project-level authorization gate.

    Runs before every tool use with the highest priority. If the tool touches a
    sensitive resource defined in the project's .evoloop/project.json, and the user
    has not already granted permission, it raises a HITL authorization request.
    """
    # Project metadata is always protected (no HITL escalation), 与项目/全局无关。
    # 必须早于全局早退执行：否则全局模式（project_id 为空）下，execute_command
    # 命令文本里的 .evoloop 引用将无人拦截（LocalSandbox 无 OS 隔离）。
    if context.tool_input is not None and context.tool_input.touches_project_metadata():
        return HookResult(
            block=True,
            message=i18n.get("engine.authorization.metadata_access_prohibited"),
        )

    if not context.project_id:
        # Global mode: no project-specific authorization policies
        return HookResult(success=True)

    auth_service = AuthorizationService(context.project_id)
    decision = await auth_service.evaluate(
        tool_name=context.tool_name or "",
        tool_input=context.tool_input,
    )

    # Extra CowAgent-inspired Safety Boundary check for file tools AND shell
    # command path arguments（缺陷 SECURITY_execute_command_path_bypass：Agent
    # 可用 execute_command 的 grep/ls/cat + 绝对路径绕过文件工具边界）。
    candidates: list[tuple[str, str]] = []
    extra_paths: list[tuple[str, str]] | None = None
    extracted = _extract_path_from_input(context.tool_name or "", context.tool_input)
    if extracted is not None:
        candidates.append(extracted)

    # 命令文本路径提取（尽力而为）：相对 token 以线程工作目录解析。
    # 注意：execute_command 通常没有结构化 path 参数，candidates 初始为空，
    # 必须以 command 文本存在作为进入条件，不能挂在 extracted 结果之下。
    command: str | None = None
    if context.tool_input is not None:
        command = context.tool_input.command
        if not command and context.tool_input.args:
            arg_command = context.tool_input.args.get("command")
            if isinstance(arg_command, str):
                command = arg_command
    has_command = bool(command and command.strip())

    if candidates or has_command:
        try:
            project_path = await get_project_path(context.project_id)
        except Exception:
            project_path = None

        try:
            working_directory = thread_context_store.get_working_directory(
                context.thread_id
            )
        except Exception:
            working_directory = None

        if has_command:
            candidates.extend(
                extract_command_paths(command, base_dir=working_directory)
            )

        if candidates:
            # Make sure we load granted permissions
            await auth_service._load()
            now = datetime.now(timezone.utc)
            # 同一次调用的全部待授权候选（复合命令多路径）：审批须覆盖全量，
            # 只授权首个路径会让重执行在下一个未授权路径上再次弹审批。
            pending_paths: list[tuple[str, str]] = []
            for resource_path, action in candidates:
                if _is_path_safe(resource_path, project_path, working_directory):
                    continue

                # Check if this permission was already granted previously
                is_already_granted = False
                for grant in auth_service._granted or []:
                    if grant.action != action:
                        continue
                    if not grant.is_expired(now):
                        # 作用域匹配：prefix 授权命中目录及全部子路径
                        # （grant_mode=dir 落盘）；exact 精确相等（含相对路径变换）。
                        scope = getattr(grant, "scope_type", "exact") or "exact"
                        if scope == "prefix":
                            import os as _os

                            base = _os.path.realpath(_os.path.expanduser(grant.path))
                            target = _os.path.realpath(
                                _os.path.expanduser(resource_path)
                            )
                            if target == base or target.startswith(base + os.sep):
                                is_already_granted = True
                                break
                            continue
                        check_paths = [resource_path]
                        if project_path and os.path.isabs(resource_path):
                            try:
                                rel = os.path.relpath(resource_path, project_path)
                                if not rel.startswith(".."):
                                    check_paths.append(rel)
                            except Exception as e:
                                logger.debug("Suppressed error: %s", e, exc_info=True)
                        if grant.path in check_paths:
                            is_already_granted = True
                            break

                if is_already_granted:
                    continue

                # 拒绝即判死（防 ping-pong）：用户已拒绝过同线程同资源的访问，
                # 后续重试直接硬拒绝（不新建 HumanRequest 打扰用户）。
                # 查询异常降级为"未拒绝过"，保持 HITL 链路可用（fail-open to HITL）。
                try:
                    previously_rejected = await HITLOrchestrator.has_thread_resource_rejection(
                        context.thread_id, resource_path
                    )
                except Exception:
                    logger.exception(
                        "[AuthorizationGate] rejection lookup failed (thread=%s)",
                        context.thread_id,
                    )
                    previously_rejected = False

                if previously_rejected:
                    decision = AuthorizationDecision(
                        approved=False,
                        requires_hitl=False,
                        reason=i18n.get(
                            "engine.authorization.previously_rejected_reason",
                            default=(
                                f"用户此前已拒绝对本资源（{resource_path}）的访问，"
                                "本次调用被直接拦截。"
                            ),
                            resource_path=resource_path,
                        ),
                        policy=None,
                        resource_path=resource_path,
                        action=action,
                    )
                    break

                # 值守模式（thread_id 以 duty_ 前缀）同样走 HITL：授权请求推送到
                # 操作台，由运营人员远程批准/拒绝（默认 REJECTED，不会永久挂起）。
                # 资金/敏感操作在值守下必须由人工确认，直接拒绝会静默放弃操作。
                policy = AuthorizationPolicy(
                    resource_type="file",
                    action=action,
                    patterns=[resource_path],
                    requires_approval=True,
                    risk_level="high",
                    description=i18n.get(
                        "engine.authorization.outside_workspace_description",
                        resource_path=resource_path,
                    ),
                )
                if not pending_paths:
                    decision = AuthorizationDecision(
                        approved=False,
                        requires_hitl=True,
                        reason=i18n.get(
                            "engine.authorization.outside_workspace_reason",
                            resource_path=resource_path,
                        ),
                        policy=policy,
                        resource_path=resource_path,
                        action=action,
                    )
                pending_paths.append((resource_path, action))

            if pending_paths and decision.requires_hitl:
                # 单一事实源：all_paths 含全部越界路径（含首路径），
                # resolve 批准/拒绝只认这一份列表。
                extra_paths = list(pending_paths)

    if decision.approved and not decision.requires_hitl:
        return HookResult(success=True)

    # EXECUTION_MODE=docker：所有 HITL 授权决策自动批准（沙箱隔离兜底）。
    # 覆盖工作区外路径与 project.json 策略两路；元数据硬拦截（上方早退）不受影响。
    # 判定单一出处：hitl_enabled()（hitl/core.py），避免与 _is_docker_mode 双答案漂移。
    if decision.requires_hitl and decision.action == "read":
        # HookContext 未透传 dispatch 的 source，从 thread 级 EvoContext 取
        # （评审 run 的工具执行与 hook 同协程，contextvars 可见）
        from app.core.context.manager import ContextManager

        _ctx_obj = ContextManager.current()
        src = getattr(getattr(_ctx_obj, "metadata", None), "source", None)
        if src == "task_review":
            logger.info(
                "[AuthorizationGate] task-review run: read-only exemption %s %s",
                decision.action,
                decision.resource_path or "",
            )
            return HookResult(success=True)

    if decision.requires_hitl and not hitl_enabled():
        logger.info(
            "[AuthorizationGate] docker mode: auto-approving %s %s (sandbox isolation)",
            decision.action,
            decision.resource_path or "",
        )
        return HookResult(success=True)

    if decision.requires_hitl and decision.policy is not None:
        # 旧图架构的 pending_approvals 记账已删：现行精简版 AgentState 无该字段
        # （曾致 AttributeError 被 hook 系统吞掉 → HITL 静默失效、工具照常执行）。
        # HumanRequest 由 request_authorization 落库，resume 从 DB 恢复，无需 state 记账。
        # 重执行的跨进程认领：同一 tool_call 在窗口内已被批准（finalize 双轨
        # COMPLETED+APPROVED）→ 直接放行本次重执行，不重复发起审批。
        # （grant_mode=once / grant 落盘失败时 grant 表不命中，此查询兜底防死循环。）
        try:
            if context.tool_use_id and await HITLOrchestrator.was_call_recently_approved(
                context.thread_id, context.tool_use_id
            ):
                logger.info(
                    "[AuthorizationGate] re-execution of approved call %s allowed (recent approval)",
                    context.tool_use_id,
                )
                return HookResult(success=True)
        except Exception:
            logger.exception(
                "[AuthorizationGate] recent-approval lookup failed (thread=%s, call=%s)",
                context.thread_id,
                context.tool_use_id,
            )

        tool_args = {}
        if context.tool_input is not None:
            tool_args = context.tool_input.args or {}
            inp = context.tool_input
            if inp.command is not None:
                tool_args["command"] = inp.command
            if inp.path is not None:
                tool_args["path"] = inp.path
            if inp.content is not None:
                tool_args["content"] = inp.content
            if inp.query is not None:
                tool_args["query"] = inp.query

        await auth_service.request_authorization(
            thread_id=context.thread_id,
            tool_name=context.tool_name or "",
            tool_call_id=context.tool_use_id or "",
            decision=decision,
            project_id=context.project_id,
            run_id=context.run_id,
            original_tool_name=context.tool_name or "",
            original_tool_args=tool_args,
            extra_paths=extra_paths if decision.requires_hitl else None,
        )
        # request_authorization raises AgentHumanInterruptException; the blocked tool
        # itself is never executed. On approval the resume handler re-invokes the tool.
        return HookResult(success=True)

    # Block without HITL (policy match but approval not available / error path)
    # DeniedError 语义（对齐 OpenCode）：告诉模型被哪条规则拒绝、不要重试。
    return HookResult(
        block=True,
        message=i18n.get(
            "engine.authorization.denied_message",
            default=(
                f"[AUTHORIZATION DENIED] 工具 {context.tool_name or ''} 被权限规则拒绝："
                f"{decision.reason}。请勿重试该调用；如确需使用请联系管理员调整权限。"
            ),
            reason=decision.reason,
        ),
    )
