# Module 1: PocketFlow Core Abstractions

This module introduces the **PocketFlow** workflow framework. You will learn why state-machine loops are highly suited for Agentic architectures, study the three pillar abstractions, and write your first custom nodes and flows.

---

## 🎯 Why State Machines for LLM Agents?

When developing LLM agents, writing standard, linear Python scripts (e.g. `while True: call_llm()` loops with standard `if/else` checks) quickly becomes complex and brittle:
1.  **Orchestration Bloat**: Adding slash commands, tool execution branches, exceptions handling, and retries results in a massive, nested "spaghetti" script.
2.  **Lack of Reusability**: Nodes cannot be isolated, tested, or re-wired easily.
3.  **No Structural Tracing**: It is extremely difficult to visualize, trace, or audit flow transitions as the agent runs.

**PocketFlow** solves this by modeling your agent loop as a **directed graph (state machine)**. Each logical phase of your agent (e.g., waiting for input, calling the model, executing a bash command) is an independent, self-contained **Node**. Transitions between nodes are declared explicitly, making the logic highly modular, visual, and resilient.

---

## 🏛️ The Three Pillars of PocketFlow

PocketFlow is built on three simple, yet exceptionally powerful, abstractions:

### 1. The Shared State (Context Store)
The **Shared State** is a standard Python dictionary `shared` passed in-place between nodes. It acts as the single source of truth for the entire workflow. Every node reads its inputs from, and records its outputs to, this shared state.

```python
sharedState = {
    "user_input": "read pyproject.toml",
    "history": [...],
    "exit": False
}
```

### 2. The `Node` (Workflow Step)
A `Node` represents a single step in your state machine. To write a node, you subclass `pocketflow.Node` and implement three distinct execution phases. 

This separation of phases is the hallmark of PocketFlow. It keeps your business logic isolated, clean, and testable:

| Phase Method | Purpose | Inputs | Returns | Writes to `shared`? |
| :--- | :--- | :--- | :--- | :--- |
| **`prep(shared)`** | Extracts and prepares raw parameters from the shared state. | `shared` | Any prepared arguments payload | ❌ No (read-only) |
| **`exec(prep_res)`** | Performs the actual computation or API call (e.g. LLM requests or shell runs). | Output of `prep()` | Computation or API results | ❌ No (isolated) |
| **`post(shared, prep, exec)`** | Updates the shared state and returns a routing **action string**. | `shared`, `prep_res`, `exec_res` | `str` action key (e.g., `"default"`) |  Yes (updates state) |

#### ⚠️ Critical Rule: The `post` Return value
The `post` method **MUST** return a string action key (like `"default"`, `"success"`, or `"tools"`). **DO NOT** return the `shared` dictionary itself! Returning a dictionary will cause a `TypeError: unhashable type: 'dict'` inside of PocketFlow's successor router.

#### Code Example: A Simple Reasoning Node
```python
from pocketflow import Node

class SimpleReasonerNode(Node):
    def prep(self, shared):
        # 1. Read input from shared state
        return shared.get("user_input")

    def exec(self, prompt):
        # 2. Perform the isolated computation (LLM Mock)
        response = f"Answer to: {prompt}"
        return response

    def post(self, shared, prep_res, response):
        # 3. Save the results back in shared, and return routing action
        shared["assistant_response"] = response
        return "default"  # Transition key
```

---

### 3. The `Flow` (Graph Orchestrator)
A `Flow` wires your nodes together into a graph and handles execution. In pocket-pi, we always **subclass `Flow` directly** to allow automated tracing.

#### Declaring Transitions (The `>>` and `-` Operators)
You connect nodes together in the `__init__` constructor of your flow using:
*   **Default Connection (`node_a >> node_b`)**: When `node_a` completes with action string `"default"`, execution transitions to `node_b` automatically.
*   **Conditional Connection (`node_a - "action" >> node_b`)**: When `node_a` completes and returns custom action string `"action"`, execution transitions to `node_b`.

#### Code Example: Wiring a Flow
```python
from pocketflow import Flow

class SimpleConversationFlow(Flow):
    def __init__(self):
        # 1. Instantiate the states
        reader = InputReaderNode()
        reasoner = SimpleReasonerNode()
        printer = OutputPrinterNode()
        
        # 2. Declaratively wire the transitions
        reader >> reasoner                      # Default connection (action "default")
        reasoner - "success" >> printer         # If reasoning completes successfully
        reasoner - "needs_clarification" >> reader # Loop back if model has questions
        printer >> reader                       # Loop back for next turn
        
        # 3. Initialize wrapping the starting node using start=reader
        # (NEVER use start_node=reader, which is unsupported)
        super().__init__(start=reader)
```

Running the flow is simple:
```python
if __name__ == "__main__":
    flow = SimpleConversationFlow()
    shared = {"user_input": "Hello world!"}
    flow.run(shared) # Orchestrates until a terminal node (with no successor) is reached
```

---

## 👩‍💻 Exercises for Students

1.  **Draft a Node**: Write a custom Node subclass named `WordCountNode` that reads `shared["text"]`, counts the total words during `exec()`, and saves the integer under `shared["word_count"]`. Return `"default"`.
2.  **Draft a Branching Flow**: Write a Flow wiring three nodes: `InputReaderNode`, `ShortPasswordNode`, and `StandardSignupNode`. If the user's input length is less than 6 characters, route to `ShortPasswordNode` which prints a warning and loops back to input. Otherwise, route to `StandardSignupNode`.

---

Next, let's explore how pocket-pi handles its settings and project security in **[Module 2: Config & Project Trust Manager](02_configuration_manager.md)**! ⚙️
