# EvoLoop Memory System

The `app.core.memory` package provides a sophisticated, multi-tier memory system for the EvoLoop AI Agent. It implements intelligent memory management inspired by Claude Code's architecture.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      MemoryContainer (DI)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Hot Tier   │  │  Smart Retr. │  │  Auto-Extractor      │  │
│  │  MEMORY.md   │  │  (LLM Rank)  │  │  (Forked Agent)      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
└─────────┼─────────────────┼─────────────────────┼──────────────┘
          │                 │                     │
┌─────────▼─────────────────▼─────────────────────▼──────────────┐
│                    TwoTierMemoryManager                        │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  MemoryManager (Unified API)                             │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │  │
│  │  │ Short-Term  │  │  Long-Term  │  │ Quality Analyzer│  │  │
│  │  │   (SQL)     │  │(File/Neo4j) │  │   (Scoring)     │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. MemoryContainer (Dependency Injection)

The central DI container manages all memory components' lifecycle:

```python
from app.core.memory import MemoryContainer, MemoryConfig

# Initialize container
config = MemoryConfig.from_settings()
container = MemoryContainer(config)
await container.initialize()

# Access components
manager = container.memory_manager
extractor = container.auto_extractor
retriever = container.smart_retriever

# Cleanup
await container.shutdown()
```

### 2. Two-Tier Memory (Claude Code Style)

- **Tier 1 (Hot)**: MEMORY.md - Always loaded, 200 lines / 25KB max
- **Tier 2 (Cold)**: Full storage searched on demand

Budgets per section:
- Architecture: 25 lines
- Decisions: 25 lines  
- Patterns: 25 lines
- Gotchas: 20 lines
- Progress: 30 lines
- Context: 15 lines

### 3. Smart Retrieval

Two-stage retrieval with LLM relevance ranking:
1. **Stage 1**: Keyword search for candidates (max 20)
2. **Stage 2**: LLM selection of most relevant (max 5)

Type multipliers for ranking:
- USER: 1.3x (user preferences)
- FEEDBACK: 1.2x (user corrections)
- PROJECT: 1.0x (team knowledge)
- REFERENCE: 0.9x (read-only refs)

### 4. Auto-Extraction

Forked agent pattern for non-blocking memory extraction:

**Gating criteria:**
- Minimum 4 messages since last extraction
- Extraction interval (every N turns)
- Skip if main agent already wrote memories

**Process:**
1. LLM extracts 0-3 memories from conversation
2. Deduplication against existing memories
3. Quality scoring (freshness, usage, specificity, actionability)
4. Storage with appropriate privacy/type

## Memory Types & Privacy

| Type | Privacy | Decay | Use Case |
|------|---------|-------|----------|
| USER | PRIVATE | None | User preferences, habits |
| FEEDBACK | PRIVATE | 30 days | User corrections, feedback |
| PROJECT | TEAM | None | Team knowledge, decisions |
| REFERENCE | TEAM | 7 days | Docs, temporary references |

## Usage Patterns

### In FastAPI Routes

```python
from fastapi import Request

@app.get("/memories")
async def get_memories(request: Request):
    container = request.app.state.memory_container
    manager = container.memory_manager
    memories = await manager.search_memories("query")
    return memories
```

### In Agent Nodes

```python
from app.core.memory import MemoryContainer, MemoryConfig

async def supervisor_node(state, config):
    # Get container from app state or create locally
    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    
    # Use manager
    manager = container.memory_manager
    relevant = await manager.search_memories(state["query"])
    
    # Cleanup
    await container.shutdown()
```

### With LifespanManager (Recommended)

```python
from app.core.memory.lifespan import MemoryLifespanManager

# At app startup
container = await MemoryLifespanManager.ainitialize()

# Anywhere in code
manager = MemoryLifespanManager.get_manager()

# At shutdown
await MemoryLifespanManager.shutdown()
```

## Daily Logs (KAIROS Mode)

Append-only daily logging with nightly consolidation:

```
~/.evoloop/memory/
├── logs/
│   └── 2026/
│       └── 04/
│           ├── 2026-04-01.md
│           └── 2026-04-02.md
├── private/
└── team/
```

## Configuration

```python
from app.core.memory import MemoryConfig

config = MemoryConfig(
    backend_type="file",  # or "neo4j"
    memory_root="~/.evoloop/memory",
    extraction_interval=4,
    enable_smart_retrieval=True,
    enable_auto_memory=True,
)
```

## Extension

To add a new backend:
1. Implement interface in `app.core.memory.interfaces`
2. Create backend in `app.core.memory.backends`
3. Register in `MemoryFactory`
4. Update `MemoryConfig` if needed

## Migration from Global Singleton

Old pattern (deprecated):
```python
from app.core.memory import memory_manager  # Removed
```

New pattern (DI):
```python
from app.core.memory import MemoryContainer, MemoryConfig

container = MemoryContainer(MemoryConfig.from_settings())
await container.initialize()
manager = container.memory_manager
```
