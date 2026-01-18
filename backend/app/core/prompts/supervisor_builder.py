"""
Supervisor Prompt Builder

Constructs the system prompt for the Supervisor ReAct Agent.
Allows for dynamic context injection and potential LLM-specific adaptations.
"""
import json

from langchain_core.runnables import RunnableConfig
from app.domain.system.service import SystemConfigService


class SupervisorPromptBuilder:
    def __init__(self,
                 project_id: int,
                 active_plan_context: str,
                 iteration_count: int,
                 sys_info: str,
                 context: dict = None):
        self.project_id = project_id
        self.active_plan_context = active_plan_context
        self.iteration_count = iteration_count
        self.sys_info = sys_info
        self.context = context or {}

    def build(self, config: RunnableConfig) -> str:
        """Constructs the full system prompt."""
        user_lang = self._get_user_language()

        # Solution A: Build Plan Status Section
        plan_status_section = self._build_plan_status_section()

        # Solution C: Build Visited Nodes Warning
        visited_nodes_warning = self._build_visited_nodes_warning()

        return f"""You are the Supervisor of an elite coding team.

## Your Role
You are a MANAGER. You analyze user requests, explore the codebase when needed, and DELEGATE to specialists.
You do NOT write application code yourself.

## Workflow
1. **Understand**: Read the user's request carefully.
2. **Explore** (if needed): Use `read_file` or `list_files` to browse files and understand context.
3. **Decide**: When ready, call `route_to` to hand off to a specialist.

## CRITICAL: Using route_to
You MUST call `route_to` when you are ready to proceed. This is the ONLY way to move forward.

Available targets for route_to:
- "planner": Task is complex, needs architectural planning BEFORE coding
- "coder": You have a clear plan or the task is simple enough to implement directly
- "tester": User wants to run tests or verify code
- "deep_researcher": Need to search the web or gather more information
- "documenter": Need to generate documentation, wiki, or README
- "chat": Request is AMBIGUOUS - need to ask user clarifying questions
- "finish": Task is COMPLETE or question has been fully answered

## Decision Guidelines
- If request is vague (e.g., "Build an app") → route_to("chat") to ask clarifying questions
- If request is complex but clear → route_to("planner") for architecture planning
- If you have a plan or task is simple → route_to("coder") for implementation
- If user asks a question and you answered it → route_to("finish")
- If you need more information from internet → route_to("deep_researcher")
{plan_status_section}
{visited_nodes_warning}
## Active Plan Context
{self.active_plan_context}

## Important Rules
## Important Rules
- **You do NOT have permission to write ANY files (code or text).**
- For documentation (.md, .txt), route to "documenter".
- For code (.py, .ts), route to "coder".
- DO NOT hallucinate the tool `write_file`. You do NOT have it.
- Always use `route_to` - never just end with text when a handoff is needed

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
            except:
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
            # Plan already approved - proceed to coder
            return f"""
## 📋 PLAN APPROVED ✅
**Title**: {title}
**Steps**:
{step_summary}

**IMPORTANT**: The user has approved this plan. Route to "coder" for implementation.
"""
        else:
            # Plan exists but not yet approved - ask user first
            return f"""
## 📋 PLAN CREATED - AWAITING USER APPROVAL
**Title**: {title}
**Steps**:
{step_summary}

**CRITICAL**: This plan has NOT been approved by the user yet.
- Do NOT route to "planner" (plan already exists)
- Do NOT route to "coder" (user must approve first)
- **You MUST use the `request_approval` tool to ask for user confirmation.**
  - action_description: "Approve Implementation Plan"
  - risk_level: "high"
  - details: "Plan Title: {title}"
  - consequences: "Will proceed to Coder for implementation immediately after approval."

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
        warning += """- **Do NOT route to the same node repeatedly.** If stuck, route to 'chat' to ask user for guidance.
- **CRITICAL**: DO NOT hallucinate tool names.
  - ❌ `route_to_coder` (INVALID)
  - ❌ `route_to_planner` (INVALID)
  - ✅ `route_to(target="coder")` (CORRECT)
  - ✅ `route_to(target="planner")` (CORRECT)
"""
        return warning

    def _get_user_language(self) -> str:
        return SystemConfigService.get_language_preference()
