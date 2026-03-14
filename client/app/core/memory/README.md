# Evoloop Memory Module

The `app.core.memory` package provides a standardized, modular interface for managing the system's memory. It encapsulates complex interactions with backend databases (Neo4j, SQL, Vector DBs) into a unified Facade.

## Architecture

The module follows an interface-driven design to ensure backend agnosticism and high testability.

- **`interfaces/`**: Abstract base classes defining the contract for memory providers.
- **`backends/`**: Concrete implementations of the interfaces (e.g., Neo4j).
- **`strategies/`**: Domain-specific logic such as context pruning or importance ranking.
- **`manager.py`**: The `MemoryManager` facade containing all core sub-modules.

## Standard API Reference

AI Agents and developers should interact with the memory system through the global `memory_manager` instance.

### Core Manager (`MemoryManager`)

- **`initialize()`**: Initializes all backends (schemas, indexes).
- **`flush()`**: Resets all memory stores (use with caution, primarily for testing).

---

### 1. Long-Term Memory (`memory_manager.long_term`)

Handles persistent knowledge nodes and experience retrieval.

| Method | Description |
| :--- | :--- |
| `store_concept(concept: Concept)` | Stores or updates a semantic knowledge unit. |
| `search_concepts(query, project_id, min_score=0.7)` | Returns a list of `SearchResult` objects. |
| `record_episode(episode: Episode)` | Records a task execution. Returns `episode_id`. |
| `retrieve_experience(goal, project_id, top_k=3)` | Returns a formatted string of similar past tasks. |
| `link_episode_to_concepts(ep_id, names, pid)` | Associates an episode with specific knowledge nodes. |
| `list_concepts(project_id, limit=50)` | Lists concepts with their associated episode counts. |
| `get_project_concepts(project_id)` | Returns all concepts as formatted text for prompt injection. |

---

### 2. Preference Store (`memory_manager.preferences`)

Manages settings and rules with hierarchical overrides.

| Method | Description |
| :--- | :--- |
| `set_preference(user_id, key, value, desc="", project_id=None)` | Sets a global or project-specific preference. |
| `get_merged_preferences(user_id, project_id)` | Returns a formatted string of active preferences (Project > Global). |

---

### 3. Graph Navigator (`memory_manager.graph`)

Provides deep structural insights for Knowledge Graph navigation.

| Method | Description |
| :--- | :--- |
| `get_directory_info(project_id, path)` | Returns architecture summary, dependencies, and sub-modules. |
| `get_node_details(node_type, filters)` | Raw query for specific graph entities. |
| `traverse(start_id, rel_type, max_depth=2)` | Explores graph relationships. |

---

## Data Models

### Concept
Used for `store_concept`.
- `name`: string identifier.
- `description`: text content.
- `project_id`: integer scoping.
- `related_files`: list of file paths.

### Episode
Used for `record_episode`.
- `goal`: task objective.
- `result`: task outcome.
- `plan_summary`: steps taken.
- `error_msg`: error trace if failed.
- `project_id`: integer scoping.

### SearchResult
Returned by `search_concepts`.
- `name`, `description`, `score`, `files`.

## Data Models

- **`Concept`**: Represents a specific knowledge node. Includes `name`, `description`, `project_id`, and `related_files`.
- **`Episode`**: Represents a historical task execution. Includes `goal`, `result`, `plan` and `error` status.

## Extension

To add a new backend (e.g., Redis for preferences):
1. Implement the corresponding interface in `app.core.memory.interfaces`.
2. Create the backend class in `app.core.memory.backends`.
3. Update `MemoryManager` in `manager.py` to use the new backend.
