"""
Supervisor Prompt Builder

Constructs the system prompt for the Supervisor ReAct Agent.
Allows for dynamic context injection and potential LLM-specific adaptations.
"""

import json

from langchain_core.runnables import RunnableConfig

from app.core.system import SystemConfigService


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
        user_lang = self._get_user_language()

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
   - SQL: `["sql_query"]` (if available)
2. **Memory Write Ban**: NEVER grant `manage_memory` to dynamic agents unless the role is explicitly "KnowledgeHarvester".
   - Sub-agents are "Stateless". They should not pollute the long-term memory.
3. **No Human Contact**: NEVER grant `request_approval` or `chat`. Sub-agents cannot talk to the user.
"""
        return f"""You are the Supervisor of an elite coding team.
{awakening_section}
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
- "developer": The primary execution specialist. Use this for ANY technical task, including architecture, coding, bug fixing, testing, **Android mobile control**, and **MacOS desktop control**. It is your only technical worker.
- "deep_researcher": Need to search the web or gather more information.
- "documenter": Need to generate documentation, wiki, or README.
- "chat": Request is AMBIGUOUS - need to ask user clarifying questions.
- "finish": Task is COMPLETE or question has been fully answered.
- "dynamic_specialist": Create a temporary, specialized sub-agent for an isolated task (e.g. "SQLRunner").

## Decision Guidelines
- If request is technical (coding, refactoring, testing, bug fixing, **operating Android/Mac**) → route_to("developer")
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
        test_results = self.context.get("structured_test_results")
        
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

        if test_results:
            status = test_results.get("status", "unknown")
            output.append(f"### VERIFICATION STATUS: {status.upper()}")
            if status == "verified":
                output.append("- Specialist node has attempted verification. Check history for pass/fail details.")
        
        return "\n".join(output) + "\n"

    def _build_episodic_memory_section(self) -> str:
        """Read recent journal entries to form Episodic Memory."""
        try:
            from app.core.config import settings
            import os
            
            journal_path = os.path.join(settings.BRAIN_MEMORY_ROOT, "knowledge", "journal.md")
            if not os.path.exists(journal_path):
                return ""
            
            # Read last 20 lines
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
        except Exception:
            return ""

    def _build_core_memory_section(self) -> str:
        """Read 'Focus' from working memory (The Flash Brain Scratchpad/Focus)."""
        try:
            from app.core.config import settings
            import os
            
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
        except Exception:
            return ""

    def _build_awakening_section(self) -> str:
        """Build the awakening section with environment awareness."""
        try:
            from app.core.environment import get_awakened_state
            state = get_awakened_state()
            
            if not state:
                return ""
            
            sections = ["\n## 🌅 I HAVE JUST AWAKENED\n"]
            
            # --- Environment Awareness ---
            sections.append("### 🌐 Environment Awareness")
            if state.macos:
                sections.append(f"- **Host**: {state.macos.model} ({state.macos.cpu}), macOS {state.macos.os_version}, {state.macos.ram_gb}GB RAM")
            
            if state.android_devices:
                for dev in state.android_devices:
                    emoji = "✅" if dev.is_reachable else "⚠️"
                    sections.append(f"- **Mobile**: {emoji} {dev.model} (Android {dev.os_version}), Battery: {dev.battery_percent}%")
            else:
                sections.append("- **Mobile**: ⚠️ No Android devices connected.")
            
            # --- Memory Replay ---
            if state.recent_episodes or state.relevant_concepts or state.journal_highlights:
                sections.append("\n### 🧠 Memory Replay (What I Remember)")
                
                if state.recent_episodes:
                    sections.append("**Recent Tasks:**")
                    for ep in state.recent_episodes[:3]:
                        sections.append(f"- [{ep.date}] {ep.goal} → {ep.result}")
                
                if state.relevant_concepts:
                    concept_names = ", ".join([c.name for c in state.relevant_concepts[:5]])
                    sections.append(f"**Key Knowledge:** {concept_names}")
                
                if state.journal_highlights:
                    sections.append(f"**Recent Learnings:**\n{state.journal_highlights}")
            
            # --- Preferences & Rules ---
            if state.user_preferences or state.system_rules:
                sections.append("\n### 🎭 My Identity & Rules")
                
                if state.user_preferences:
                    prefs = ", ".join([f"{k}={v}" for k, v in list(state.user_preferences.items())[:5]])
                    sections.append(f"- **User Preferences**: {prefs}")
                
                if state.system_rules:
                    sections.append("- **Inviolable Rules**:")
                    for rule in state.system_rules[:3]:
                        sections.append(f"  - ❌ {rule}")
            
            # --- Capability Boundaries ---
            if state.capability_boundaries:
                sections.append("\n### ❌ What I CANNOT Do")
                for boundary in state.capability_boundaries[:4]:
                    sections.append(f"- {boundary}")
            
            return "\n".join(sections) + "\n"
            
        except Exception:
            return ""

    def _get_user_language(self) -> str:
        return SystemConfigService.get_language_preference()
