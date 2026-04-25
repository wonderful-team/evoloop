---
name: Project Discovery
description: Standard Operating Procedure for analyzing a software project structure and generating a comprehensive PROJECT.md documentation file.
namespace: roles
trigger_patterns:
  - "Create PROJECT.md"
  - "Document this project"
  - "Project discovery"
  - "Analyze project structure"
parameters:
  working_directory:
    type: string
    description: The root directory of the project to analyze.
---

# Project Discovery

Analyze a software project's structure, technology stack, and architecture, then generate a comprehensive `PROJECT.md` file at the project root.

## 🎯 Mission Objective

Create `PROJECT.md` at the project root that documents this project for AI assistants. The document must be accurate, concise, and actionable.

## 🛠 Execution Flow

1. **Initial Survey**:
   - Call `list_directory(path=".", tree=False)` once to see top-level files and directories.
   - Do NOT use `tree=True` — flat listing is sufficient and preserves context.

2. **Read Key Configs**:
   - Use `read_file` to read the most important configuration files:
     - `composer.json` / `package.json` / `pom.xml` / `build.gradle` / `Cargo.toml` / `go.mod` / `requirements.txt` / `pyproject.toml`
     - `README.md` or `readme.md`
     - Any framework-specific config (e.g., `.env.example`, `phpunit.xml`, `vite.config.*`)
   - Read at most 5 files. Choose the ones most indicative of the project's identity.

3. **Analyze & Synthesize**:
   - Extract: project name, purpose, tech stack, framework, key dependencies, directory structure conventions.
   - Do NOT mechanically copy file contents. Summarize and interpret.

4. **Write PROJECT.md**:
   - Call `write_file(path="PROJECT.md", content="...")` as your **FINAL action**.
   - The content should follow the format below.

## 📝 PROJECT.md Format

```markdown
# {Project Name}

## Overview
Brief description of what this project does and its primary purpose.

## Tech Stack
- **Language**: e.g., PHP 8.2
- **Framework**: e.g., ThinkPHP 6 / Laravel / React / Vue
- **Key Dependencies**: List major packages/libraries from composer.json/package.json
- **Database**: e.g., MySQL 8.0
- **Server**: e.g., Nginx + PHP-FPM

## Directory Structure
Top-level layout and what each major directory contains.

## Key Files
- `composer.json` — Dependency management
- `README.md` — Human-readable project intro
- ...

## Development Notes
Any important conventions, build steps, or gotchas.
```

## ⚠️ Critical Rules

- **ONE listing only**: Call `list_directory` exactly once. Never re-list the same directory.
- **NO redundant reads**: Do not read files whose content you already have in context.
- **FINAL action must be `write_file`**: After reading files, proceed DIRECTLY to writing `PROJECT.md`. Do NOT output a text summary instead of calling `write_file`.
- **Be concise**: The final document should be 800–1500 characters. Focus on what an AI assistant needs to know.
