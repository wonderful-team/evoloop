import json
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.core.workflows.state import AgentState
from app.domain.tools.registry import get_all_tools
from app.core.tools.executor import ToolExecutor
from app.core.llm.factory import LLMFactory
from app.domain.testing.parser import TestParser

from pydantic import BaseModel, Field

from typing import Optional, List
from langchain_core.runnables import RunnableConfig

# Define Structured Output
class TestAnalysis(BaseModel):
    status: str = Field(description="PASS or FAIL")
    summary: str = Field(description="Brief summary of test execution")
    root_cause: Optional[str] = Field(description="Hypothesis for failure (if FAIL)")
    fix_suggestion: Optional[str] = Field(description="Concrete code snippet or steps to fix the issue (if FAIL). Be extremely specific.")
    


def _repair_history(messages: list) -> list:
    """
    Ensure no ToolMessage is orphaned (without preceding AIMessage with tool_calls).
    If found, insert a dummy AIMessage.
    """
    repaired = []
    
    for msg in messages:
        if isinstance(msg, ToolMessage):
            # Check previous
            is_orphaned = True
            if repaired:
                last = repaired[-1]
                if isinstance(last, AIMessage) and last.tool_calls:
                    # Check ID match
                    ids = [tc['id'] for tc in last.tool_calls]
                    if msg.tool_call_id in ids:
                         is_orphaned = False
            
            if is_orphaned:
                 # Insert Dummy AIMessage
                 dummy = AIMessage(content="Thinking...", tool_calls=[
                     {"id": msg.tool_call_id, "name": "unknown_tool", "args": {}}
                 ])
                 repaired.append(dummy)
        
        repaired.append(msg)
        
    return repaired

async def tester_node(state: AgentState, config: RunnableConfig):
    llm = LLMFactory.create_llm()
    """
    Intelligent Tester:
    1. Looks at what Coder did.
    2. Decides what test to run.
    3. Executes test via MCP `run_command`.
    4. Reports PASS/FAIL using Structured Output.
    """
    messages = state["messages"]

    # Language Preference
    from app.domain.system.service import SystemConfigService
    user_lang = SystemConfigService.get_language_preference()

    # Tester System Prompt
    system_msg = f"""You are a Senior QA Engineer.
    The Coder has just written/modified code. Your job is to VERIFY it.
    
    Tools:
    - run_command(command): Run tests (e.g., `pytest`, `python -m ...`).
    - browser_agent(task): Use a browser to verify web apps.
    
    Strategy:
    1. Identify what files changed.
    2. Run relevant tests. If no tests exist, try to run the code itself.
    3. **PROTOCOL**: When running pytest, ALWAYS use `pytest --junitxml=report.xml` to generate a structured report. 
    4. If tests fail, analyze the specific *stack trace* provided in the tool output.
    5. Generate a Fix Suggestion in the final output.
    
    If you see a `report.xml` parsed output, TRUST IT.

    LANGUAGE PROTOCOL:
    User Preference: {user_lang}
    You MUST write your Test Analysis, Summary, and Fix Suggestion in {user_lang}.
    """

    # RBAC Tools for Tester
    from app.core.tools.registry_utils import get_node_tools
    tools = get_node_tools("tester")
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    # Construct and Repair Context
    raw_context = [SystemMessage(content=system_msg)] + messages[-5:]
    loop_messages = _repair_history(raw_context)

    import os
    cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
    
    # Run Tool Loop (Max 3 steps)
    report_analysis = ""
    
    for _ in range(3):
        response = await llm_with_tools.ainvoke(loop_messages, config=config)
        loop_messages.append(response)

        if not response.tool_calls:
            # Agent wants to finish (talks to user/system)
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            tool = tool_map.get(tool_name)
            executor = ToolExecutor()
            
            if tool:
                result = await executor.execute(tool, tool_args, config=config)
                
                # Special handling for test reports
                report_file = os.path.join(cwd, "report.xml")
                if os.path.exists(report_file):
                    parsed_report = TestParser.parse_junit_xml(report_file)
                    
                    if not parsed_report.is_pass:
                        # Format failures for LLM
                        fail_txt = "\n".join([f"FAIL: {f.name}\nMsg: {f.message}\nTrace: {f.stack_trace[:500]}..." for f in parsed_report.failed_cases])
                        report_analysis = f"TEST REPORT PARSED:\nFailed: {parsed_report.failures}\nDetails:\n{fail_txt}"
                    else:
                        report_analysis = "TEST REPORT: ALL PASSED."
                        
                    result = f"{result}\n\n{report_analysis}"
                    
                    # Cleanup
                    try:
                        os.remove(report_file)
                    except:
                        pass
            else:
                 result = f"Error: Tool {tool_name} not found"

            loop_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    # Final Verification Step: Structured Output
    structured_llm = llm.with_structured_output(TestAnalysis)
    
    # We feed the FULL conversation (including potential tool outputs) to the structured LLM
    # to let it summarize the result. Matches Loop Messages.
    # Note: loop_messages already includes system msg and tools.
    
    final_prompt = [
        SystemMessage(content="Analyze the test execution above. Provide a structured report in JSON format. If failed, you MUST provide a fix_suggestion based on the stack trace."),
    ] + loop_messages[1:] # Skip original system message to avoid duplication if we want, but loop_messages has the history.
    
    # Actually, structured_llm needs Clean History too. loop_messages IS clean (repaired).
    # But loop_messages[0] is SystemMessage. We can replace it or just append.
    # Let's just use loop_messages but prepend the instruction.
    
    final_prompt = [SystemMessage(content="Analyze the test execution above...")] + loop_messages[1:]
    
    try:
        analysis = await structured_llm.ainvoke(final_prompt, config={"callbacks": []})
    except Exception as e:
        # Fallback
        analysis = TestAnalysis(status="FAIL", summary=f"Error analyzing tests: {e}", root_cause="LLM Error", fix_suggestion="Check logs")

    # Format output for next node (Coder or Supervisor)
    
    # Construct JSON Artifact
    artifact = {
        "type": "artifact",
        "artifact_type": "test_report",
        "data": {
            "status": analysis.status,
            "summary": analysis.summary,
            "root_cause": analysis.root_cause,
            "fix_suggestion": analysis.fix_suggestion,
            "failures": [] # We could populate this from test_results if we parsed them in detail here, but analysis.summary usually covers it.
        }
    }
    
    # Add failure details if available in parsed results (optional, requires passing more data from run_tests)
    # For now, relying on analysis fields.
    
    output_msg = json.dumps(artifact, ensure_ascii=False)

    return {
        "test_results": analysis.status,
        "messages": [AIMessage(content=output_msg)],
        "iteration_count": state.get("iteration_count", 0) + 1
    }
