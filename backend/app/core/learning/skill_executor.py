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
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.engine import AgentEngine
from app.core.llm.factory import LLMFactory
from app.core.monitoring.activity import activity_monitor
from app.core.tools.executor import ToolExecutor
from app.core.tools.registry_utils import get_node_tools
from app.i18n.service import i18n
from app.core.context.manager import ContextManager
from app.infrastructure.database.sql.database import session_scope
from app.models import LearnedSkill as LearnedSkillModel
from app.domain.environment import get_awakened_state
from app.domain.environment.prompt import AppEnvironmentPrompt

logger = logging.getLogger(__name__)


@dataclass
class SkillStepResult:
    """
    Structured result from a Skill step execution.
    
    Implements dict-like access so that it is compatible with 
    _substitute_params template resolution (e.g. {{result.text}}, {{result.files_modified}}).
    """
    text: str
    tool_calls_made: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    structured_data: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.text

    def __contains__(self, item: str) -> bool:
        """Support 'in' checks for backward compatibility (e.g. 'error' in result)."""
        return item in self.text.lower()

    # Dict-like access for _substitute_params {{result.field}} resolution
    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        if key in self.structured_data:
            return self.structured_data[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    @staticmethod
    def _extract_modified_files(messages: list) -> list[str]:
        """Extract file paths from tool messages that indicate file modifications."""
        modified = []
        write_tools = {"write_file", "edit_file", "file_system", "manage_file"}
        for msg in messages:
            if isinstance(msg, ToolMessage) and msg.name in write_tools:
                # Try to extract 'path' from the tool call args
                # The name of modified file is often in the previous AIMessage's tool_call args
                pass  # Files are tracked from AIMessage tool_calls below
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get("name") in write_tools:
                        path = tc.get("args", {}).get("path") or tc.get("args", {}).get("file_path")
                        if path and path not in modified:
                            modified.append(path)
        return modified


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
        """
        # Load skill from DB
        async with session_scope() as db:
            skill = await db.get(LearnedSkillModel, skill_id)
            if not skill:
                return False, i18n.get("prompts.skill_executor.skill_not_found", id=skill_id)

        try:
            steps = json.loads(skill.steps) if skill.steps else []
            logger.info(f"Executing skill '{skill.name}' with {len(steps)} root steps")

            # Notify Activity Monitor
            thread_id = self.config.get("configurable", {}).get("thread_id")
            skill_step_id = None
            if thread_id:
                skill_step_id = await activity_monitor.add_step(
                    thread_id,
                    i18n.get("prompts.skill_executor.task_executing", name=skill.name),
                    "skill",
                )

            # --- Context Middleware: Inject Environment Awareness ---
            try:
                state = get_awakened_state()
                if state:
                    ctx = ContextManager.current()
                    # Inject into standardized metadata
                    ctx.metadata["_env"] = {
                        "os": state.platform,
                        "devices": [d.id for d in state.android_devices],
                        "cwd": __import__("os").getcwd()
                    }
            except Exception as e:
                logger.warning(f"Failed to inject environment context: {e}")

            # Initial context (global params)
            context = {**params}
            results = []

            # Execute root steps recursively
            success, root_results = await self._execute_steps(
                steps, context, tool_registry, depth=0, base_path=[], skill_instructions=skill.instructions
            )
            results.extend(root_results)

            # Update usage stats and confidence score
            async with session_scope() as db:
                skill_record = await db.get(LearnedSkillModel, skill_id)
                if skill_record:
                    from datetime import datetime
                    import json as json_lib
                    
                    old_status = skill_record.status
                    
                    if not success:
                        skill_record.failure_count += 1
                        skill_record.last_failure_at = datetime.now()
                        skill_record.confidence_score = max(-3.0, skill_record.confidence_score - 0.5)
                        if skill_record.confidence_score <= -2:
                            skill_record.status = "deprecated"
                            skill_record.is_active = False
                    else:
                        skill_record.success_count += 1
                        skill_record.last_success_at = datetime.now()
                        skill_record.confidence_score += 1.0
                        if skill_record.confidence_score >= 3 and skill_record.status == "draft":
                            skill_record.status = "candidate"
                        elif skill_record.confidence_score >= 5 and skill_record.status == "candidate":
                            skill_record.status = "verified"
                    
                    if skill_record.status != old_status:
                        history = []
                        if skill_record.promotion_history:
                            try:
                                history = json_lib.loads(skill_record.promotion_history)
                            except Exception:
                                pass
                        history.append({
                            "from": old_status,
                            "to": skill_record.status,
                            "at": datetime.now().isoformat(),
                            "confidence": skill_record.confidence_score
                        })
                        skill_record.promotion_history = json_lib.dumps(history)
                    
                    await db.commit()
                
                    # Publish events
                    from app.domain.environment.events import event_bus, SkillExecutedEvent
                    await event_bus.publish(SkillExecutedEvent(
                        skill_id=skill_id,
                        skill_name=skill_record.name,
                        success=success,
                        confidence_delta=1.0 if success else -0.5
                    ))

            summary = "\n".join(results)
            if thread_id and skill_step_id:
                status = "done" if success else "failed"
                await activity_monitor.update_step(thread_id, skill_step_id, status, details=summary)

            return success, summary

        except Exception as e:
            logger.exception(f"Skill execution failed with fatal error: {e}")
            # Final attempt to update stats on failure
            async with session_scope() as db:
                skill_record = await db.get(LearnedSkillModel, skill_id)
                if skill_record:
                    skill_record.failure_count += 1
                    skill_record.confidence_score = max(-3.0, skill_record.confidence_score - 1.0)
                    await db.commit()
            return False, f"System Error: {str(e)}"

    async def _execute_steps(
        self, steps: list[dict], context: dict[str, Any], tool_registry: dict[str, Any], 
        depth: int = 0, base_path: list[int] = None, skill_instructions: str = None
    ) -> tuple[bool, list[str]]:
        """
        Recursive helper to execute a list of steps.
        """
        results = []
        previous_result = None
        thread_id = self.config.get("configurable", {}).get("thread_id")
        
        for i, step in enumerate(steps):
            current_path = (base_path or []) + [i]
            action = step.get("action", "")
            args = step.get("args", {})
            condition = step.get("condition")
            children = step.get("children", [])

            # Phase 3: Emit Debug Event
            if thread_id:
                try:
                    await activity_monitor.update_agent_state(
                        thread_id=thread_id,
                        mode="SKILL",
                        task_name=i18n.get("prompts.skill_executor.task_executing", name=action),
                        task_status=f"Executing step {'.'.join(map(str, current_path))}",
                        details={
                            "type": "debug",
                            "step_path": current_path,
                            "variables": context,
                            "previous_result": previous_result
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to emit debug event: {e}")

            # Check skip condition (Simple string-based check)
            if condition and previous_result is not None:
                if "previous step succeeded" in condition.lower() and "error" in str(previous_result).lower():
                    results.append(f"{'  ' * depth}Skipped: {action} (Condition failed)")
                    continue

            # Resolve arguments with current context
            resolved_args = self._substitute_params(args, context, previous_result)

            # --- Logic Actions ---
            
            # 1. Loop
            if action == "loop":
                count = int(resolved_args.get("count", 1))
                items = resolved_args.get("items")
                
                loop_success = True
                if items and isinstance(items, list):
                    for idx, item in enumerate(items):
                        loop_context = {**context, "item": item, "loop_index": idx}
                        batch_success, batch_results = await self._execute_steps(
                            children, loop_context, tool_registry, depth + 1, base_path=current_path, skill_instructions=skill_instructions
                        )
                        results.extend(batch_results)
                        if not batch_success:
                            loop_success = False; break
                else:
                    for idx in range(count):
                        loop_context = {**context, "loop_index": idx}
                        batch_success, batch_results = await self._execute_steps(
                            children, loop_context, tool_registry, depth + 1, base_path=current_path, skill_instructions=skill_instructions
                        )
                        results.extend(batch_results)
                        if not batch_success:
                            loop_success = False; break
                
                previous_result = "Loop Finished" if loop_success else "Loop Failed"
                if not loop_success: return False, results

            # 2. Condition (If/Else)
            elif action == "condition":
                condition_expr = resolved_args.get("if", "True")
                then_steps = resolved_args.get("then", children) # Fallback to children for then_steps
                else_steps = resolved_args.get("else", [])
                
                # Simple eval-style check (SAFE: only checking boolean logic or existence)
                is_true = False
                try:
                    # Very basic truthy check
                    is_true = bool(eval(str(condition_expr), {"__builtins__": {}}, context))
                except:
                    is_true = bool(condition_expr)
                
                target_steps = then_steps if is_true else else_steps
                cond_success, cond_results = await self._execute_steps(
                    target_steps, context, tool_registry, depth + 1, base_path=current_path, skill_instructions=skill_instructions
                )
                results.extend(cond_results)
                if not cond_success: return False, results
                previous_result = f"Condition {'True' if is_true else 'False'}"

            # 3. Group
            elif action == "group":
                grp_success, grp_results = await self._execute_steps(
                    children, context, tool_registry, depth + 1, base_path=current_path, skill_instructions=skill_instructions
                )
                results.extend(grp_results)
                if not grp_success: return False, results
                previous_result = "Group Finished"

            # 4. Natural Language Instruction (Standard Skill Support)
            elif action == "natural_language_instruction":
                logger.info(f"Executing instructional step: {resolved_args.get('instruction')}")
                instruction_batch = resolved_args.get("instruction", "Follow skill instructions")
                
                # Use AgentEngine to fulfill the instruction
                # This ensures consistent logging, error handling, and context management
                
                # Build context for LLM
                env_prompt = AppEnvironmentPrompt.build()
                system_prompt = f"{env_prompt}\nYou are executing an AI Skill step. Use the following Skill Instructions as your logic guide:\n\n{skill_instructions or 'No specific instructions provided.'}\n\nIMPORTANT: Prioritize UI interactions (click, type, find_element) to achieve the goal. Avoid excessive memory searches unless explicitly needed for variable retrieval."
                
                # Prepare initial messages
                initial_messages = [
                    HumanMessage(content=f"Current Objective: {instruction_batch}\nCurrent Context: {context}\nPrevious result: {previous_result}\n\nExecute the necessary tool calls.")
                ]
                
                try:
                    # Bind tools from registry
                    available_tools = list(tool_registry.values())
                    
                    # Construct valid AgentState
                    agent_state = {
                        "messages": initial_messages,
                        "param_schema": {}, # Optional
                        "execution_ticket": {} # Optional
                    }
                    
                    # Run using standard AgentEngine
                    # We use a distinct name 'Skill-Worker' to differentiate in logs
                    engine_result = await AgentEngine.run_node(
                        state=agent_state,
                        config=self.config,
                        system_prompt=system_prompt,
                        tools=available_tools,
                        max_steps=50, # Same as previous max_turns
                        name="Skill-Worker"
                    )
                    
                    # Process result — extract structured information
                    final_messages = engine_result.get("messages", [])
                    if final_messages:
                        last_msg = final_messages[-1]
                        if isinstance(last_msg, AIMessage):
                            content_str = last_msg.content
                        else:
                            content_str = str(last_msg.content) if last_msg.content else "Skill Worker Finished"
                        
                        # Build structured result
                        tool_names_used = [
                            msg.name for msg in final_messages 
                            if isinstance(msg, ToolMessage) and msg.name
                        ]
                        files_modified = SkillStepResult._extract_modified_files(final_messages)
                        
                        step_result = SkillStepResult(
                            text=content_str,
                            tool_calls_made=tool_names_used,
                            files_modified=files_modified,
                        )
                        
                        results.append(
                            f"{'  ' * depth}Skill Worker Finished: {content_str[:100]}... "
                            f"(tools: {len(tool_names_used)}, files: {len(files_modified)})"
                        )
                        previous_result = step_result
                    else:
                        results.append(f"{'  ' * depth}Skill Worker Finished (no messages returned)")
                    
                    # Verify success
                    # If the engine finished without error, we consider it a success unless specific failure criteria met
                    # The AgentEngine handles retries and tool errors internally
                    
                except Exception as e:
                    logger.error(f"Instructional step failed via AgentEngine: {e}")
                    results.append(f"{'  ' * depth}Instructional Error: {str(e)}")
                    return False, results

            # 5. Standard Tools
            elif action in tool_registry:
                tool = tool_registry[action]
                try:
                    result = await self.tool_executor.execute(tool, resolved_args, self.config)
                    previous_result = result
                    
                    # Store result in context for future steps if it has a name
                    if "result_var" in step:
                        context[step["result_var"]] = result
                    results.append(f"{'  ' * depth}Executed: {action} (Result: {str(result)[:50]}...)")
                    
                    # Trigger recovery if output looks like an error
                    if isinstance(result, str) and "Error executing" in result:
                        raise Exception(result)
                except Exception as e:
                    # Phase 4: Self-Correction Logic
                    on_error = step.get("on_error", "retry" if action in ["mobile_control", "desktop_control"] else "fail")
                    
                    if on_error == "retry":
                        logger.info(f"Step {action} failed, attempting recovery: {e}")
                        recovery_success = await self._handle_step_failure(action, resolved_args, str(e), tool_registry)
                        if recovery_success:
                            # Retry once
                            try:
                                result = await self.tool_executor.execute(tool, resolved_args, self.config)
                                previous_result = result
                                results.append(f"{'  ' * depth}Recovered: {action}")
                                continue 
                            except Exception as e2:
                                logger.error(f"Retry failed after recovery: {e2}")
                                results.append(f"{'  ' * depth}Failed after retry: {action} ({e2})")
                                return False, results
                        else:
                            results.append(f"{'  ' * depth}Recovery failed: {action} ({e})")
                            return False, results
                    elif on_error == "ignore":
                        logger.warning(f"Step {action} failed, ignoring: {e}")
                        results.append(f"{'  ' * depth}Ignored error: {action}")
                        previous_result = f"Error ignored: {e}"
                        continue
                    else:
                        logger.error(f"Step {action} failed: {e}")
                        results.append(f"{'  ' * depth}Error: {action} ({e})")
                        return False, results
            else:
                results.append(f"{'  ' * depth}Step {i+1} ({action}) - Skipped (Tool not found)")

        return True, results

    def _substitute_params(
        self, args: dict[str, Any], context: dict[str, Any], previous_result: Any = None
    ) -> dict[str, Any]:
        """
        Substitute {{param}} placeholders in args using context.
        Supports {{result.field}} and {{variable.field}}.
        """
        import re

        def _resolve_val(v):
            if isinstance(v, str):
                # 1. Handle {{variable.field}} and {{variable}}
                matches = re.findall(r"\{\{([^}]+)\}\}", v)
                for match in matches:
                    placeholder = f"{{{{{match}}}}}"
                    
                    # Special case: result
                    if match == "result":
                        v = v.replace(placeholder, str(previous_result))
                        continue
                    if match.startswith("result.") and previous_result is not None:
                        # Supports both dict and SkillStepResult (dict-like via __getitem__)
                        parts = match.split(".")
                        val = previous_result
                        for p in parts[1:]:
                            if isinstance(val, dict) and p in val:
                                val = val[p]
                            elif hasattr(val, "get"):
                                val = val.get(p, f"UNDEFINED({p})")
                            else:
                                val = f"UNDEFINED({p})"
                                break
                        v = v.replace(placeholder, str(val))
                        continue

                    # General case: context variables
                    if "." in match:
                        parts = match.split(".")
                        root = parts[0]
                        if root in context:
                            val = context[root]
                            for p in parts[1:]:
                                if isinstance(val, dict) and p in val:
                                    val = val[p]
                                else:
                                    val = f"UNDEFINED({p})"
                                    break
                            v = v.replace(placeholder, str(val))
                    elif match in context:
                        v = v.replace(placeholder, str(context[match]))
                
                return v
            elif isinstance(v, dict):
                return {k: _resolve_val(val) for k, val in v.items()}
            elif isinstance(v, list):
                return [_resolve_val(i) for i in v]
            return v

        resolved = {}
        for key, value in args.items():
            resolved[key] = _resolve_val(value)

        return resolved

    async def _handle_step_failure(self, action: str, args: dict, error: str, tool_registry: dict) -> bool:
        """
        Use LLM + Screenshot to attempt a recovery action.
        Returns True if a recovery action was successfully executed.
        """
        try:
            # 1. Capture current screenshot (if possible)
            screenshot_b64 = None
            if "mobile_control" in tool_registry:
                res = await self.tool_executor.execute(tool_registry["mobile_control"], {"action": "screenshot"}, self.config)
                if isinstance(res, dict) and "screenshot_b64" in res:
                    screenshot_b64 = res["screenshot_b64"]
            
            # 2. Consult LLM for recovery
            from app.core.llm.factory import LLMFactory
            from langchain_core.messages import HumanMessage, SystemMessage
            
            llm = LLMFactory.create_llm()
            
            prompt = i18n.get("prompts.skill_executor.recovery_system_prompt")
            # If i18n fails, use fallback
            if not prompt or "{action}" not in prompt:
                prompt = """You are the "Recovery Specialist". A skill step failed. Suggest ONE tool call to fix the state.
Return exactly: TOOL: tool_name(arg1=val, ...) or UNRECOVERABLE.
FAILED: {action} ({error}) with args {args}"""

            formatted_prompt = prompt.format(action=action, args=args, error=error)
            
            content = [
                {"type": "text", "text": formatted_prompt}
            ]
            
            if screenshot_b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
                })
            
            messages = [
                SystemMessage(content="You are a recovery agent assisting a skill executor."),
                HumanMessage(content=content)
            ]
            
            response = await llm.ainvoke(messages)
            suggestion = response.content.strip()
            
            if "UNRECOVERABLE" in suggestion:
                return False
            
            if "TOOL:" in suggestion:
                # Simple parsing: TOOL: name(args)
                try:
                    tool_call_str = suggestion.split("TOOL:")[1].strip()
                    tool_name = tool_call_str.split("(")[0].strip()
                    import ast
                    args_str = tool_call_str[tool_call_str.find("(")+1 : tool_call_str.rfind(")")]
                    # Very basic arg parsing, for real use we'd want something more robust
                    # For now just handle simple k=v or empty
                    if not args_str:
                        rec_args = {}
                    else:
                        # Convert k=v, k2=v2 to valid dict if possible
                        # This is a bit fragile, but better than nothing
                        rec_args = {}
                        for pair in args_str.split(","):
                            if "=" in pair:
                                k, v = pair.split("=", 1)
                                try:
                                    rec_args[k.strip()] = ast.literal_eval(v.strip())
                                except:
                                    rec_args[k.strip()] = v.strip().strip("'").strip('"')
                    
                    if tool_name in tool_registry:
                        logger.info(f"Executing recovery action: {tool_name}({rec_args})")
                        await self.tool_executor.execute(tool_registry[tool_name], rec_args, self.config)
                        return True
                except Exception as ex:
                    logger.error(f"Failed to parse recovery tool: {ex}")
            
            return False
        except Exception as e:
            logger.error(f"Recovery agent failed: {e}")
            return False


# Singleton matcher for efficiency
skill_matcher = SkillMatcher()
