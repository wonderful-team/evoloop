"""
Supervisor Prompt Builder

Constructs the system prompt for the Supervisor ReAct Agent.
Allows for dynamic context injection and potential LLM-specific adaptations.
"""

import json
import logging
import os

from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.system import SystemConfigService

logger = logging.getLogger(__name__)


class SupervisorPromptBuilder:
    def __init__(
        self,
        project_id: int,
        active_plan_context: str,
        iteration_count: int,
        sys_info: str,
        context: dict = None,
    ):
        self.project_id = project_id
        self.active_plan_context = active_plan_context
        self.iteration_count = iteration_count
        self.sys_info = sys_info
        self.context = context or {}

    def build(self, config: RunnableConfig) -> str:
        """Constructs the full system prompt."""
        user_lang = SystemConfigService.get_language_preference()

        # Awakening: Inject environment awareness at the top
        awakening_section = self._build_awakening_section()

        # Solution A: Build Plan Status Section
        plan_status_section = self._build_plan_status_section()

        # Solution C: Build Visited Nodes Warning
        visited_nodes_warning = self._build_visited_nodes_warning()

        # Phase 8: Build Blackboard State Section
        blackboard_section = self._build_blackboard_section()

        # Brain Integration: Episodic Memory
        episodic_memory = self._build_episodic_memory_section()
        
        # Brain Integration: Core Memory (Focus)
        core_memory = self._build_core_memory_section()

        # Phase 11: Dynamic Agent Sandbox Protocol
        dynamic_protocol = """
### DYNAMIC AGENT PROTOCOLS (SANDBOX)
When you use `route_to(target="dynamic_specialist")`, you are creating a temporary agent.
You MUST adhere to the **SANDBOX PROTOCOL**:
1. **Least Privilege**: Only grant tools ESSENTIAL for the task.
   - Default: `["read_file", "list_files", "grep_files"]`
   - SQL: `["sql_query"]`
   - Android/Mobile: `["mobile_control", "analyze_image"]`
   - MacOS/Desktop: `["desktop_control", "analyze_image"]`
2. **Memory Write Ban**: NEVER grant `manage_memory` to dynamic agents unless the role is explicitly "KnowledgeHarvester".
   - Sub-agents are "Stateless". They should not pollute the long-term memory.
3. **No Human Contact**: NEVER grant `request_approval` or `chat`. Sub-agents cannot talk to the user.
"""
        return f"""You are the Supervisor of an elite Universal AI Agent Team.
{awakening_section}
## Your Role
You are a MANAGER. You analyze user requests, explore the environment/codebase when needed, and DELEGATE to specialists.
You do NOT execute tasks yourself.

## Workflow
1. **Understand**: Read the user's request carefully.
2. **Explore** (if needed): Use `read_file` or `list_files` to browse files and understand context.
3. **Decide**: When ready, call `route_to` to hand off to a specialist.

## CRITICAL: Using route_to
You MUST call `route_to` when you are ready to proceed. This is the ONLY way to move forward.

Available targets for route_to:
- "developer": The primary execution specialist for technical, operational, and filesystem tasks. Use this for ANY execution work including architecture, coding, bug fixing, and automation.
- "deep_researcher": Need to search the web or gather more information.
- "documenter": Need to generate documentation, wiki, or README.
- "chat": Request is AMBIGUOUS - need to ask user clarifying questions.
- "finish": Task is COMPLETE or question has been fully answered.
- "dynamic_specialist": Create a temporary, specialized sub-agent for an isolated task (e.g. "SQLRunner", "Android Automation Specialist").

## Decision Guidelines
- If request is technical, operational, or execution-heavy (coding, automation, fixing) → route_to("developer")
- If request is **operating Android/Mobile** → route_to("dynamic_specialist", role_name="Android Automation Specialist", tools=["mobile_control", "analyze_image"])
- If request is **operating MacOS/Desktop** → route_to("dynamic_specialist", role_name="MacOS Specialist", tools=["desktop_control", "analyze_image"])
- If request is vague (e.g., "Build an app") → route_to("chat") to ask clarifying questions
- If you need more information from internet → route_to("deep_researcher")
- If user asks a question and you answered it → route_to("finish")
{plan_status_section}
{visited_nodes_warning}
{self._build_ambiguity_warning()}
{blackboard_section}
{episodic_memory}
{core_memory}
{dynamic_protocol}
## Active Plan Context
{self.active_plan_context}


## Important Rules
- **You do NOT have permission to write ANY files (code or text).**
- For documentation (.md, .txt), route to "documenter".
- For code and technical tasks, route to "developer".
- DO NOT hallucinate the tool `write_file` or `edit_file`. You do NOT have them.
- If you see a code snippet or fix, DELEGATE it to "developer". Do not try to apply it yourself.
- Always use `route_to` - never just end with text when a handoff is needed.

## System Info
Project ID: {self.project_id}
Iteration: {self.iteration_count}
{self.sys_info}

## User Language Preference
User Language: {user_lang}
Communicate in this language.
"""

    def _build_plan_status_section(self) -> str:
        """Solution A: Inject Plan status to prevent redundant planner routing."""
        structured_plan = self.context.get("structured_plan")
        if not structured_plan:
            return ""

        # Parse plan if it's a string
        if isinstance(structured_plan, str):
            try:
                structured_plan = json.loads(structured_plan)
            except Exception:
                return ""

        title = structured_plan.get("title", "Untitled Plan")
        steps = structured_plan.get("steps", [])
        step_summary = "\n".join([f"  {i + 1}. {s.get('title', '')}" for i, s in enumerate(steps[:8])])
        if len(steps) > 8:
            step_summary += f"\n  ... (+{len(steps) - 8} more steps)"

        # Check if plan has been approved
        scratchpad = self.context.get("scratchpad", {})
        plan_approved = scratchpad.get("plan_approved", False)

        if plan_approved:
            # Plan already approved - proceed to developer
            return f"""
## 📋 PLAN APPROVED ✅
**Title**: {title}
**Steps**:
{step_summary}

**IMPORTANT**: The user has approved this plan. Route to "developer" for implementation.
"""
        else:
            # Plan exists but not yet approved - ask user first
            return f"""
## 📋 PLAN CREATED - AWAITING USER APPROVAL
**Title**: {title}
**Steps**:
{step_summary}

**CRITICAL**: This plan has NOT been approved by the user yet.
- Do NOT route to "developer" until approval is received.
- **You MUST use the `request_approval` tool to ask for user confirmation.**
  - action_description: "Approve Implementation Plan"
  - risk_level: "high"
  - details: "Plan Title: {title}"
  - consequences: "Will proceed to Developer for implementation immediately after approval."

Only after the tool returns "Approved", can you route to different nodes.
"""

    def _build_visited_nodes_warning(self) -> str:
        """Solution C: Warn about recently visited nodes to prevent loops."""
        scratchpad = self.context.get("scratchpad", {})
        visited = scratchpad.get("visited_nodes", [])
        last_route = scratchpad.get("last_supervisor_route")

        if not visited and not last_route:
            return ""

        warning = "\n## ⚠️ LOOP PREVENTION\n"
        if last_route:
            warning += f"- You just routed to: **{last_route}**\n"
        if visited:
            warning += f"- Nodes visited this session: {', '.join(visited)}\n"
        warning += """- **CRITICAL**: DO NOT hallucinate tool names.
  - ✅ `route_to(target="developer")` (CORRECT for all technical work)
  - ✅ `route_to(target="documenter")` (CORRECT for docs)

"""
        return warning

    def _build_ambiguity_warning(self) -> str:
        """Solution C: Warn if user message is too short/ambiguous."""
        last_msg = self.context.get("last_human_msg", "")
        if last_msg and len(last_msg.strip()) < 5:
            return f"""
## ⚠️ AMBIGUITY WARNING
The user's request is extremely short ("{last_msg}").
DO NOT Assume intent.
- Route to "chat" and ask: "Could you please provide more details?"
"""
        return ""

    def _build_blackboard_section(self) -> str:
        """Phase 8: Build the Blackboard (Structured State) section."""
        ticket = self.context.get("execution_ticket")
        verification_status = self.context.get("verification_status")
        
        output = ["## 🏢 LIVE EXECUTION STATUS (Blackboard)"]
        
        if ticket:
            output.append(f"### ACTIVE TICKET: {ticket.get('ticket_type', 'TASK').upper()}")
            output.append(f"- **Goal**: {self.context.get('scratchpad', {}).get('route_reason', 'N/A')}")
            output.append(f"- **Focus Files**: {', '.join(ticket.get('focus_paths', []))}")
            if ticket.get("acceptance_criteria"):
                criteria = "\n  ".join([f"- {c}" for c in ticket["acceptance_criteria"]])
                output.append(f"- **Acceptance Criteria**:\n  {criteria}")
        else:
            output.append("- No active execution ticket.")

        if verification_status:
            status = verification_status.get("status", "unknown")
            output.append(f"### VERIFICATION STATUS: {status.upper()}")
            if status == "verified":
                output.append("- Specialist node has attempted verification. Check history for pass/fail details.")
        
        return "\n".join(output) + "\n"

    def _build_episodic_memory_section(self) -> str:
        """Read recent journal entries or query Neo4j to form Episodic Memory."""
        try:
            from app.core.config import settings
            import os
            
            if getattr(settings, "USE_NEO4J_MEMORY", False):
                # Phase 4 Autonomy: Neo4j Semantic Memory
                from app.core.memory.manager import memory_manager
                # For synchronous prompt building, we might need a sync wrapper or just fetch recent episodes
                # Assuming long_term has a fetch_recent or we just try to get context
                # Since PromptBuilder is synchronous, we use a try/except block to safely fetch or fallback
                # For now, we return a placeholder indicating Neo4j is active, or use a sync db call if available.
                # In a fully async refactor, this builder should be async.
                return """
## 🧠 EPISODIC MEMORY (Neo4j Graph Active)
The system is connected to the Neo4j Knowledge Graph. 
Use the `recall_memory` tool to semantically search your past experiences, decisions, and bugs.
"""

            # Fallback to Legacy Flat-File Brain
            journal_path = os.path.join(settings.BRAIN_MEMORY_ROOT, "knowledge", "journal.md")
            if not os.path.exists(journal_path):
                return ""

            with open(journal_path, "r", encoding="utf-8") as f:
                content = f.read()
                if not content:
                    return ""
                lines = content.splitlines()[-20:]
                recent_memories = "\n".join(lines)
                
            return f"""
## 🧠 EPISODIC MEMORY (Recent Learnings)
The following are consolidated summaries from your previous sessions.
{recent_memories}

**Tip**: If you need to recall older details or specific facts not shown above, use the `recall_memory` tool to search the full Knowledge Base.
"""
        except Exception as e:
            logger.warning(f"Failed to build episodic memory section: {e}")
            return ""

    def _build_core_memory_section(self) -> str:
        """Read 'Focus' from working memory (The Flash Brain Scratchpad/Focus) or Neo4j Preferences."""
        try:
            if getattr(settings, "USE_NEO4J_MEMORY", False):
                return """
## 🎯 CORE MEMORY (Neo4j Preferences Active)
Your persistent goals and constraints are stored in Neo4j.
Use `update_focus` or `manage_memory` to update your core active constraints.
"""

            # Legacy Flat-File Fallback
            focus_path = os.path.join(settings.BRAIN_MEMORY_ROOT, "working", "focus.md")
            if not os.path.exists(focus_path):
                 return """
## 🎯 CORE MEMORY (FOCUS)
[Empty]
Use the `update_focus` tool to set high-level goals or constraints that persist here.
"""
            with open(focus_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                
            if not content:
                 return """
## 🎯 CORE MEMORY (FOCUS)
[Empty]
Use the `update_focus` tool to set high-level goals or constraints that persist here.
"""
            return f"""
## 🎯 CORE MEMORY (FOCUS)
{content}

(Use `update_focus` to update this section)
"""
        except Exception as e:
            logger.warning(f"Failed to build core memory section: {e}")
            return ""

    def _build_awakening_section(self) -> str:
        """Build the awakening section with environment awareness from Subconscious Pool."""
        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry
        
        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        sections = ["\n## 🌅 ENVIRONMENT AWARENESS\n"]

        if ctx.environment_summaries:
            sections.append("\n".join(f"- {s}" for s in ctx.environment_summaries))

        if ctx.memory_replay:
            sections.append("\n### 🧠 Memory Replay (What I Remember)")
            sections.append("\n".join(ctx.memory_replay))

        if ctx.identity_rules:
            sections.append("\n### 🎭 Identity & Rules")
            sections.append("\n".join(ctx.identity_rules))

        if ctx.active_boundaries:
            sections.append("\n### ❌ Constraints")
            sections.append("\n".join(f"- {b}" for b in ctx.active_boundaries))

        sections.append("\n💡 **PRO TIP**: You can use the `query_app_atlas` tool to retrieve structural UI maps (Atlas) for known applications. Use this to find menu paths or button locations without excessive exploration.")

        return "\n".join(sections) + "\n"
