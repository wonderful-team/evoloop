import asyncio
import os
import sys
from jinja2 import Environment, FileSystemLoader

async def verify_all_templates():
    print("🚀 Verifying System-Wide Prompt Template Migration...")
    
    template_dir = "evoloop/backend/app/core/engine/prompts/templates"
    if not os.path.exists(template_dir):
        template_dir = "app/core/engine/prompts/templates"
    
    env = Environment(loader=FileSystemLoader(template_dir))
    
    common_vars = {
        "user_lang": "en",
        "environment": {
            "summaries": ["Connected to Lab"],
            "memory_replay": ["Past Task: Cleanup"],
            "user_preferences": {"style": "professional"},
            "boundaries": ["No dangerous code"],
            "spatial_awareness": ["App A is open"],
            "mcp_inventory": "MCP Servers: git, shell",
        },
        "blackboard": {
            "ticket": {
                "ticket_type": "task",
                "focus_paths": ["doc.md"],
                "acceptance_criteria": ["Doc is updated"],
            },
            "verification": {"status": "pending"},
            "route_reason": "Documentation update",
        },
        "memory": {
            "episodic_raw": "Memory A: Learned X",
            "core_raw": "Focus: Consistency",
        },
        "project_id": 123,
    }

    # 1. Verify Operator
    print("\n--- Testing Operator ---")
    op_vars = {**common_vars, "tree_section": "File Tree...", "skills": [{"name": "Skill A", "description": "Desc A"}]}
    op_prompt = env.get_template("operator.prompt.j2").render(**op_vars)
    assert "Connected to Lab" in op_prompt
    assert "Memory A: Learned X" in op_prompt
    assert "Skill A" in op_prompt
    print("✅ Operator OK")

    # 2. Verify Deep Research
    print("\n--- Testing Deep Research (Conclusion Mode) ---")
    dr_vars = {**common_vars, "mode": "conclusion", "iteration": 3}
    dr_prompt = env.get_template("deep_research.prompt.j2").render(**dr_vars)
    assert "Final Conclusion" in dr_prompt
    assert "Connected to Lab" in dr_prompt
    print("✅ Deep Research OK")

    # 3. Verify Documenter
    print("\n--- Testing Documenter ---")
    doc_vars = {**common_vars, "skills": [{"name": "DocSkill", "instructions": "Write well"}]}
    doc_prompt = env.get_template("documenter.prompt.j2").render(**doc_vars)
    assert "DocSkill" in doc_prompt
    assert "Connected to Lab" in doc_prompt
    print("✅ Documenter OK")

    # 4. Verify Dynamic Specialist
    print("\n--- Testing Dynamic Specialist ---")
    ds_vars = {**common_vars, "role_name": "SQL Specialist", "instructions": "Query DB", "knowledge_blocks": ["- Use SELECT"]}
    ds_prompt = env.get_template("worker.prompt.j2").render(**ds_vars)
    assert "SQL Specialist" in ds_prompt
    assert "Use SELECT" in ds_prompt
    print("✅ Dynamic Specialist OK")

    # 5. Verify Wiki (Content Mode)
    print("\n--- Testing Wiki (Content) ---")
    wiki_vars = {**common_vars, "mode": "content", "page_title": "Overview", "relevant_files_content": "CODE...", "files_list_md": "- f1.py", "target_lang": "English"}
    wiki_prompt = env.get_template("wiki.prompt.j2").render(**wiki_vars)
    assert "# Overview" in wiki_prompt
    assert "CODE..." in wiki_prompt
    print("✅ Wiki OK")

    # 6. Verify Vision
    print("\n--- Testing Vision ---")
    vision_vars = {"mode": "locate", "element": "Submit Button", "user_lang": "en"}
    vision_prompt = env.get_template("vision.prompt.j2").render(**vision_vars)
    assert "Locate the following element" in vision_prompt
    assert "Submit Button" in vision_prompt
    print("✅ Vision OK")

    # 7. Verify Reviewer
    print("\n--- Testing Reviewer ---")
    rev_vars = {**common_vars, "audit_context": "User checked docs"}
    rev_prompt = env.get_template("finish.prompt.j2").render(**rev_vars)
    assert "Session Reviewer" in rev_prompt
    assert "ACTIVE TICKET: TASK" in rev_prompt
    assert "User checked docs" in rev_prompt
    print("✅ Reviewer OK")

    # 8. Verify Chat
    print("\n--- Testing Chat ---")
    chat_vars = {**common_vars}
    chat_prompt = env.get_template("chat.prompt.j2").render(**chat_vars)
    assert "currently in 'Chat Mode'" in chat_prompt
    assert "Connected to Lab" in chat_prompt
    print("✅ Chat OK")

    # 9. Verify Mission Ticket
    print("\n--- Testing Mission Ticket ---")
    mission_vars = {
        "topic": "Verify Fix",
        "acceptance_criteria": ["Test passes"],
        "parameters": {"depth": 3}
    }
    mission_msg = env.get_template("fragments/mission_ticket.j2").render(**mission_vars)
    assert "**Goal**: Verify Fix" in mission_msg
    assert "Test passes" in mission_msg
    assert "depth: 3" in mission_msg
    print("✅ Mission Ticket OK")

    # 10. Verify Awakening (Legacy Bridge)
    print("\n--- Testing Awakening (AppEnvironmentPrompt) ---")
    awake_vars = {**common_vars, "tips": True}
    awake_prompt = env.get_template("awakening.prompt.j2").render(**awake_vars)
    assert "ENVIRONMENT AWARENESS" in awake_prompt
    assert "PRO TIP" in awake_prompt
    print("✅ Awakening OK")

    # 11. Verify Knowledge Block
    print("\n--- Testing Knowledge Block ---")
    kb_vars = {
        "skill": {"name": "TestSkill", "description": "TestDesc", "instructions": "Step 1..."},
        "is_primary": True
    }
    kb_msg = env.get_template("fragments/knowledge_block.j2").render(**kb_vars)
    assert "[ACTIVE MISSION SOP]: TestSkill" in kb_msg
    assert "strict state-machine" in kb_msg
    assert "Step 1..." in kb_msg
    
    # Test secondary block
    kb_vars["is_primary"] = False
    kb_msg_sec = env.get_template("fragments/knowledge_block.j2").render(**kb_vars)
    assert "Related Reference SOP: TestSkill" in kb_msg_sec
    assert "strict state-machine" not in kb_msg_sec
    print("✅ Knowledge Block OK")

    print("\n🎉 All 11 templates and fragments verified successfully!")

if __name__ == "__main__":
    asyncio.run(verify_all_templates())
