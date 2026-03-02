# Critical Evaluation of Evoloop Agent Architecture

## 1. Executive Summary
The current architecture (v2.1) suffers from **"Role-Playing Over-Engineering"**. By mimicking a human corporate structure (Manager-Coder-Tester-Planner), the system introduces significant **latency, token waste, and context fragmentation**.

A **Functional Architecture** (grouping by *capability* rather than *job title*) would reduce graph steps by ~40% and improve success rates by maintaining tighter feedback loops.

## 2. Efficiency Bottlenecks identified

### 2.1 The "Blind Handoff" Overhead
Every time the graph transitions from Node A to Node B (e.g., Coder -> Tester):
1.  **Serialization**: State is saved to DB.
2.  **Routing**: Router logic runs.
3.  **Deserialization**: Next node loads state.
4.  **Context Reload**: The new node must re-read the project tree and re-process the "Handoff Context".
5.  **LLM Warm-up**: The LLM must "get into character" again.

**Impact**: A simple "fix a typo" loop (Supervisor -> Coder -> Tester -> Supervisor) takes **3 full LLM calls + 3 DB writes**, whereas a unified Developer node could do it in **1 loop**.

### 2.2 The "Fake Fast Path"
`intent_classifier.py` was intended as a "Fast Path", but it effectively makes an LLM call (`LLMFactory.create_llm(temperature=0.0)`).
-   **Reality**: It is not "fast". It incurs an LLM round-trip just to decide "Go to Coder".
-   **Optimization**: This should be a Regex/Keyword router first, or merged into the Supervisor's prompt to avoid an extra hop.

### 2.3 Redundant Nodes
*   **Planner Node**: For 80% of tasks, the "Plan" is just "Edit file X". Invoking a dedicated Planner to output a JSON plan for a 1-file change is overkill.
*   **Meta-Reviewer**: This node is a weak band-aid. If Coder/Tester are failing 3 times, an external "Reviewer" rarely helps. The Coder needs *better tools* (e.g., search), not a "Manager" yelling at it.

## 3. Detailed Component Critique

| Component | Status | Critique | Recommendation |
| :--- | :--- | :--- | :--- |
| **Supervisor** | ⚠️ Keep | Good for routing, but heavily overloaded with context injection. | Keep as Entry/Router, but strip "Cognitive Injection" logic to a middleware. |
| **Coder** | ❌ Refactor | Lacks "Verify" capability. Blindly writes code and prays Tester catches it. | **Merge with Tester** into `DeveloperNode`. |
| **Tester** | ❌ Refactor | Passive. Just runs command and reports XML. Logic is too thin for a Node. | Convert to a **Tool** (`verify_changes`) used by Developer. |
| **Planner** | ⚠️ Merge | Useful for "New Feature", useless for "Bug Fix". | Become a **Tool** (`create_detailed_plan`) available to Supervisor/Developer. |
| **Documenter** | ✅ Keep | Good candidate for isolation. Documentation is a distinct context. | Keep as specialized node. |
| **DeepResearcher** | ✅ Keep | Long-running process. Needs isolation. | Keep. |
| **IntentClassifier** | ❌ Remove | Calling 2 LLMs (Classifier + Router) is wasteful. | Remove. Let Supervisor decide or use regex. |

## 4. Proposed "Functional Architecture" (v3.0)

Instead of "Roles", we use "Capabilities".

### 4.1 The Core Triangle
1.  **Supervisor (Orchestrator)**:
    -   Inputs: User User check, High-level intent.
    -   Outputs: Route to `Developer` or `Researcher`.
    -   **Optimization**: Direct regex routing for "Fix file X".

2.  **Developer Agent (The Workhorse)**:
    -   **Merged**: Coder + Tester + Planner (Lite).
    -   **Loop**: `Think -> Plan (Optional) -> Edit Code -> Run Test (Tool) -> Analyse Result -> Self-Correct -> Submit`.
    -   **Benefit**: "Inner Loop" happens in **one** node session. No graph hopping until task is DONE or BLOCKED.

3.  **Researcher Agent (The Brain)**:
    -   Handles `DeepResearcher` (Web) and `CodebaseAnalysis` (Local).
    -   Used when Developer is stuck.

### 4.2 Migration Strategy
1.  **Consolidate**: Create `DeveloperNode` that binds `edit_file`, `run_command`, and `grep_files`.
2.  **Internalize Testing**: Give `DeveloperNode` a `verify_task` instruction in its prompt.
3.  **Flatten Graph**:
    -   *Old*: `Supervisor -> Planner -> Coder -> Tester -> Supervisor`
    -   *New*: `Supervisor -> Developer (Loop until pass) -> Supervisor`

## 5. Conclusion
The user's intuition is correct. The current system is optimized for "Demo Clarity" (showing pretty graph nodes) rather than "Production Efficiency". Moving to a functional `Supervisor -> Developer` topology will significantly reduce latency and cost.
