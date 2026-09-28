---
name: Wiki Generation
description: Generate a comprehensive, structured Wiki documentation for a software
  project by analyzing its codebase and writing multi-page Markdown documentation.
namespace: roles
trigger_patterns:
- Generate wiki
- Create project wiki
- Build documentation
- Generate project documentation
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

## Target Audience

Developers who need to understand the project's architecture, APIs, setup, and key concepts. The content must be accurate and well-structured.

## Language & Address Consistency (MANDATORY)

The user's preferred language is provided in the mission context. **ALL** wiki content — including page titles, headings, and body text — MUST be written in that language. 
**CRITICAL**: Use the exact same page title as the address when calling `write_wiki_page`. Do not invent separate English slugs if the title is Chinese.

## Cognitive Guidelines: Scale Awareness & Task Decomposition (Meta-Cognition)

**You must develop a sensitivity to the project's scale. Do not blindly generate a "catch-all" overview without a comprehensive understanding of the project's structure.**

1. **Indexed Survey First**:
   - The first step MUST consume the existing codebase index instead of walking the filesystem.
   - Use `glob` on top-level module dirs (e.g. `addon/`, `plugins/`, `packages/`, `src/modules/`) to enumerate code units and infer the module structure.
   - Use `grep` for route decorators/registrations (e.g. `@app.route|@router\.|add_api_route|Controller`) to identify all API routes.
   - Use `glob` with per-language source patterns if the full list of parsed files is needed for scale estimation.
   - Observe the number of core modules (e.g., `addon/`, `plugins/`, `packages/`, `src/modules/`, etc.).

2. **Entity-Based Decomposition**:
   - Never use a single page to summarize dozens of plugins or modules.
   - If you discover N core entities (e.g., 30 plugins or 15 microservices) from the index, your plan **MUST** include generating an individual, in-depth documentation page for **each** of these N entities.
   - The depth of the Wiki should be proportional to the physical complexity of the project.

## Execution Flow

### Phase 1: Cognitive Discovery & Planning (MANDATORY)
1. **Read Framework Profile** (if available):
   - Call `file(action="read", path=".evoloop/project.json")` and extract `framework_profile`.
   - Use `module_paths` as authoritative module boundaries for Wiki structure planning.
   - Use `domain_vocabulary` to guide page naming and chapter headings.
   - If absent, proceed with standard `glob`/`grep` discovery.
2. **Discover from Index**: 
   - Call `grep`/`glob` to understand the module structure and key code units.
   - Call `grep` for route decorators/registrations to get the complete API catalog.
   - (Optional) Use `grep` for security-sensitive patterns (secrets, raw SQL, shell exec) to identify risks worth documenting.
3. **Estimate**: In your thinking, state exactly how many entities you found and acknowledge the scale.
4. **Selective Deep Reading**: Only read source files for modules listed in `framework_profile.module_paths`, or those identified as API entry points via `grep`. If `framework_profile` is unavailable, use `grep`/`glob` results to infer module boundaries.
5. **Plan Generation**: Call `plan(action="create", title="Wiki Generation Plan", steps=[...])`.
   - The steps MUST follow a **hierarchical order**: Define Parent pages before their respective Children.
   - Example: Plan "Overview" -> "Architecture" -> "Database Design".
6. **The plan is your contract**. You will be held accountable for completing every step in order.

### Phase 2: Content Generation & Active Memory Management

**For Massive Projects (Long-Horizon Survival):**
You are expected to execute a massive amount of pages. To avoid context window collapse, you MUST use the **Active Forgetting** technique:
1. Focus on one step/module from your plan.
2. `file(action="read")` to analyze that module (only if the directory summary indicates it is necessary).
3. `write_wiki_page` to document it.
4. `plan` with `action='update_steps'` (steps=[{step_id, status: "completed", result: "..."}]) to mark it completed.
5. Context window pressure is handled by the system-level trimmer (oldest tool outputs fold automatically) — no manual cleanup needed; proceed to the next module right away.
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
- Compare your progress against the `plan` steps.
- If ANY step is still pending, you MUST continue generating. Do NOT report completion.
- You are not bound by a "turn limit". Keep generating and forgetting memory until the exhaustive plan is complete.

### Phase 4: Concept Extraction (Optional but recommended)
- Call `save_concepts(concepts=[{"name": "...", "description": "..."}, ...])` to store architectural patterns in long-term memory.

### Phase 5: Self-Audit & Hierarchy Linking
- After writing all content pages, check if all `parent_id` relationships are correctly established.
- If you missed a parent link, use `edit_wiki_page` or re-write the child page with the correct `parent_title`.

### Phase 6: Final Verification
- Do a self-audit: Did I cover all the entities I discovered from the index in Phase 1?
- Only report completion when ALL planned steps are marked `completed` and the depth of the Wiki matches the complexity of the project.

## Critical Rules

- **No blind filesystem scanning**: Do NOT walk the tree with `file(action="list")`. All discovery must come from targeted `glob`/`grep`.
- **ONE selective tree listing only**: If you absolutely need a high-level directory view (e.g., to verify summary coverage), call `file(action="list", path=".", tree=True, depth=1)` **once** and only for confirmation.
- **Selective file reading**: Do not read more than 10 source files total per module. Choose the most representative ones.
- **Memory Hygiene**: Do NOT manually clean tool outputs — the system-level context trimmer automatically folds the oldest tool outputs when the window pressure grows. Just keep moving to the next major module.
- **Language**: ALL content must be in the user's preferred language. No exceptions.
- **No early stopping**: Do NOT report success until all plan steps are completed and the true depth of the project is documented.
