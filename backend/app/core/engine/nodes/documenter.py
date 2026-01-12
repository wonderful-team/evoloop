import logging
import os

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)

# Re-use DeepResearcher logic but wrapped for documentation purpose
# Or we can just include the "Deep Research" loop inside here if we want tighter control.
# For now, let's make it a high-level orchestrator.

# Re-use DeepResearcher logic but wrapped for documentation purpose
# Or we can just include the "Deep Research" loop inside here if we want tighter control.
# For now, let's make it a high-level orchestrator.


async def documenter_node(state: AgentState, config: RunnableConfig):
    """
    Documenter Agent:
    Phase 1: Analyzes project structure -> Generates Plan -> Requests Approval.
    Phase 2: Resumes -> Checks Approval -> Generates Content.
    """
    import json


    # Check for pending plan in hitl_state
    hitl = state.get("hitl_state")
    pending_plan_json = hitl.get("context", {}).get("wiki_plan") if hitl else None

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
                    "hitl_state": None  # Clear HITL state
                }
            # Non-approval treated as re-plan request - fall through to Phase 1
            logger.info("User did not explicitly approve. Treating as Re-Plan request.")
            pass
        else:
            # EXECUTION
            try:
                plan_data = json.loads(pending_plan_json)
                pages = plan_data
            except:
                return {"messages": [AIMessage(content="Error loading pending plan. Please try again.")], "hitl_state": None}

            # 3. Generate Pages (Iterative Deep Research)
            from app.domain.research.engine import DeepResearchEngine

            # Initialize Engine
            llm = LLMFactory.create_llm()
            engine = DeepResearchEngine(llm)

            docs_dir = os.path.join(settings.PROJECTS_ROOT, "docs", "wiki")
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
                    # Use Builder for prompt
                    from app.core.prompts.documenter_builder import (
                        DocumenterPromptBuilder,
                    )
                    prompt_content = DocumenterPromptBuilder.build_page_generation_prompt(topic, filename)

                    content = await engine.run(topic=prompt_content, max_iterations=3, config=config)

                    # Save to file
                    file_path = os.path.join(docs_dir, filename)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)

                    generated_pages.append(f"{filename} ({len(content)} chars)")

                except Exception as e:
                    logger.error(f"Failed to generate {filename}: {e}")
                    generated_pages.append(f"{filename} (FAILED: {e})")

            msg_content = "Wiki Generation Complete.\nPages created:\n" + "\n".join(generated_pages)

            return {
                "messages": [AIMessage(content=msg_content)],
                "hitl_state": None  # Clear HITL state
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

    class WikiPage(BaseModel):
        filename: str = Field(description="Filename including extension, e.g., overview.md")
        topic: str = Field(description="The main topic to be covered in this page")

    class WikiPlan(BaseModel):
        pages: list[WikiPage] = Field(description="List of wiki pages to create")

    llm = LLMFactory.create_llm()
    structured_llm = llm.with_structured_output(WikiPlan)

    # Language Preference
    from app.domain.system.service import SystemConfigService
    user_lang = SystemConfigService.get_language_preference()

    try:
        from app.core.prompts.documenter_builder import DocumenterPromptBuilder

        # Builder handles language injection internally now
        prompt_content = DocumenterPromptBuilder.build_file_structure_prompt(tree_output)

        msgs = [
            HumanMessage(content=prompt_content)
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

        # Trigger Approval Tool... UNLESS configured to skip
        from app.domain.tools.human_input import request_approval

        # Check System Config for Autonomous Mode
        require_approval_str = SystemConfigService.get_value("REQUIRE_PLAN_APPROVAL", default="true")
        require_approval = str(require_approval_str).lower() == "true"

        if not require_approval:
            logger.info("Autonomous Mode: Skipping plan approval (REQUIRE_PLAN_APPROVAL=False).")
            # Auto-execution handled below in the else block

        # Format plan as Markdown...
        plan_md = "| Filename | Topic |\n|---|---|\n"
        for p in pages:
            plan_md += f"| `{p['filename']}` | {p['topic']} |\n"

        if require_approval:
            await request_approval.ainvoke({
                "action_description": "Create Wiki Documentation based on Project Structure",
                "risk_level": "low",
                "details": f"**Proposed File Structure:**\n\n{plan_md}",
                "consequences": f"This will create {len(pages)} new files in `docs/wiki/`. Existing files with same names will be overwritten."
            }, config=config)

            # Return state with HITL (wiki_plan stored in context)
            import uuid
            from datetime import datetime
            return {
                "messages": [
                    AIMessage(content=approval_msg),
                ],
                "hitl_state": {
                    "request_id": str(uuid.uuid4()),
                    "request_type": "approval",
                    "resume_node": "documenter",
                    "context": {"wiki_plan": plan_json},
                    "created_at": datetime.utcnow().isoformat()
                }
            }
        else:
            # Auto-Execution Path
            # We want to execute immediately. We can call the execution logic recursively?
            # Or just signal "Approved" and let Supervisor route back?
            # Routing back relies on Supervisor.
            # Let's try to cheat: Manually construct the "Approved" signal so next loop picks it up?

            # Better: Just execute right here!
            # We have the `pages` object.
            # The execution logic (lines 100-143) relies on `pages` variable.
            # We can refactor execution logic into a helper function, or just copy/paste (bad),
            # or jump to a shared label (not possible in Python).

            # Refactoring is best but risky.
            # Alternative: Return a special "Resume" signal? No.

            # Let's perform the execution HERE for auto-approve case.
            # It duplicates the logic from lines 100-147 but ensures immediate execution.

            # Copy-paste verified safe logic for now:
            from app.domain.research.engine import DeepResearchEngine
            llm = LLMFactory.create_llm()
            engine = DeepResearchEngine(llm)
            docs_dir = os.path.join(settings.PROJECTS_ROOT, "docs", "wiki")
            os.makedirs(docs_dir, exist_ok=True)
            generated_pages = []

            for page in pages:
                # ... same logic ...
                # Simplified for compactness
                fname = page['filename']
                topic = page['topic']
                try:
                    prompt_content = f"Write documentation for {fname}: {topic}. Lang: {user_lang}."
                    content = await engine.run(topic=prompt_content, max_iterations=3, config=config)
                    with open(os.path.join(docs_dir, fname), "w", encoding="utf-8") as f:
                        f.write(content)
                    generated_pages.append(f"{fname}")
                except Exception as e:
                    generated_pages.append(f"{fname} (Err: {e})")

            msg_content = "Wiki Auto-Generated (Autonomous Mode).\nPages:\n" + "\n".join(generated_pages)
            return {
                "messages": [AIMessage(content=msg_content)],
                "hitl_state": None  # Clear any residual state
            }

    except Exception as e:
        logger.error(f"Failed to parse documentation plan: {e}")
        return {
            "messages": [AIMessage(content=f"Error planning documentation: {e}")]
        }
