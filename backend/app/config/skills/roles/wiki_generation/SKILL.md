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

### Language Constraint (MANDATORY)
The user's preferred language is provided in the mission context. **ALL** wiki content — including page titles, headings, body text, tables, and the table of contents — MUST be written in that language. This is a hard constraint, not a suggestion.

## 🛠 Execution Flow

1. **Project Survey**:
   - Call `list_directory(path=".", tree=True)` to understand the project structure.
   - Read `README.md` and up to 5 key configuration files (package.json, pyproject.toml, docker-compose.yml, etc.) for context.
   - Identify the project type, tech stack, and architecture patterns.

2. **Structure Planning**:
   - Decide on a logical Wiki structure. A well-structured wiki typically includes:
     - **Overview** — What the project does, its purpose, and key features.
     - **Architecture** — High-level system design, component diagrams (use Mermaid), data flow.
     - **Tech Stack** — Languages, frameworks, databases, middleware, and their versions.
     - **Getting Started / Setup** — Prerequisites, installation steps, environment configuration.
     - **API Reference** — Key endpoints, request/response formats (if applicable).
     - **Development Guide** — Coding conventions, build commands, testing strategy.
     - **Deployment** — How to deploy to staging/production, Docker instructions.
     - **Troubleshooting** — Common issues and solutions.
   - You do NOT need to create all of these — adapt the structure to the project's actual needs. Small projects may only need 3-4 pages; large projects may need 8-10.

3. **Content Generation (Page by Page)**:
   - For each planned page:
     - Read relevant source files if needed (do NOT read every file; be selective).
     - Generate well-formatted Markdown content with:
       - Clear headings and sections
       - Code blocks with language tags for syntax highlighting
       - **Mermaid diagrams** (`graph TD`, `sequenceDiagram`, `classDiagram`) where appropriate
       - Tables for structured data (API endpoints, environment variables, etc.)
       - `<details>` blocks for expanded file references or large code snippets
     - **CRITICAL**: You MUST call `write_wiki_page(title=..., content=..., slug=..., parent_slug=..., order=...)` to persist each page. Do NOT use `write_file` for wiki pages — `write_file` writes to the filesystem but does NOT create browsable Wiki entries in the database. Only `write_wiki_page` makes pages appear in the Wiki UI.
   - Use `parent_slug` to establish hierarchy (e.g., "api" as parent of "api-auth", "api-users").
   - Use `order` to control display order among siblings (0, 1, 2, ...).

4. **Concept Extraction** (Optional but recommended):
   - After writing all pages, review the generated content.
   - Identify 3-5 key architectural concepts, patterns, or domain terms.
   - Call `memory_store_concept(name=..., description=..., category="architecture")` for each to make them searchable by the AI assistant.

5. **Table of Contents Page** (Mandatory — DO NOT SKIP):
   - After writing all content pages, create a dedicated Table of Contents page.
   - Title it according to the user's language (e.g., '目录' for Chinese, 'Table of Contents' for English).
   - Use `write_wiki_page(title='...', content='...', slug='toc', order=0)` to create it.
   - The content should list all wiki pages in a hierarchical tree format (indented by level), with links to each page by title.
   - **If you skip this step, the mission is incomplete.**

6. **Completion**:
   - Call `list_wiki_pages()` to verify all pages were created correctly.
   - Report the final Wiki structure (page titles and their hierarchy) as the mission result.

## 📝 Page Quality Guidelines

- **Accuracy**: Do not invent features or APIs that don't exist. If you're unsure, say so.
- **Completeness**: Cover the "what", "why", and "how" for each topic.
- **Conciseness**: Avoid filler text. Developers want actionable information.
- **Links**: Reference related wiki pages by title when mentioning them.
- **Mermaid**: Use diagrams for architecture, data flow, and relationships — they render beautifully in the Wiki UI.

## ⚠️ Critical Rules

- **ONE tree listing**: Call `list_directory(path=".", tree=True)` exactly once at the beginning.
- **Selective file reading**: Do not read more than 10 source files total. Choose the most representative ones.
- **Secrets safety**: NEVER include credentials, API keys, tokens, or passwords in wiki content. Redact them as `***REDACTED***`.
- **Language**: ALL content must be in the user's preferred language. No exceptions.
- **Incremental writes**: Use `write_wiki_page` after completing each page — don't batch everything into one tool call.
- **Table of Contents**: Always create a TOC page as the last content page before verification. Skipping it means the mission failed.
- **FINAL action**: End by calling `list_wiki_pages()` to confirm the complete Wiki structure.
