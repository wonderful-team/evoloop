from __future__ import annotations

import asyncio
import json
from typing import Any

from app.domain.tasks.constants import WAKEUP_RUN_DEADLINE_SECONDS
from app.domain.tasks.events import publish_workflow_event
from app.domain.tasks.service import TaskQueueService
from app.domain.tasks.workflows import WorkflowService
from app.models.project import ProjectTask


class AgentRuntimeError(Exception):
    pass


REQUIRED_OUTPUT_KEYS = ("summary", "data", "risks", "recommendation")


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        str(part.get("text") or "")
        for part in content
        if isinstance(part, dict) and part.get("type") == "text"
    )


def _with_balanced_delimiters(payload: str) -> str:
    stack: list[str] = []
    in_string = False
    escaped = False
    pairs = {"{": "}", "[": "]"}

    for character in payload:
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if character in pairs:
            stack.append(character)
        elif character in pairs.values():
            if not stack:
                return payload
            opening = stack.pop()
            if pairs[opening] != character:
                return payload

    if not stack:
        return payload
    return payload + "".join(pairs[opening] for opening in reversed(stack))


def parse_structured_output(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) > 2:
            stripped = "\n".join(lines[1:-1]).strip()

    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character != "{":
            continue

        for candidate_text in (stripped[index:], _with_balanced_delimiters(stripped[index:])):
            try:
                candidate, _ = decoder.raw_decode(candidate_text)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and all(
                key in candidate for key in REQUIRED_OUTPUT_KEYS
            ):
                return candidate

    raise AgentRuntimeError("Evoloop Agent returned invalid structured output")


def _iter_metadata_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            payload
            for child in value.values()
            for payload in _iter_metadata_strings(child)
        ]
    if isinstance(value, list | tuple):
        return [
            payload
            for child in value
            for payload in _iter_metadata_strings(child)
        ]
    return []


def _parse_output_from_messages(messages: list[Any]) -> dict[str, Any]:
    for message in reversed(messages):
        candidates = [
            _message_text(message),
            str(getattr(message, "thinking", "") or ""),
            *_iter_metadata_strings(getattr(message, "meta_data", None)),
            *_iter_metadata_strings(getattr(message, "tool_calls", None)),
        ]
        for candidate in candidates:
            if not candidate.strip():
                continue
            try:
                return parse_structured_output(candidate)
            except AgentRuntimeError:
                continue
    raise AgentRuntimeError("Evoloop Agent returned invalid structured output")


class EvoloopAgentRuntimeAdapter:
    @staticmethod
    async def run(task: ProjectTask) -> str:
        from app.core.engine.agent import run_agent_background
        from app.core.engine.dispatch import dispatch_agent_run
        from app.core.engine.message.repository import MessageRepository

        task_data = task.task_data or {}
        stage = str(task_data.get("workflow_stage") or "")
        workflow_id = str(task_data.get("workflow_id") or "")
        thread_id = f"agent_{task.project_id}_{task.id}"

        await TaskQueueService.take_task(task.id, thread_id)
        await publish_workflow_event(
            workflow_id,
            event="task_started",
            task_id=task.id,
            stage=stage,
            status="in_progress",
        )
        prompt = await WorkflowService.build_task_prompt(task)
        dispatch_result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=prompt,
            project_id=task.project_id or None,
            member_id=await TaskQueueService.resolve_member_id(task),
            metadata={
                "source": "duty",
                "source_task_id": task.id,
                "task_type": "growth_workflow",
                "workflow_id": workflow_id,
                "workflow_stage": stage,
                "channel_name": str((task.source_ref or {}).get("channel") or ""),
                "goal_prefix": "[Workflow] ",
            },
        )
        if dispatch_result.status.name == "FAILED" or dispatch_result.inputs is None:
            raise AgentRuntimeError(
                dispatch_result.error or "Evoloop Agent dispatch failed"
            )
        await WorkflowService.ensure_task_plan(task, thread_id)

        try:
            await asyncio.wait_for(
                run_agent_background(thread_id, dispatch_result.inputs),
                timeout=WAKEUP_RUN_DEADLINE_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise AgentRuntimeError("Evoloop Agent run timed out") from exc

        messages, _, _ = await MessageRepository(
            thread_id,
            task.project_id,
            member_id=await TaskQueueService.resolve_member_id(task),
        ).get_full_history(limit=50, include_invisible=False)
        final_ai_text = next(
            (
                output
                for message in reversed(messages)
                if getattr(message, "role", "") == "ai"
                and (output := _message_text(message)).strip()
            ),
            "",
        )
        if not final_ai_text:
            raise AgentRuntimeError(
                "Evoloop Agent did not return a final assistant message"
            )

        output = _parse_output_from_messages(messages)
        summary = str(output.get("summary") or final_ai_text[:500])
        await WorkflowService.complete_task(
            task,
            result=summary,
            output=output,
            thread_id=thread_id,
        )
        return summary
