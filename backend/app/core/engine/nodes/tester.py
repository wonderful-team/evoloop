import json
import logging
import os
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.core.engine.message_utils import repair_message_history
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
        system_msg = TesterPromptBuilder.build_system_prompt()

        # 2. Construct Loop Context
        # We take last 5 messages + System Prompt
        raw_context = [SystemMessage(content=system_msg)] + messages[-5:]
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
        final_prompt = [SystemMessage(content=instruction)] + history[1:]

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


# Legacy function entry point for Graph
tester_node = TesterNode()

