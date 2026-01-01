import json
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.core.workflows.state import AgentState
from app.domain.tools.registry import get_all_tools
from app.core.tools.executor import ToolExecutor
from app.core.llm.factory import LLMFactory

llm = LLMFactory.create_llm()

from langchain_core.runnables import RunnableConfig


async def tester_node(state: AgentState, config: RunnableConfig):
    """
    Intelligent Tester:
    1. Looks at what Coder did.
    2. Decides what test to run.
    3. Executes test via MCP `run_command`.
    4. Reports PASS/FAIL.
    """
    messages = state["messages"]

    # Tester System Prompt
    system_msg = """You are a QA Engineer.
    The Coder has just written/modified code. Your job is to VERIFY it.
    
    Tools:
    - run_command(command): Run tests (e.g., `pytest`, `python -m ...`).
    - browser_agent(task): Use a browser to verify web apps (e.g., "Open localhost:3000 and check login").
    
    Strategy:
    1. Identify what files changed (look at context or recent messages).
    2. Run relevant tests. If no tests exist, try to run the code itself.
    3. **PROTOCOL**: When running pytest, ALWAYS use `pytest --junitxml=report.xml` to generate a structured report. The system will automatically parse this file for you.
    4. Analyze the output (and any parsed report).
    5. If tests pass, report PASS.
    6. If tests fail, report FAIL and provide a Root Cause Analysis (RCA).
    
    ### OUTPUT FORMAT (MANDATORY)
    If PASS:
    PASS: <Brief confirmation>
    
    If FAIL:
    FAIL: <Summary of failure>
    RCA: <Hypothesis on WHY it failed. Be specific about lines or logic.>
    Suggestion: <Code snippet or step to fix it.>
    """

    tools = get_all_tools()
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    loop_messages = [AIMessage(content=system_msg)] + messages[-3:]  # Context

    final_status = "FAIL"  # Default to fail if unsure

    import os
    import xml.etree.ElementTree as ET
    
    # helper to parse report
    def parse_test_report(report_path):
        try:
            tree = ET.parse(report_path)
            root = tree.getroot()
            failures = []
            for testcase in root.iter("testcase"):
                # Check for failure or error
                failure = testcase.find("failure")
                error = testcase.find("error")
                if failure is not None:
                    msg = failure.attrib.get("message", "Unknown failure")
                    text = failure.text or ""
                    failures.append(f"FAIL: {testcase.attrib.get('name')} - {msg}\n{text[:300]}...")
                elif error is not None:
                     msg = error.attrib.get("message", "Unknown error")
                     failures.append(f"ERROR: {testcase.attrib.get('name')} - {msg}")
            
            if not failures:
                return "Report parsed: All tests passed."
            return "Report parsed:\n" + "\n".join(failures)
        except Exception as e:
            return f"Failed to parse report: {e}"

    cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()

    for _ in range(3):
        response = await llm_with_tools.ainvoke(loop_messages, config=config)
        loop_messages.append(response)

        if not response.tool_calls:
            # Agent finished
            content = response.content.upper()
            if "PASS" in content and "FAIL" not in content:
                final_status = "PASS"
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
                    parsed_report = parse_test_report(report_file)
                    result = f"{result}\n\n{parsed_report}"
                    # Cleanup
                    try:
                        os.remove(report_file)
                    except:
                        pass
            else:
                 result = f"Error: Tool {tool_name} not found"

            loop_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    return {
        "test_results": final_status,
        "messages": [AIMessage(content=f"Test Phase Complete. Result: {final_status}")]
    }
