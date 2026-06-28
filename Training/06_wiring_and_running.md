# Module 6: Graph Wiring & App Bootstrapping

This final module details how we declaratively connect our states inside `flow.py`, explaining the correct feedback loop structure, study our entry point boots script in `main.py`, and run the completed package using `uv`.

---

## 🔗 Declaring the Workflow Graph (`flow.py`)

In Module 1, we learned how flows represent directed graphs. In **`flow.py`**, we bring all of our independent nodes together, and wire them declaratively inside the constructor of **`PiAgentFlow`**:

```python
from pocketflow import Flow
from pocket_pi.workflow.nodes import (
    ConsoleInputNode, HelpNode, LoginNode, ModelNode, ResumeNode,
    SessionNode, NewSessionNode, CompactNode, PlannerNode, ExecutorNode, QuitNode
)

class PiAgentFlow(Flow):
    def __init__(self):
        # 1. Instantiate the nodes
        console_input = ConsoleInputNode()
        help_node = HelpNode()
        login_node = LoginNode()
        model_node = ModelNode()
        resume_node = ResumeNode()
        session_node = SessionNode()
        new_session = NewSessionNode()
        compact_node = CompactNode()
        planner_node = PlannerNode()
        executor_node = ExecutorNode()
        quit_node = QuitNode()
        
        # 2. Wire core conversational loop
        console_input - "default" >> planner_node
        console_input - "input_again" >> console_input
        
        # 3. Connect the Action-Observation feedback loop!
        planner_node - "tools" >> executor_node
        planner_node - "loop" >> console_input
        
        # ⚠️ CRUCIAL: ExecutorNode must loop back to PlannerNode!
        executor_node >> planner_node
        
        # 4. Connect administrative / slash command subflows...
        console_input - "help" >> help_node
        help_node >> console_input
        
        console_input - "login" >> login_node
        login_node >> console_input
        
        console_input - "model" >> model_node
        model_node >> console_input
        
        console_input - "resume" >> resume_node
        resume_node >> console_input
        
        console_input - "session" >> session_node
        session_node >> console_input
        
        console_input - "new" >> new_session
        new_session >> console_input
        
        console_input - "compact" >> compact_node
        compact_node >> console_input
        
        # 5. Connect exit boundaries
        console_input - "quit" >> quit_node
        
        # 6. Initialize wrapping the starting node using start=console_input
        super().__init__(start=console_input)
```

---

## 🧠 Why `ExecutorNode` Loops Back to `PlannerNode`

In our initial iterations, `ExecutorNode` was wired directly back to `ConsoleInputNode` (`executor_node >> console_input`). This was a **critical feedback-interruption bug**!

A complete Agentic iteration runs through two distinct phases:
1.  **Execution Turn**: `PlannerNode` decides to call a tool, routes to `ExecutorNode` (`"tools" >> executor_node`), which runs the tool and appends `toolResult` to the session history.
2.  **Observation Turn**: Instead of asking the user for input again immediately, `ExecutorNode` must loop back **to `PlannerNode` (`executor_node >> planner_node`)!** This allows the LLM to inspect the newly appended tool results, formulate its final text answer, and only *then* route back to `console_input` (`"loop" >> console_input`) to let the user type again.

Correcting this feedback flow is what gives pocket-pi its absolute, flawless stability!

---

## 📡 API-Level Prompt Caching & Token Cost Optimization (`utils.py`)

When building production-grade agent loops, the conversation history can grow extremely fast. If your context window reaches 15,000+ tokens, querying an API (like Anthropic Claude or OpenAI) on *every single turn* becomes very expensive, slow, and latent.

To solve this, **pocket-pi** incorporates standard **Prompt Caching** (giving you up to **99% cache hits** on subsequent turns!).

### The Caching Rules: Order and Breakpoints
For an API prompt cache to succeed, you must follow two highly strict architectural principles:

#### 1. Symmetrical Prefix-Ordering (Static-to-Dynamic)
An API cache matches prefixes from top to bottom. If any character at the beginning changes (like a ticking clock or changing path), the entire cache is invalidated.
*   **Static at the beginning**: We place the constant System Prompt, tools schemas, and base guidelines at the **very top** first.
*   **Dynamic at the very end**: We place changing environmental states (like ticking date and times) and the growing chat history list **at the very bottom (end)** of the system instructions. This ensures that time updates do not invalidate the cached system guidelines!

#### 2. Explicit Caching Breakpoints (`cache_control`)
While OpenAI supports automated server-side caching, **Anthropic Claude strictly requires explicit cache control breakpoints** inside your request payload. If you do not attach them, Anthropic will completely ignore your payload and report a **0% Cache Hit**!

We implement this beautifully inside **`pocket_pi/workflow/utils.py`** by attaching exact `cache_control` breakpoints inside both the system and messages parameters:

### Step 1: System-Prompt Cache
We convert `system` from a simple string to a structured content-block list carrying the cache control directive:
```python
        "system": [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"} # Breakpoint 1!
            }
        ]
```
This instantly freezes and caches the entire 1,500-token system instruction guidelines and tools schemas on the very first turn.

### Step 2: History-Prefix Cache
To cache the growing conversation stream, we intercept the **very latest user message** at the end of our list, convert it to a content block array, and attach the caching breakpoint:

```python
    if anthropic_messages:
        last_msg = anthropic_messages[-1]
        raw_content = last_msg["content"]
        if isinstance(raw_content, str):
            # Convert string to dict and inject cache control
            last_msg["content"] = [
                {
                    "type": "text",
                    "text": raw_content,
                    "cache_control": {"type": "ephemeral"} # Breakpoint 2!
                }
            ]
        elif isinstance(raw_content, list) and len(raw_content) > 0:
            # Shallow copy and inject cache control to the very last block
            new_content = [dict(b) for b in raw_content]
            new_content[-1]["cache_control"] = {"type": "ephemeral"}
            last_msg["content"] = new_content
```

This tells Claude's servers to cache the entire prefix of your conversation up to that message. On subsequent turns, the entire preceding history matches the cache, resulting in a **99% cache hit rate**, speedups of up to **10x** (returning responses in sub-seconds!), and a **90%+ cost reduction**!

---

## 🚀 Bootstrapping the Harness Application (`main.py`)

Our global package entry point reside in **`pocket_pi/main.py`** under `main()`. It handles workspace bootstrapping:

```python
def main():
    display_banner()
    
    # 1. Initialize Configuration Manager
    cwd = os.getcwd()
    config = ConfigManager(cwd=cwd)
    
    # 2. Check and enforce Local project Trust interactive prompt
    if config.local_config_path.exists() and not config.is_project_trusted():
        config.ask_and_save_project_trust()
            
    # Apply global configurations proxies
    config.apply_http_proxy()
    
    # 3. Create a fresh session folder or resume most recent past session tree
    sessions = SessionManager.list_sessions(cwd)
    if sessions:
        latest_file = sessions[0][0]
        session = SessionManager(cwd=cwd, session_file_path=latest_file)
        console.print(f"[green]Resumed active session:[/green] [bold cyan]{session.get_session_name()}[/bold cyan]")
    else:
        session = SessionManager(cwd=cwd)
        console.print(f"[green]Initialized fresh session in CWD.[/green]")
        
    # 4. Initialize the Shared Dict context
    shared = {
        "config": config,
        "session": session,
        "exit": False
    }
    
    # 5. Instantiate and execute the PocketFlow Graph!
    flow = PiAgentFlow()
    try:
        flow.run(shared)
    except KeyboardInterrupt:
        console.print("\n[bold orange]Interrupted. Exiting...[/bold orange]")
        sys.exit(0)
```

Because `PiAgentFlow` connects all terminal state loops, triggering `flow.run(shared)` executes the interactive, state-machine terminal shell indefinitely until the user prompts `/quit` (routing to `QuitNode` which sets `shared["exit"] = True` and gracefully terminates of the process!).

---

## 📦 Bundling, Packaging & Running with `uv`

To package and run the application globally, we register the script in `pyproject.toml` using PEP 621 script-entry metadata and standard Hatch build system:

```toml
[project.scripts]
pocket-pi = "pocket_pi.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
package = true
```

With **`uv`**, compile and run the agent workspace instantly:

```bash
# Sync and packages dependencies
uv sync

# Run the direct package entry point script
uv run pocket_pi/main.py

# Or run the globally compiled binary
uv run pocket-pi
```

---

## 🏆 Congratulations! Course Completed!

You have completed the entire **Pocket-Pi Developer Training Course**! 

You now possess a complete, master-level understanding of:
1.  How to design modular, cyclic state machines using **PocketFlow**.
2.  How to build robust, tree-structured JSONL databases for session histories.
3.  How to write exact, normalized fuzzy-matching file editing algorithms.
4.  How to prevent model tool bias, manage project trust permissions, and build non-blocking terminal completions.

Use this foundational knowledge to build and customize your own AI agents – and let your workflow orchestrations fly! 🎨🚀
