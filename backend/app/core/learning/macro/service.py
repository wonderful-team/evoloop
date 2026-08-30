import logging
from typing import Any

from app.core.learning.constants import RUN_RESULT_FALLBACK_REQUIRED
from app.core.learning.macro.engine import MacroEngine
from app.core.learning.macro.event.publishers import publish_macro_execution_failed
from app.core.learning.macro.healing_policy import SelfHealingPolicy
from app.core.learning.macro.schemas import MacroRunResult, MacroScript
from app.core.monitoring.activity import activity_monitor
from app.core.monitoring.constants import ActivityStatus
from app.models.macro import Macro

logger = logging.getLogger(__name__)


def _skill_parameters(skill) -> list[dict]:
    """Normalize a skill's parameter declarations for the paired macro."""
    from app.utils.parameters import normalize_parameters

    return normalize_parameters(getattr(skill, "parameters", None))


class MacroService:
    """
    The unified Orchestrator for Macro Logic.
    Provides a clean API for SkillSynthesizer, Agents, and Workflows.
    """

    @classmethod
    async def list_routable_macros(
        cls,
        project_id: int | None = None,
        namespace: str | None = None,
    ) -> list[Macro]:
        """Return verified+active macros in routing order.

        Several routing consumers (init_spec, macro_resolver, macro_device_map,
        navigation_macro_cache) duplicated "list verified+active then sort
        preset-first / newest-first". This is the single home for that.
        """
        from app.core.learning.macro.lifecycle import list_macros

        macros = await list_macros(
            status="verified", is_active=True, namespace=namespace
        )
        macros.sort(
            key=lambda m: (
                m.project_id != project_id if project_id else False,
                m.namespace != "preset",
                -(m.created_at.timestamp() if m.created_at else 0),
            )
        )
        return macros

    @classmethod
    async def resolve_navigation_macro(
        cls,
        text: str,
    ) -> tuple[int, str, str] | None:
        """Resolve ``text`` against preset navigation macros by exact phrase.

        Returns ``(macro_id, route, feedback)`` when ``text`` matches a
        verified+active preset navigation macro's trigger phrase, else None.

        The navigation-macro fast path used to live in routing's
        ``NavigationMacroCache`` (30s TTL). For this local, single-user
        system the DB read is cheap enough that the macro module serves it
        directly — the routing layer no longer needs its own cache or its own
        phrase-matching logic.
        """
        from app.core.learning.macro.runner import is_navigation_macro

        macros = await cls.list_routable_macros(namespace="preset")
        for macro in macros:
            route = is_navigation_macro(macro)
            if route is None:
                continue
            for pattern in macro.trigger_patterns or []:
                if isinstance(pattern, str) and pattern and pattern == text:
                    return macro.id, route, (macro.feedback or "")
        return None

    @classmethod
    async def create_for_skill(
        cls,
        db,
        skill,
        macro_script: str,
        project_id: int | None = None,
        member_id: int = 0,
        source_thread_id: str | None = None,
    ) -> Macro:
        """Create a macro paired with a learned skill and link it back.

        Several skill-synthesis flows (skills.py, synthesis.py, tasks.py)
        duplicated the same "build macro with fallback_skill_id → set
        skill.macro_id" dance. This is the single home for it.

        The caller must publish skill/macro mutation events after the
        surrounding transaction commits.
        """
        from app.core.learning.macro.lifecycle import create_macro_from_synthesis

        macro = await create_macro_from_synthesis(
            db,
            name=skill.name,
            description=getattr(skill, "description", "") or "",
            trigger_patterns=getattr(skill, "trigger_patterns", None) or [],
            parameters=_skill_parameters(skill),
            macro_script=macro_script,
            fallback_skill_id=skill.id,
            source_thread_id=source_thread_id,
            project_id=project_id,
            member_id=member_id,
        )
        skill.macro_id = macro.id
        return macro

    @classmethod
    async def reconcile_for_skill(
        cls,
        db,
        skill,
        macro_script: str,
        source_thread_id: str | None = None,
    ) -> int:
        """Update-or-create the paired macro for a skill, linking it back.

        Chain-heals a skill's flywheel macro: reuse an existing paired macro
        (by skill.macro_id, or by fallback_skill_id) when present, otherwise
        create one. Returns the macro id and sets ``skill.macro_id``.
        """
        from app.core.learning.macro.lifecycle import (
            create_macro_from_synthesis,
            list_macros,
            update_macro,
        )

        if getattr(skill, "macro_id", None):
            if await update_macro(
                skill.macro_id, {"macro_script": macro_script}, db=db
            ):
                return skill.macro_id

        existing_rows = await list_macros(fallback_skill_id=skill.id, db=db)
        existing = existing_rows[0] if existing_rows else None
        if existing is not None:
            await update_macro(existing.id, {"macro_script": macro_script}, db=db)
            skill.macro_id = existing.id
            return existing.id

        macro = await create_macro_from_synthesis(
            db,
            name=skill.name,
            description=getattr(skill, "description", "") or "",
            trigger_patterns=getattr(skill, "trigger_patterns", None) or [],
            parameters=_skill_parameters(skill),
            macro_script=macro_script,
            fallback_skill_id=skill.id,
            source_thread_id=source_thread_id,
            project_id=getattr(skill, "project_id", None),
            member_id=getattr(skill, "member_id", 0),
        )
        skill.macro_id = macro.id
        return macro.id

    @classmethod
    async def run(
        cls,
        thread_id: str,
        script_input: MacroScript | list[dict],
        params: dict[str, Any] | None = None,
        macro: Macro | None = None,  # Macro, optional for policy check
    ) -> MacroRunResult:
        """
        High-level entry point to execute a macro.
        Handles: Validation, Activity Monitoring, Parameters, and Engine Dispatch.

        Args:
            thread_id: The conversation thread ID
            script_input: Macro script (MacroScript object or list of step dicts)
            params: Execution parameters (optional)
            macro: The Macro being executed (optional, for self-healing policy)
        """
        # 1. Validation / Hydration
        try:
            if isinstance(script_input, list):
                script = MacroScript(steps=script_input)
            else:
                script = script_input
        except Exception:
            logger.exception("[%s] Macro validation failed", thread_id)
            return MacroRunResult(success=False, message="Invalid macro format")

        if not script.steps:
            logger.warning(f"[{thread_id}] Macro execution skipped: script is empty.")
            return MacroRunResult(success=False, message="Macro script is empty")

        logger.info(
            f"[{thread_id}] Starting Standardized Macro Execution ({len(script.steps)} steps)"
        )
        if params is None:
            params = {}

        # 集中解析 {{base_url}}（MacroService 直连路径：自愈重试/工具调用）。
        # MacroEngine.run 已做同样注入，但自愈重试（runner._run_with_self_heal）
        # 与直接调用方绕过 run()，直接进 execute_steps，故此处必须兜底。
        # 仅在成功解析时注入；macro 为 None（如纯脚本验证）时无法定位项目，跳过。
        if macro is not None and "base_url" not in params:
            from app.core.learning.macro.runner import resolve_project_base_url

            base_url = await resolve_project_base_url(macro.project_id)
            if base_url:
                params["base_url"] = base_url

        # 2. Activity Monitoring
        await activity_monitor.start_run(thread_id)

        extracted_data = {}
        try:
            # 3. Engine Dispatch
            success, msg, fallback_ctx = await MacroEngine.execute_steps(
                thread_id, script.steps, params, extracted_data
            )

            if not success:
                logger.error("[%s] Macro execution failed: %s", thread_id, msg)
                await activity_monitor.end_run(thread_id, ActivityStatus.FAILED)

                # --- Unified Self-Healing Decision ---
                decision = SelfHealingPolicy.check(macro=macro, execution_params=params)

                if not decision.allowed:
                    logger.warning(
                        "[%s] Self-healing disabled: %s", thread_id, decision.reason
                    )
                    return MacroRunResult(
                        success=False,
                        message=msg,
                        allow_self_healing=False,
                        healing_disabled_reason=decision.reason,
                        healing_disabled_source=decision.source,
                        step_log=(fallback_ctx or {}).get("step_log"),
                        execution_warnings=(fallback_ctx or {}).get("execution_warnings"),
                    )

                # Self-healing is allowed - trigger fallback via event system
                macro_name = (
                    macro.name if macro is not None else params.get("_macro_name")
                )
                event = await publish_macro_execution_failed(
                    macro_name=macro_name or "manual_macro",
                    error_message=msg,
                    fallback_context=fallback_ctx,
                    thread_id=thread_id,
                )

                return MacroRunResult(
                    success=False,
                    message=msg,
                    allow_self_healing=True,
                    suggestions=event.suggestions,
                    status=RUN_RESULT_FALLBACK_REQUIRED,
                    fallback_context=fallback_ctx,
                    step_log=(fallback_ctx or {}).get("step_log"),
                    execution_warnings=(fallback_ctx or {}).get("execution_warnings"),
                )

            # 4. Success Reporting
            await activity_monitor.log_event(
                "macro_thought",
                {"text": "Macro execution completed successfully."},
                thread_id,
            )
            await activity_monitor.end_run(thread_id, ActivityStatus.DONE)
            return MacroRunResult(
                success=True,
                message="Deterministic Macro Execution Complete.",
                extracted_data=extracted_data,
                step_log=(fallback_ctx or {}).get("step_log"),
                execution_warnings=(fallback_ctx or {}).get("execution_warnings"),
            )

        except Exception as e:
            logger.error(f"[{thread_id}] Macro service crash: {e}", exc_info=True)
            await activity_monitor.end_run(thread_id, ActivityStatus.FAILED)
            return MacroRunResult(
                success=False, message=f"System error during macro execution: {str(e)}"
            )
