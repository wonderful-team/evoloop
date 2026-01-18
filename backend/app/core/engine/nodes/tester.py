import json
import logging
import os
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.core.engine.message_utils import repair_message_history, smart_window_slice
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.core.prompts.tester_builder import TesterPromptBuilder
from app.core.tools.executor import ToolExecutor
from app.core.tools.registry_utils import get_node_tools
from app.domain.testing.parser import TestParser

logger = logging.getLogger(__name__)


# Define Structured Output
class TestAnalysis(BaseModel):
    status: str = Field(description="PASS or FAIL")
    summary: str = Field(description="Brief summary of test execution")
    root_cause: str | None = Field(description="Hypothesis for failure (if FAIL)")
    fix_suggestion: str | None = Field(description="Concrete code snippet or steps to fix the issue (if FAIL). Be extremely specific.")


class TesterNode:
    """
    Intelligent Tester Node:
    1. Looks at what Coder did.
    2. Decides what test to run.
    3. Executes test via MCP `run_command`.
    4. Reports PASS/FAIL using Structured Output.
    """

    def __init__(self):
        self.llm = LLMFactory.create_llm()
        self.tools = get_node_tools("tester")
        self.tool_map = {t.name: t for t in self.tools}
        self.llm_with_tools = self.llm.bind_tools(self.tools)

    async def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """Entry point for the node."""
        messages = state["messages"]

        # 1. Build System Prompt
        # 1a. Generate Project Structure (Context Injection)
        cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
        project_structure = "Tree not available"
        try:
            from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator
            generator = AnnotatedTreeGenerator(cwd, max_depth=3, with_symbols=False, file_limit=30)
            project_structure = await generator.generate()
        except Exception:
            pass

        system_msg = TesterPromptBuilder.build_system_prompt(project_structure=project_structure[:5000])

        # 1b. ATTENTION GUIDANCE HYDRATION (Phase 21)
        scratchpad = state.get("scratchpad", {})
        handoff_context = scratchpad.get("handoff_context", {})
        cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()

        hydration_prompt = await self._hydrate_context(handoff_context, cwd)
        if hydration_prompt:
            system_msg += f"\n\n{hydration_prompt}"

        # 2. Construct Loop Context
        # We use smart_window_slice to keep User Goal + Recent Context
        windowed_messages = smart_window_slice(messages, window_size=5)
        raw_context = [SystemMessage(content=system_msg)] + windowed_messages
        loop_messages = repair_message_history(raw_context)

        cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()

        # 3. Tool Loop (Custom Logic for XML Parsing)
        # NOTE: This loop handles specific post-tool execution logic (report.xml parsing)
        # which is not supported by the generic AgentEngine loop.
        report_analysis = ""

        for _ in range(3):
            # Invoke LLM
            response = await self.llm_with_tools.ainvoke(loop_messages, config=config)
            loop_messages.append(response)

            if not response.tool_calls:
                break

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                tool = self.tool_map.get(tool_name)
                executor = ToolExecutor()

                if tool:
                    result = await executor.execute(tool, tool_args, config=config)

                    # Special handling for test reports (XML)
                    # This logic is unique to Tester, hard to put in generic engine without hooks.
                    result = self._handle_test_report(result, cwd)
                else:
                    result = f"Error: Tool {tool_name} not found"

                # Create Tool Message
                loop_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id, name=tool_name))

        # 4. Final Analysis
        analysis = await self._generate_analysis(loop_messages)

        # 5. Output Construction
        output_msg = self._create_output_artifact(analysis)

        return {
            "test_results": analysis.status,
            "messages": [AIMessage(content=output_msg)],
            "iteration_count": state.get("iteration_count", 0) + 1
        }

    def _handle_test_report(self, tool_output: str, cwd: str) -> str:
        """Check for report.xml and parse it if present."""
        report_file = os.path.join(cwd, "report.xml")
        if os.path.exists(report_file):
            try:
                parsed_report = TestParser.parse_junit_xml(report_file)

                if not parsed_report.is_pass:
                    # Format failures for LLM
                    fail_txt = "\n".join([f"FAIL: {f.name}\nMsg: {f.message}\nTrace: {f.stack_trace[:500]}..." for f in parsed_report.failed_cases])
                    report_analysis = f"TEST REPORT PARSED:\nFailed: {parsed_report.failures}\nDetails:\n{fail_txt}"
                else:
                    report_analysis = "TEST REPORT: ALL PASSED."

                tool_output = f"{tool_output}\n\n{report_analysis}"

                # Cleanup
                os.remove(report_file)
            except Exception as e:
                logger.warning(f"Failed to parse report.xml: {e}")

        return tool_output

    async def _generate_analysis(self, history: list[Any]) -> TestAnalysis:
        """Run structured output extraction on the interaction history."""
        structured_llm = self.llm.with_structured_output(TestAnalysis)

        instruction = TesterPromptBuilder.build_structured_output_prompt()

        # Phase 18 Fix: Filter out all SystemMessages to avoid "multiple non-consecutive system messages" error
        non_system_history = [msg for msg in history if not isinstance(msg, SystemMessage)]
        final_prompt = [SystemMessage(content=instruction)] + non_system_history

        try:
            result = await structured_llm.ainvoke(final_prompt, config={"callbacks": []})
            if result is None:
                logger.warning("[TesterNode] LLM returned None for analysis.")
                return TestAnalysis(status="FAIL", summary="LLM Verification Failed (Empty Response)", root_cause="LLM Output Error", fix_suggestion="Check LLM logs")
            return result
        except Exception as e:
            return TestAnalysis(status="FAIL", summary=f"Error analyzing tests: {e}", root_cause="LLM Error", fix_suggestion="Check logs")

    def _create_output_artifact(self, analysis: TestAnalysis) -> str:
        """Format the final JSON output."""
        artifact = {
            "type": "artifact",
            "artifact_type": "test_report",
            "data": {
                "status": analysis.status,
                "summary": analysis.summary,
                "root_cause": analysis.root_cause,
                "fix_suggestion": analysis.fix_suggestion,
                "failures": []
            }
        }
        return json.dumps(artifact, ensure_ascii=False)

    async def _hydrate_context(self, context: dict, cwd: str) -> str:
        """
        Hydrate context pointers into actual content.
        Protocol: Attention Guidance (Phase 21).
        """
        output = []
        focus_paths = context.get("focus_paths", [])

        if not focus_paths:
            return ""

        output.append("### SUPERVISOR HANDOFF CONTEXT (ATTENTION GUIDANCE)")
        output.append(f"The Supervisor has identified {len(focus_paths)} focus files for you. I have pre-read them:")

        for rel_path in focus_paths:
            try:
                # Sanitize path
                full_path = os.path.join(cwd, rel_path)
                if not os.path.exists(full_path):
                    output.append(f"- [MISSING] {rel_path} (Supervisor pointed to non-existent file)")
                    continue

                # Check size
                size = os.path.getsize(full_path)
                if size > 20_000:  # 20KB limit for auto-read
                    output.append(f"- [SKIPPED] {rel_path} (Too large {size}b - Read manually if needed)")
                    continue

                # Read content
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                output.append(f"\n--- FILE: {rel_path} ---\n{content}\n--- END OF FILE ---\n")

            except Exception as e:
                output.append(f"- [ERROR] {rel_path}: {e}")

        return "\n".join(output) + "\n"


# Legacy function entry point for Graph
tester_node = TesterNode()
