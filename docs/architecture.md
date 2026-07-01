# Architecture & State Machine

Pocket-Pi is engineered around a deterministic state-machine using **PocketFlow**. By orchestrating the LLM prompt-tool loop through discrete nodes rather than a single monolithic python function, we gain extreme traceability, easy debugging, and safe recovery paths.

## PocketFlow Node Specifications

Every block in the state-machine is subclassed from `pocketflow.Node`. They communicate via a unified, shared dictionary (`shared`).

### 1. `ConsoleInputNode`
- **Purpose**: Reads input safely via `prompt_toolkit`.
- **Logic**: Integrates slash command completions and handles prompt coloring and basic terminal shortcuts.
- **Actions**: Directs matching commands to their respective subflows, or forwards pure developer inquiries onto `PlannerNode`.

### 2. `PlannerNode`
- **Purpose**: Prepares prompts and dispatches queries to LLM Providers.
- **Logic**:
  1. Calls `session.build_session_context()` to assemble the tree-based conversation history (including compaction summaries).
  2. Decorates parameters based on selected thinking levels.
  3. Sends request to LLM (Anthropic / OpenAI / OpenRouter).
  4. Parses results for content updates or tool requests.
- **Actions**:
  - Drops back to `ConsoleInputNode` if the response is complete (no tool calls).
  - Routes to `ExecuteToolsNode` if the LLM requests actions.

### 3. `ExecuteToolsNode`
- **Purpose**: Executes tool suites requested by the model.
- **Logic**:
  1. Inspects tool request schema (e.g. `read`, `write`, `edit`, `search`, `bash`).
  2. Dispatches to individual tool files within the `pocket_pi/tools` suite.
  3. Formats execution returns into structured `toolResult` message payloads.
  4. Appends items to session history.
- **Actions**: Unconditionally returns back to `PlannerNode` to give the LLM the tools' context outputs.

---

## The Compaction and Context Pruning Strategy
When `PlannerNode` runs, it detects token counts. If values exceed predefined buffer boundaries (or manual `/compact` is requested):
- The agent isolates early conversational logs.
- Synthesizes a semantic summary using a fast, cost-effective model call.
- Writes a `compaction` block to the JSONL.
- The `SessionManager` automatically skips elements before the compaction boundary on successive runs.
