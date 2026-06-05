---
name: Wiki Generation
description: Generate a comprehensive, structured Wiki documentation for a software project by analyzing its codebase and writing multi-page Markdown documentation.
namespace: roles
trigger_patterns:
  - "Generate wiki"
  - "Create project wiki"
  - "Build documentation"
  - "Generate project documentation"
parameters:
  project_id:
    type: integer
    description: The target project ID.
  working_directory:
    type: string
    description: The root directory of the project to document.
---

# Wiki Generation

Analyze a software project's codebase and generate a structured, multi-page Wiki documentation stored in the project's knowledge base.

## 🎯 Mission Objective

Create a comprehensive Wiki for the project that documents its architecture, APIs, setup guides, and key concepts for human developers. The Wiki must be accurate, well-structured, and browsable via a tree navigation UI.

### Language & Address Consistency (MANDATORY)
The user's preferred language is provided in the mission context. **ALL** wiki content — including page titles, headings, and body text — MUST be written in that language. 
**CRITICAL**: Use the exact same page title as the address when calling `write_wiki_page`. Do not invent separate English slugs if the title is Chinese.

## 📐 Cognitive Guidelines: Scale Awareness & Task Decomposition (Meta-Cognition)

**You must develop a sensitivity to the project's scale. Do not blindly generate a "catch-all" overview without a comprehensive understanding of the project's structure.**

1. **Intuitive Survey**:
   - The first step of any mission MUST be scanning the project's core skeleton using `list_dir` (suggested depth: 2-3 levels).
   - Observe the number of core modules (e.g., `addon/`, `plugins/`, `packages/`, `src/modules/`, etc.).

2. **Entity-Based Decomposition**:
   - Never use a single page to summarize dozens of plugins or modules.
   - If you discover N core entities (e.g., 30 plugins or 15 microservices) in Phase 1, your plan **MUST** include generating an individual, in-depth documentation page for **each** of these N entities.
   - The depth of the Wiki should be proportional to the physical complexity of the project.

## 🛠 Execution Flow

### Phase 1: Cognitive Discovery & Planning (MANDATORY)
1. **Discover**: Call `list_dir` to map the codebase. Count the major directories, plugins, or components.
2. **Estimate**: In your thinking, state exactly how many entities you found and acknowledge the scale.
3. **Plan Generation**: Call `create_plan(title="Wiki Generation Plan", steps=[...])`.
   - The steps MUST follow a **hierarchical order**: Define Parent pages before their respective Children.
   - Example: Plan "Overview" -> "Architecture" -> "Database Design".
4. **The plan is your contract**. You will be held accountable for completing every step in order.

### Phase 2: Content Generation & Active Memory Management

**For Massive Projects (Long-Horizon Survival):**
You are expected to execute a massive amount of pages. To avoid context window collapse, you MUST use the **Active Forgetting** technique:
1. Focus on one step/module from your plan.
2. `read_file` to analyze that module.
3. `write_wiki_page` to document it.
4. `update_step_status` to mark it completed.
5. **CRITICAL**: Call `forget_tool_outputs([tool_ids_for_read_file], "Finished module A")` to wipe the raw code from your memory.
6. Move to the next module in the plan immediately. DO NOT STOP.

**Content Quality Guidelines:**
- **Accuracy**: Do not invent features or APIs that don't exist. If you're unsure, say so.
- **Completeness**: Cover the "what", "why", and "how" for each topic.
- **Conciseness**: Avoid filler text. Developers want actionable information.
- **Page Length**: Each page should be **3000-4000 characters**. Be concise — do not write exhaustive treatises.
- **Mermaid**: Use diagrams for architecture, data flow, and relationships. Keep diagrams ≤10 nodes.
- **Hierarchy**: Use `parent_title` to establish hierarchy (e.g., "API Overview" as parent of "API Authentication").
- **Incremental Editing**: For small fixes to existing pages prefer `edit_wiki_page(title, old_string, new_string)`.

### Phase 3: Progress Tracking & Continuation
- Compare your progress against the `create_plan` steps.
- If ANY step is still pending, you MUST continue generating. Do NOT report completion.
- You are not bound by a "turn limit". Keep generating and forgetting memory until the exhaustive plan is complete.

### Phase 4: Concept Extraction (Optional but recommended)
- Call `save_concepts(concepts=[{"name": "...", "description": "..."}, ...])` to store architectural patterns in long-term memory.

### Phase 5: Self-Audit & Hierarchy Linking
- After writing all content pages, check if all `parent_id` relationships are correctly established.
- If you missed a parent link, use `edit_wiki_page` or re-write the child page with the correct `parent_title`.

### Phase 6: Final Verification
- Do a self-audit: Did I cover all the entities I discovered in Phase 1?
- Only report completion when ALL planned steps are marked `completed` and the depth of the Wiki matches the complexity of the project.

## ⚠️ Critical Rules

- **ONE tree listing**: Call `list_dir(path=".", tree=True)` exactly once at the beginning.
- **Selective file reading**: Do not read more than 10 source files total per module. Choose the most representative ones.
- **Memory Hygiene**: You MUST use `forget_tool_outputs` after processing each major module to survive long generation tasks.
- **Language**: ALL content must be in the user's preferred language. No exceptions.
- **No early stopping**: Do NOT report success until all plan steps are completed and the true depth of the project is documented.