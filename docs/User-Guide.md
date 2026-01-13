# EvoLoop User Guide

> 🚀 **EvoLoop** — Your Intelligent Development Assistant

Welcome to EvoLoop! This guide will help you quickly understand and master this powerful intelligent development tool.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Core Features](#core-features)
4. [Interface Guide](#interface-guide)
5. [Tips & Tricks](#tips--tricks)
6. [FAQ](#faq)

---

## Introduction

### What is EvoLoop?

EvoLoop is an **intelligent development assistant** that understands your needs and helps you:

- 📝 **Write Code** — Generate high-quality code from natural language descriptions
- 🔍 **Understand Projects** — Automatically analyze codebase structure and architecture
- 🐛 **Solve Problems** — Diagnose bugs and provide fix suggestions
- 📚 **Generate Documentation** — Automatically write project docs and API references
- 🔄 **Automate Tasks** — Handle repetitive development work

### Who is it for?

| Role | Use Cases |
|:---|:---|
| **Developers** | Accelerate coding, code review, learn new technologies |
| **Tech Leads** | Project architecture analysis, technical documentation |
| **Product Managers** | Quickly understand technical solutions, requirement communication |
| **Learners** | Code interpretation, programming learning assistance |

---

## Getting Started

### Step 1: Create or Import a Project

1. Open the EvoLoop desktop application
2. Go to the **"Projects"** page
3. Click **"New Project"** or select an existing project
4. The system will automatically analyze the project structure

> 💡 **Tip**: When importing a project for the first time, the system needs to build a knowledge index, which may take a few minutes.

### Step 2: Start a Conversation

1. Switch to the **"Chat"** page
2. Make sure the correct project is selected (project switcher in the top left)
3. Describe your needs in the input box
4. Click send or press Enter

### Example Conversation

```
You: Help me analyze the overall architecture of this project

AI: Sure, let me analyze this project's architecture...
    
    This is a FastAPI-based backend project with the following main modules:
    - app/core — Core business logic
    - app/api — API endpoint definitions
    - app/models — Data models
    ...
```

---

## Core Features

### 1. Intelligent Chat 💬

Interact with AI using natural language — no need to memorize complex commands.

**Supported Operation Types:**

| Type | Example Commands |
|:---|:---|
| Code Generation | "Write a user login API endpoint for me" |
| Code Explanation | "Explain what the auth.py file does" |
| Bug Diagnosis | "What's causing this error? [paste error message]" |
| Refactoring Suggestions | "How can I optimize this code's performance?" |
| Documentation | "Generate API documentation for this module" |

**Advanced Usage:**
- Upload images (screenshots, diagrams) for AI analysis
- Attach files as reference context
- Use voice input (click the microphone icon)

---

### 2. Project Management 📁

Centrally manage all your development projects.

**Features:**

- **File Browser** — View project directory structure and file contents
- **Semantic Search** — Search code by functionality description (not just keyword matching)
- **Task Tracking** — Manage development tasks and progress
- **Gantt Chart** — Visualize project timeline

**How to Use:**

1. Select the target project from the project list
2. Click to enter the project detail page
3. Use the top tabs to switch between different views

---

### 3. Context Panel 🧠

The context panel on the right side of the chat interface is your "workbench."

**Panel Contents:**

| Section | Purpose |
|:---|:---|
| **Pinned Files** | Pin frequently used files here for AI reference |
| **Runtime Tools** | View the tools currently available to AI |
| **External Links** | Add reference documentation or API URLs |

**How to Pin Files:**
1. Find the target file in the file browser
2. Right-click → Select "Pin to Resources"
3. The file will appear in the context panel

---

### 4. MCP Extensions 🔌

Connect external tools through the MCP (Model Context Protocol) protocol.

**Supported Extensions:**

| Extension | Functionality |
|:---|:---|
| **Git** | Execute Git operations, view commit history |
| **Database** | Query and analyze database contents |
| **Search Engine** | Search technical documentation online |
| **File System** | Access local files (beyond project scope) |

**How to Add Extensions:**
1. Go to the **"MCP Servers"** page
2. Click **"Add Server"**
3. Fill in the server name and startup command
4. Save and the system will automatically connect

---

### 5. Personalization Settings ⚙️

Customize EvoLoop to your preferences.

**Configurable Options:**

| Setting | Description |
|:---|:---|
| **Language** | Switch interface language (Chinese/English) |
| **Device Name** | Identify this device in multi-device environments |
| **Projects Root** | Set the default project scanning path |
| **AI Model** | Select the language model and API to use |
| **Approval Mode** | Control whether AI needs your confirmation before executing actions |
| **Theme** | Light/Dark/System |

---

## Interface Guide

### Overall Layout

```
┌─────────────────────────────────────────────────────────┐
│  ┌──────┐                                               │
│  │ Logo │  Sidebar                      Main Content    │
│  ├──────┤                                               │
│  │Dashboard│                                            │
│  │ Chat   │  ┌─────────────────────────────────────────┐│
│  │Projects│  │                                         ││
│  │ MCP    │  │      Content varies by selection        ││
│  │Settings│  │                                         ││
│  │        │  │                                         ││
│  └──────┘  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Chat Interface Breakdown

```
┌───────────────────────────────────────────────────────────┐
│  Chat Sidebar  │      Message Area      │ Context Panel   │
│ ┌─────────────┐│ ┌─────────────────────┐│ ┌─────────────┐ │
│ │Project Switch││ │ You: Help me...     ││ │ Pinned Files│ │
│ ├─────────────┤│ │                     ││ │ - file1.py  │ │
│ │Chat List    ││ │ AI: Sure...         ││ │ - file2.ts  │ │
│ │ · Chat 1    ││ │ [Execution Steps]   ││ ├─────────────┤ │
│ │ · Chat 2    ││ │                     ││ │ Available   │ │
│ │ · Chat 3    ││ │                     ││ │ Tools       │ │
│ └─────────────┘│ ├─────────────────────┤│ │ - File Mgmt │ │
│               ││ │ [Input]       [Send]││ │ - Terminal  │ │
└───────────────────────────────────────────────────────────┘
```

### Key Interactive Elements

| Element | Location | Purpose |
|:---|:---|:---|
| **Project Switcher** | Top of chat sidebar | Switch current working project |
| **New Chat Button** | Above chat list | Start a new conversation |
| **Attachment Button** | Right of input 📎 | Upload images or files |
| **Voice Button** | Left of input 🎤 | Voice input |
| **Skill Library** | Left of input 📖 | View and use skill templates |
| **Stop Button** | Shown when AI is running | Interrupt current operation |

---

## Tips & Tricks

### 💡 Tips for Better Responses

1. **Provide Sufficient Context**
   - ❌ "This function has a problem"
   - ✅ "The validate_token function in auth.py returns None, but I expect it to return a user object"

2. **Be Clear About Expected Results**
   - ❌ "Help me change the code"
   - ✅ "Convert this function to an async version and add error handling"

3. **Use File Pinning**
   - Pin relevant files to the context panel
   - AI will automatically reference these files

4. **Ask Step by Step**
   - Break complex tasks into smaller steps
   - Confirm each step before continuing

### ⌨️ Keyboard Shortcuts

| Action | Shortcut |
|:---|:---|
| Send message | `Enter` |
| New line (without sending) | `Shift + Enter` |
| New chat | Click the + button in sidebar |
| Stop generation | Click the red stop button |

### 🔄 Approval Mode Explained

EvoLoop supports two working modes:

| Mode | Description | Best For |
|:---|:---|:---|
| **Approval Mode (Default)** | AI requests confirmation before important operations | Production, sensitive operations |
| **Autonomous Mode** | AI auto-executes low-risk operations, only requests confirmation for high-risk | Development, rapid iteration |

Switch in **Settings → General → Agent Behavior**.

---

## FAQ

### Q1: Why are AI responses sometimes slow?

**Possible Reasons:**
- Project is building its index (during first import)
- Request involves analyzing many files
- Unstable network connection

**Solutions:**
- Wait for indexing to complete (check status on project detail page)
- Try breaking the question into smaller parts
- Check your network connection

---

### Q2: How does AI know my project structure?

EvoLoop builds a **knowledge index** of your project in the background, including:

1. **File Structure** — Directory tree and file relationships
2. **Code Semantics** — Meaning of functions, classes, and variables
3. **Dependencies** — Call relationships between modules

This process is automatic — just wait for indexing to complete.

---

### Q3: Can I let AI perform dangerous operations?

EvoLoop has built-in safety mechanisms:

- **Requires Approval by Default** — File modifications, command execution, etc., trigger approval cards
- **Risk Level Indicators** — High-risk operations have clear warnings
- **Rollback Support** — Recommended to use with Git for reverting unexpected changes

---

### Q4: How do I restart the onboarding tour?

1. Go to **Settings → General**
2. Scroll to the bottom of the page
3. Click the **"Replay Tour"** button

---

### Q5: Which programming languages are supported?

EvoLoop supports mainstream programming languages, including but not limited to:

- **Backend**: Python, Java, Go, Rust, Node.js
- **Frontend**: TypeScript, JavaScript, React, Vue
- **Mobile**: Swift, Kotlin, Flutter
- **Others**: SQL, Shell, Markdown

---

### Q6: Is my data secure?

- Your code is **not uploaded to public clouds** (unless you use a cloud LLM)
- Local index data is stored on your device
- If using a private LLM (like local Ollama), data stays completely offline

---

## Contact & Feedback

If you encounter issues or have suggestions during use, please contact us through:

- 🌐 Website: [develop-assistant.cn](https://develop-assistant.cn)
- 📧 Email: support@develop-assistant.cn

---

> 📖 This guide was last updated in January 2026
