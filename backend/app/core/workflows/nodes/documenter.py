import logging
import os

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from app.core.config import settings
from app.core.workflows.state import AgentState
from app.domain.tools.registry import get_all_tools
from app.core.llm.factory import LLMFactory
from app.core.tools.executor import ToolExecutor

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

Output a JSON object with a "pages" key:
{{
  "pages": [
    {{"filename": "overview.md", "topic": "Project Overview & Core Features"}},
    ...
  ]
}}
"""


async def documenter_node(state: AgentState, config: RunnableConfig):
    """
    Documenter Agent:
    Phase 1: Analyzes project structure -> Generates Plan -> Requests Approval.
    Phase 2: Resumes -> Checks Approval -> Generates Content.
    """
    import json
    from app.core.tools.executor import ToolExecutor
    from langchain_core.messages import ToolMessage
    
    # Check for pending plan
    pending_plan_json = state.get("pending_wiki_plan")
    
    # Phase 2: Execution (Resume)
    if pending_plan_json:
        logger.info("Resuming Documenter: Found pending plan.")
        
        # Check if user approved.
        # Implied: If we are back here, the Supervisor routed us here.
        # Supervisor only routes here if the user said "Yes" or we force routed back.
        # Let's perform a safety check on the last message.
        messages = state.get("messages", [])
        last_msg = messages[-1]
        
        is_approved = False
        if isinstance(last_msg, HumanMessage):
             # Simple heuristic for "Yes"
             if "yes" in last_msg.content.lower() or "approve" in last_msg.content.lower() or "ok" in last_msg.content.lower():
                 is_approved = True
        
        if not is_approved:
            # Maybe they said "No" or "Change X".
            # For "No", we abort.
            if "no" in last_msg.content.lower() and len(last_msg.content) < 10:
                return {
                    "messages": [AIMessage(content="Documentation plan cancelled by user.")],
                    "pending_wiki_plan": None # Clear it
                }
            # For "Change X", we arguably should Re-Plan. 
            # For simple MVP, let's treat non-approval as "Re-Plan" request.
            logger.info("User did not explicitly approve. Treating as Re-Plan request.")
            # Fallthrough to Phase 1, but maybe we should clear the pending plan first?
            # Actually, to re-plan, we just overwrite pending_wiki_plan with new one.
            # So we can just let it fall through to Phase 1 logic below?
            # Wait, if we fall through, we generate a NEW plan.
            pass
        else:
            # EXECUTION
            try:
                plan_data = json.loads(pending_plan_json)
                pages = plan_data
            except:
                return {"messages": [AIMessage(content="Error loading pending plan. Please try again.")], "pending_wiki_plan": None}

            # 3. Generate Pages (Iterative Deep Research)
            from app.domain.research.engine import DeepResearchEngine
            
            # Initialize Engine
            llm = LLMFactory.create_llm()
            engine = DeepResearchEngine(llm)
            
            docs_dir = os.path.join(settings.PROJECT_ROOT, "docs", "wiki")
            os.makedirs(docs_dir, exist_ok=True)
            
            generated_pages = []
            
            # Language Preference
            from app.domain.system.service import SystemConfigService
            user_lang = SystemConfigService.get_language_preference()
            
            for page in pages:
                filename = page.get('filename')
                topic = page.get('topic')
                
                if not filename or not topic:
                    continue
                    
                logger.info(f"Generating Wiki Page: {filename} ({topic})")
                
                try:
                    # Trigger Deep Research Loop
                    prompt_content = f"Write a comprehensive documentation page about: {topic}. This is for the file {filename}.\n\nIMPORTANT: Write the documentation content in {user_lang}."
                    content = await engine.run(topic=prompt_content, max_iterations=3, config=config)
                    
                    # Save to file
                    file_path = os.path.join(docs_dir, filename)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                        
                    generated_pages.append(f"{filename} ({len(content)} chars)")
                    
                except Exception as e:
                    logger.error(f"Failed to generate {filename}: {e}")
                    generated_pages.append(f"{filename} (FAILED: {e})")
            
            msg_content = f"Wiki Generation Complete.\nPages created:\n" + "\n".join(generated_pages)
            
            return {
                "messages": [AIMessage(content=msg_content)],
                "pending_wiki_plan": None # Clear state
            }

    # Phase 1: Planning (Draft)
    # 2. Get Project Structure
    tree_output = ""
    try:
        from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator
        root_path = config.get("configurable", {}).get("working_directory", ".")
        generator = AnnotatedTreeGenerator(root_path, max_depth=3, with_symbols=False, file_limit=30)
        tree_output = await generator.generate()
    except Exception as e:
        tree_output = f"(Tree generation failed: {e})"
    
    # 2. Plan Structure
    from pydantic import BaseModel, Field
    from typing import List

    class WikiPage(BaseModel):
        filename: str = Field(description="Filename including extension, e.g., overview.md")
        topic: str = Field(description="The main topic to be covered in this page")

    class WikiPlan(BaseModel):
        pages: List[WikiPage] = Field(description="List of wiki pages to create")

    llm = LLMFactory.create_llm()
    structured_llm = llm.with_structured_output(WikiPlan)
    
    # Language Preference
    from app.domain.system.service import SystemConfigService
    user_lang = SystemConfigService.get_language_preference()
    
    lang_directive = f"""LANGUAGE PROTOCOL:
    User Preference: {user_lang}.
    All documentation topics and filenames (if appropriate) should respect this language.
    Specifically, the 'topic' description should be in {user_lang}.
    """
    
    try:
        from langchain_core.messages import SystemMessage
        msgs = [
            SystemMessage(content=lang_directive),
            HumanMessage(content=FILE_STRUCTURE_PROMPT.format(tree=tree_output))
        ]
        
        # Prevent streaming the raw JSON to the frontend
        clean_config = config.copy() if config else {}
        clean_config["callbacks"] = []
        
        plan: WikiPlan = await structured_llm.ainvoke(msgs, config=clean_config)
        pages = [p.model_dump() for p in plan.pages]
        
        # Save to State
        plan_json = json.dumps(pages)
        
        # Generate Approval Message
        plan_summary = "\n".join([f"- **{p['filename']}**: {p['topic']}" for p in pages])
        approval_msg = f"I have designed the following Wiki structure based on your project:\n\n{plan_summary}\n\nDo you want me to proceed with generating these files?"
        
        # Trigger Approval Tool
        from app.domain.tools.human_input import request_approval

        # Format plan as Markdown for better readability in the Approval Card
        plan_md = "| Filename | Topic |\n|---|---|\n"
        for p in pages:
            plan_md += f"| `{p['filename']}` | {p['topic']} |\n"

        await request_approval.ainvoke({
            "action_description": "Create Wiki Documentation based on Project Structure",
            "risk_level": "low",
            "details": f"**Proposed File Structure:**\n\n{plan_md}",
            "consequences": f"This will create {len(pages)} new files in `docs/wiki/`. Existing files with same names will be overwritten."
        }, config=config)
        
        # Return state
        return {
            "messages": [
                AIMessage(content=approval_msg),
            ],
            "pending_wiki_plan": plan_json
        }
        
    except Exception as e:
        logger.error(f"Failed to parse documentation plan: {e}")
        return {
            "messages": [AIMessage(content=f"Error planning documentation: {e}")]
        }
