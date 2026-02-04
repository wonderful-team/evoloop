"""
SkillExecutor - Phase 3/4 of Imitation Learning

Executes learned skills by:
1. Matching user input against skill trigger patterns
2. Extracting parameters from input
3. Executing skill steps sequentially using ToolExecutor
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.llm.factory import LLMFactory
from app.core.monitoring.activity import activity_monitor
from app.core.tools.executor import ToolExecutor
from app.core.tools.registry_utils import get_node_tools
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models import LearnedSkill as LearnedSkillModel

logger = logging.getLogger("evoloop.learning.executor")


def build_skill_tool_registry() -> dict[str, Any]:
    """
    Build a tool registry for SkillExecutor from the Developer's tool set.
    This ensures learned skills can access platform control tools like mobile_control.
    """
    registry = {}
    for tool in get_node_tools("developer"):
        registry[tool.name] = tool
    return registry


@dataclass
class SkillMatch:
    """Result of skill matching."""

    skill_id: int
    skill_name: str
    confidence: float  # 0-1
    extracted_params: dict[str, Any]


class SkillMatcher:
    """
    Matches user input against learned skill trigger patterns.
    Uses both regex pattern matching and LLM-based semantic matching.
    """

    def __init__(self):
        self._skills_cache: list[LearnedSkillModel] | None = None
        self._cache_expiry = 0

    async def _load_skills(self) -> list[LearnedSkillModel]:
        """Load active skills from database."""
        import time

        current = time.time()

        # Cache for 60 seconds
        if self._skills_cache and current < self._cache_expiry:
            return self._skills_cache

        async with session_scope() as db:
            stmt = select(LearnedSkillModel).where(LearnedSkillModel.is_active)
            result = await db.execute(stmt)
            self._skills_cache = list(result.scalars().all())
            self._cache_expiry = current + 60

        return self._skills_cache

    def _pattern_to_regex(self, pattern: str) -> str:
        """
        Convert trigger pattern to regex.
        {param} -> named capture group
        """
        # Escape regex special chars except for our {param} placeholders
        escaped = re.escape(pattern)
        # Convert \{param\} back to (?P<param>.+?)
        regex = re.sub(r"\\{(\w+)\\}", r"(?P<\1>.+?)", escaped)
        return f"^{regex}$"

    async def match(self, user_input: str, threshold: float = 0.5, thread_id: str = None) -> SkillMatch | None:
        """
        Find best matching skill for user input.

        Returns SkillMatch if confidence >= threshold, else None.
        """
        skills = await self._load_skills()

        if not skills:
            return None

        best_match: SkillMatch | None = None
        best_confidence = 0.0

        for skill in skills:
            try:
                patterns = json.loads(skill.trigger_patterns) if skill.trigger_patterns else []
            except Exception:
                patterns = []

            for pattern in patterns:
                # Try regex matching
                regex = self._pattern_to_regex(pattern)
                match = re.match(regex, user_input, re.IGNORECASE)

                if match:
                    params = match.groupdict()
                    # Exact match = high confidence
                    confidence = 0.95

                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = SkillMatch(
                            skill_id=skill.id,
                            skill_name=skill.name,
                            confidence=confidence,
                            extracted_params=params,
                        )

        # If no regex match, try semantic matching with LLM
        if not best_match or best_confidence < threshold:
            semantic_match = await self._semantic_match(user_input, skills, thread_id=thread_id)
            if semantic_match and semantic_match.confidence > best_confidence:
                best_match = semantic_match

        if best_match and best_match.confidence >= threshold:
            return best_match

        return None

    async def _semantic_match(
        self, user_input: str, skills: list[LearnedSkillModel], thread_id: str = None
    ) -> SkillMatch | None:
        """
        Use LLM to semantically match user input to skills.
        """
        if not skills:
            return None

        # Build skill list for prompt
        skill_list = []
        for skill in skills:
            skill_list.append(f"- ID: {skill.id}, Name: {skill.name}, Desc: {skill.description}")

        prompt = f"""Given the user's request, determine if it matches any learned skill.

User Request: "{user_input}"

Available Skills:
{chr(10).join(skill_list)}

If a skill matches, output JSON:
{{"skill_id": <id>, "skill_name": "<name>", "confidence": <0.0-1.0>, "params": {{}}}}

If no skill matches well (confidence < 0.5), output:
{{"skill_id": null}}

Output ONLY the JSON, no explanation."""

        try:
            llm = LLMFactory.create_llm()
            response = await llm.ainvoke([
                SystemMessage(content="You are a skill matching assistant."),
                HumanMessage(content=prompt)
            ], config={"callbacks": []})  # Disable global callbacks to prevent JSON leakage

            content = response.content.strip()
            if "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                if content.startswith("json"):
                    content = content[4:].strip()

            data = json.loads(content)

            if data.get("skill_id"):
                match = SkillMatch(
                    skill_id=data["skill_id"],
                    skill_name=data.get("skill_name", ""),
                    confidence=data.get("confidence", 0.6),
                    extracted_params=data.get("params", {}),
                )

                # Phase 6: Transparent Thought
                if thread_id:
                    try:
                        await activity_monitor.update_agent_state(
                            thread_id=thread_id,
                            mode="SKILL",
                            task_name=i18n.get("prompts.skill_executor.task_matching"),
                            task_status=i18n.get("prompts.skill_executor.status_identified", name=match.skill_name),
                            details={
                                "type": "thought",
                                "thought_type": "skill_match",
                                "skill_name": match.skill_name,
                                "confidence": match.confidence,
                                "params": match.extracted_params,
                            },
                        )
                    except Exception:
                        pass

                return match
        except Exception as e:
            logger.warning(f"Semantic skill matching failed: {e}")

        return None


class SkillExecutor:
    """
    Executes a learned skill by running its steps.
    """

    def __init__(self, config: RunnableConfig | None = None):
        self.config = config or {}
        self.tool_executor = ToolExecutor()

    async def execute_skill(
        self, skill_id: int, params: dict[str, Any], tool_registry: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Execute a skill by its ID.

        Args:
            skill_id: Database ID of the skill
            params: Parameters extracted from user input
            tool_registry: Dict mapping tool names to tool instances

        Returns:
            (success: bool, result_message: str)
        """
        # Load skill from DB
        async with session_scope() as db:
            skill = await db.get(LearnedSkillModel, skill_id)
            if not skill:
                return False, i18n.get("prompts.skill_executor.skill_not_found", id=skill_id)

        try:
            steps = json.loads(skill.steps) if skill.steps else []
        except Exception:
            return False, i18n.get("prompts.skill_executor.parse_failed")

        logger.info(f"Executing skill '{skill.name}' with {len(steps)} steps")

        # Notify Activity Monitor
        thread_id = self.config.get("configurable", {}).get("thread_id")
        skill_step_id = None
        if thread_id:
            skill_step_id = await activity_monitor.add_step(
                thread_id,
                i18n.get("prompts.skill_executor.task_executing", name=skill.name),
                "skill",
            )

        results = []
        previous_result = None

        for i, step in enumerate(steps):
            action = step.get("action", "")
            args = step.get("args", {})
            condition = step.get("condition")

            # Check condition
            if condition and previous_result is not None:
                # Simple condition evaluation
                if "previous step succeeded" in condition.lower():
                    if "error" in str(previous_result).lower():
                        logger.info(f"Skipping step {i+1} due to condition: {condition}")
                        continue

            # Parameter substitution
            resolved_args = self._substitute_params(args, params, previous_result)

            # Execute step
            if action in tool_registry:
                tool = tool_registry[action]
                try:
                    result = await self.tool_executor.execute(tool, resolved_args, self.config)
                    previous_result = result

                    # Format output, truncating if too long for summary
                    output_str = str(result)
                    if len(output_str) > 2000:
                        output_str = output_str[:2000] + "... (truncated)"

                    results.append(i18n.get(
                        "prompts.skill_executor.step_success",
                        i=i + 1,
                        action=action,
                        output=output_str,
                    ))
                    logger.info(f"Step {i+1} ({action}) completed")
                except Exception as e:
                    previous_result = f"Error: {e}"
                    results.append(i18n.get(
                        "prompts.skill_executor.step_failed",
                        i=i + 1,
                        action=action,
                        error=e,
                    ))
                    logger.error(f"Step {i+1} ({action}) failed: {e}")
            else:
                logger.warning(f"Tool '{action}' not found in registry, skipping")
                results.append(i18n.get("prompts.skill_executor.step_skipped", i=i+1, action=action))

        # Update usage stats
        async with session_scope() as db:
            skill_record = await db.get(LearnedSkillModel, skill_id)
            if skill_record:
                has_errors = any("Failed" in r for r in results)
                if has_errors:
                    skill_record.failure_count += 1
                else:
                    skill_record.success_count += 1
                await db.commit()

        success = not any("Failed" in r for r in results)
        summary = "\n".join(results)

        if thread_id and skill_step_id:
            status = "done" if success else "failed"
            await activity_monitor.update_step(thread_id, skill_step_id, status, details=summary)

        return success, summary

    def _substitute_params(
        self, args: dict[str, Any], params: dict[str, Any], previous_result: Any = None
    ) -> dict[str, Any]:
        """
        Substitute {{param}} placeholders in args.
        """
        resolved = {}

        for key, value in args.items():
            if isinstance(value, str):
                # Replace {{param}} with actual value
                for param_name, param_value in params.items():
                    value = value.replace(f"{{{{{param_name}}}}}", str(param_value))

                # Replace {{result}} with previous result
                if previous_result and "{{result" in value:
                    if isinstance(previous_result, dict):
                        for k, v in previous_result.items():
                            value = value.replace(f"{{{{result.{k}}}}}", str(v))
                    value = value.replace("{{result}}", str(previous_result))

                resolved[key] = value
            else:
                resolved[key] = value

        return resolved


# Singleton matcher for efficiency
skill_matcher = SkillMatcher()
