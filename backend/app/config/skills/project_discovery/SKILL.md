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

0. **Project Identification & Infrastructure Setup**:
   - Call `list_dir(path=".", tree=False)` once to see top-level files.
   - Determine project type and technology stack.
   - **Infrastructure Discovery & Provisioning**:
     - **REQUIRED ACTION (Docker)**: If `docker-compose.yml` or `docker-stack.yml` exists, you **MUST EXECUTE** `execute_command("docker-compose up -d")` immediately before proceeding to other survey steps.
     - **Middleware Verification**: Check if required services (e.g., Redis on 6379, MySQL on 3306) are running. If not, and no Docker exists, attempt `brew install` or `apt-get install`.
     - **Verification**: Call `execute_command("lsof -i :<port>")` to confirm the service is actually listening.
     - **Action**: Perform language-level initialization (e.g., `npm install`).

1. **Conditional Deployment & Startup**:
   - **Software Projects**: Identify **ALL** core components (e.g., Frontend, Backend, Database, API).
     - For **EACH** component, identify its entry point (e.g., `npm run dev`, `php -S`, `python main.py`).
     - Attempt to deploy and start **ALL** identified services.
     - **Nginx/Proxy Check**: If the project requires specific routing (PHP/Nginx), verify if the proxy/pathinfo configuration is active.
     - Verify startup success for each service by checking logs or port availability.
     - **Deep Verification**: Use `browser_control` to verify UI rendering and detect 403/404/500 errors.
     - Note the access URLs, process IDs, and status for **all** started services.
   - **Non-Software Projects**: If it's a documentation, asset, or data project, SKIP this step.

2. **Initial Survey & Analysis**:
   - Analyze the directory structure and read at most 5 key configuration/README files.
   - **Secrets Check**: Follow security guidelines regarding credentials in `.env` or config files.

3. **Analyze & Synthesize**:
   - Extract: name, purpose, tech stack, environment state, and **Running Status**.

4. **Write PROJECT.md**:
   - Call `write_file(path="PROJECT.md", content="...")` as your **FINAL action**.

5. **Framework Profile**:
   - Based on what you've already read (Step 2), write `framework_profile` into `.evoloop/project.json`.
   - First `read_file(".evoloop/project.json")`, then merge `framework_profile` — NEVER overwrite existing fields.
   - Schema:
     ```json
     {
       "framework_profile": {
         "language": "java",
         "framework": "spring-cloud",
         "build_tool": "maven",
         "architecture": "microservices",
         "role_classifiers": {
           "controller": {"annotations": ["@RestController"], "name_patterns": ["*Controller"]},
           "service": {"annotations": ["@Service"], "name_patterns": ["*Service"]},
           "repository": {"annotations": ["@Mapper"], "name_patterns": ["*Mapper"]}
         },
         "module_paths": {"auth": "ruoyi-auth", "gateway": "ruoyi-gateway"},
         "domain_vocabulary": ["权限", "租户"],
         "profile_version": "1.0"
       }
     }
     ```
   - Populate `role_classifiers` from annotation/name patterns you observed during survey.
   - Populate `module_paths` from the actual module directory layout.
   - Populate `domain_vocabulary` from business terms found in code comments, class names, and config files.

## 📝 PROJECT.md Format

```markdown
# {Project Name}

## Overview
Brief description of what this project does and its primary purpose.

## Tech Stack & Environment
- **Type**: e.g., Next.js Web App / PHP Backend
- **Language/Framework**: e.g., PHP 7.4, TypeScript
- **Environment State**: e.g., "Initialized (node_modules/vendor present)"

## Infrastructure & Middleware
- **Services Detected**: e.g., MySQL, Redis, Nginx
- **Status**: e.g., "Running (Docker)", "Missing (Needs setup)"
- **Action Taken**: e.g., "Executed docker-compose up", "None"

## Directory Structure
Top-level layout and what each major directory contains.

## Security & Secrets (Optional)
*Only include if explicitly requested in mission guidelines.*
- Keys/Tokens found or placeholder locations.

## Development Notes
Build steps, conventions, or initialization commands.
```

## ⚠️ Critical Rules

- **ONE listing only**: Call `list_dir` exactly once.
- **Secrets Handling**: Strictly follow the "Security Guideline" in the mission message. If forbidden, omit all credentials.
- **Non-Code Projects**: If no source code exists, document the project as a documentation/resource repository.
- **FINAL action must be `write_file`**: Always end by creating `PROJECT.md`.
- **Be concise**: Keep the final document under 1500 characters.
