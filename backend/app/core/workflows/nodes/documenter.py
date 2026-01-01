from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from app.core.config import settings
from app.core.workflows.state import AgentState
from app.domain.tools.registry import get_all_tools
from app.core.llm.factory import LLMFactory
from app.core.tools.executor import ToolExecutor

import logging
import os
import json

logger = logging.getLogger(__name__)

# Re-use DeepResearcher logic but wrapped for documentation purpose
# Or we can just include the "Deep Research" loop inside here if we want tighter control.
# For now, let's make it a high-level orchestrator.

FILE_STRUCTURE_PROMPT = """You are a Technical Documentation Architect.

Your goal is to design a Wiki structure for this project.
Based on the project structure, list the essential documentation pages we should create.
Strictly focus on internal technical documentation for developers.

Project Root:
{tree}

Common Pages (create these if relevant):
- Overview/Introduction
- System Architecture
- API Reference
- Database Schema
- Component Interaction
- Configuration & Ops

Output a JSON list of objects:
[
  {{"filename": "overview.md", "topic": "Project Overview & Core Features"}},
  {{"filename": "architecture.md", "topic": "System Architecture & Design Patterns"}},
  ...
]
Output ONLY JSON.
"""


async def documenter_node(state: AgentState, config: RunnableConfig):
    """
    Documenter Agent:
    1. Analyzes project structure.
    2. Plans a documentation structure (Wiki).
    3. For each page, triggers a Deep Research session to write the content.
    4. Saves the files.
    """
    # 1. Get Project Structure
    # We can use the MCP tool 'get_annotated_tree' manually here
    annotated_tree_tool = None
    tools = get_all_tools()
    for t in tools:
        if t.name == "get_annotated_tree":
            annotated_tree_tool = t
            break
    
    tree_output = ""
    if annotated_tree_tool:
        executor = ToolExecutor()
        tree_output = await executor.execute(annotated_tree_tool, {"max_lines": 500}, config=config)
        if str(tree_output).startswith("Error"):
             tree_output = f"(Tree generation failed: {tree_output})"
    
    # 2. Plan Structure (Using LLM directly)
    from pydantic import BaseModel, Field
    from typing import List

    class WikiPage(BaseModel):
        filename: str = Field(description="Filename including extension, e.g., overview.md")
        topic: str = Field(description="The main topic to be covered in this page")

    class WikiPlan(BaseModel):
        pages: List[WikiPage] = Field(description="List of wiki pages to create")

    llm = LLMFactory.create_llm()
    structured_llm = llm.with_structured_output(WikiPlan)
    
    try:
        plan: WikiPlan = await structured_llm.ainvoke([HumanMessage(content=FILE_STRUCTURE_PROMPT.format(tree=tree_output))], config=config)
        pages = [p.model_dump() for p in plan.pages]
        
    except Exception as e:
        logger.error(f"Failed to parse documentation plan: {e}")
        return {
            "messages": [AIMessage(content=f"Error planning documentation: {e}")]
        }
    
    # 3. Generate Pages (Iterative Deep Research)
    from app.domain.research.engine import DeepResearchEngine
    
    # Initialize Engine
    engine = DeepResearchEngine(llm)
    
    docs_dir = os.path.join(settings.PROJECT_ROOT, "docs", "wiki")
    os.makedirs(docs_dir, exist_ok=True)
    
    generated_pages = []
    
    for page in pages:
        filename = page.get('filename')
        topic = page.get('topic')
        
        if not filename or not topic:
            continue
            
        logger.info(f"Generating Wiki Page: {filename} ({topic})")
        
        try:
            # Trigger Deep Research Loop
            # We use a reduced iteration count (e.g. 3) for docs to save time, unless it's complex
            content = await engine.run(topic=f"Write a comprehensive documentation page about: {topic}. This is for the file {filename}.", max_iterations=3, config=config)
            
            # Save to file
            file_path = os.path.join(docs_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            generated_pages.append(f"{filename} ({len(content)} chars)")
            
        except Exception as e:
            logger.error(f"Failed to generate {filename}: {e}")
            generated_pages.append(f"{filename} (FAILED: {e})")

    return {
        "messages": [AIMessage(content=f"Wiki Generation Complete.\nPages created:\n" + "\n".join(generated_pages))]
    }
