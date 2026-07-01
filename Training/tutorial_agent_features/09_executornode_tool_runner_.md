# Chapter 9: ExecutorNode (Tool Runner)

In Chapter 8, we explored the `PlannerNode`, Pocket-Pi's intelligent decision-maker, responsible for generating a sequence of thoughts and, crucially, specific tool calls to address user requests. Now, we turn our attention to the operational arm of Pocket-Pi: the `ExecutorNode`. If the `PlannerNode` is the architect drawing up the blueprints, the `ExecutorNode` is the skilled construction crew, taking those plans and making them a reality.

The `ExecutorNode` is Pocket-Pi's 'hands'. It's the central nexus responsible for orchestrating the execution of tools selected by the `PlannerNode`, collecting their results, and feeding that vital information back into the `PocketFlow` state machine. This cyclical feedback loop—plan, execute, observe—is the essence of agentic behavior, much like a control system continuously sensing inputs, computing adjustments, and actuating outputs.

## The ExecutorNode's Workflow: A Reinforced Feedback Loop

The `ExecutorNode` doesn't blindly execute commands. It integrates a critical security layer and ensures that all tool activities are meticulously logged for auditability and for the `PlannerNode`'s subsequent reasoning steps.

Here's a breakdown of its operational flow:

```mermaid
graph TD
    A[PlannerNode] -- "Requests Tools to execute" --> B{ExecutorNode.prep()};
    B -- "Passes tool calls through" --> C[Security Gatekeeper (Human-In-The-Loop)];
    C -- "Confirmed/Blocked Tool Calls" --> D{ExecutorNode.exec()};
    D -- "Executes Tools & Collects Output" --> E[Consolidated Tool Results];
    E -- "Logs results to SessionManager" --> F{ExecutorNode.post()};
    F -- "Routing action: 'default'" --> A;
```

This diagram illustrates the tight loop between the `PlannerNode` and `ExecutorNode`. When the `PlannerNode` has a set of tools it needs to run, it passes control to the `ExecutorNode`. After execution, the `ExecutorNode` sends control *back* to the `PlannerNode` so the LLM can interpret the outcome and decide the next step. This design prevents premature user interaction and enables self-correction, which is fundamental to building stable agentic workflows, akin to how a robust CI/CD pipeline executes tasks and reports status back to the orchestrator for the next stage.

## Phase 1: `prep()` - The Security Checkpoint

Before any tool is run, the `ExecutorNode.prep()` method acts as a critical checkpoint. Its primary responsibility is to pass the pending tool calls through the **Security Gatekeeper**.

```python
# From pocket_pi/workflow/nodes.py (ExecutorNode.prep)
    def prep(self, shared):
        log_debug("[ExecutorNode] Preparing tool execution environment with Gatekeeper...")
        cwd = str(shared["session"].cwd)
        tool_calls = shared["last_tool_calls"]
        
        gatekeeper_tool_calls = []
        for tc in tool_calls:
            tc_copy = dict(tc)
            name = tc["name"]
            args = tc["arguments"]
            
            is_allowed, reason = check_and_prompt_permissions(cwd, name, args)
            if not is_allowed:
                tc_copy["blocked_reason"] = reason
            else:
                tc_copy["blocked_reason"] = None
                
            gatekeeper_tool_calls.append(tc_copy)
            
        return {
            "tool_calls": gatekeeper_tool_calls,
            "cwd": cwd
        }
```
Here's what happens:
1.  **Context Extraction**: It retrieves the current working directory (`cwd`) from the `SessionManager` (via `shared["session"]`) and the list of intended `tool_calls` from `shared["last_tool_calls"]` (populated by the `PlannerNode`).
2.  **Gatekeeper Interception**: For each tool call, it invokes `check_and_prompt_permissions()`. This function, which we'll analyze in detail in Chapter 13, is Pocket-Pi's **human-in-the-loop permission system**. It verifies if the intended action (e.g., executing a `bash` command, accessing a URL) has been previously allowed by the user for the current project. If not, it interactively prompts the user for approval.
3.  **Permission Tagging**: The `check_and_prompt_permissions` function returns a boolean indicating `is_allowed` and a `reason` if blocked. This information is then attached to a copy of the tool call object as `blocked_reason`.
4.  **Prepared Data**: Finally, `prep` returns a dictionary containing the `tool_calls` (now tagged with their permission status) and the `cwd`. This structure ensures the `exec` method receives all necessary information and respects user-defined security policies. This resembles an access control list (ACL) check in a file system or a firewall rule evaluation before allowing network traffic.

## Phase 2: `exec()` - The Action and Observation

The `ExecutorNode.exec()` method receives the pre-processed data from `prep()` and is responsible for actually running the approved tools and collecting their output.

```python
# From pocket_pi/workflow/nodes.py (ExecutorNode.exec)
    def exec(self, data):
        results = []
        for tc in data["tool_calls"]:
            name = tc["name"]
            args = tc["arguments"]
            tc_id = tc["id"]
            blocked_reason = tc.get("blocked_reason")
            
            if blocked_reason:
                console.print(f"\n[bold red]🛑 Gatekeeper: Blocked Tool Call [/bold red][bold cyan]'{name}'[/bold cyan]")
                output = blocked_reason
            else:
                console.print(f"\n[cyan]🛠️ Calling Tool:[/cyan] [bold]{name}[/bold](" + ", ".join([f"{k}={repr(v)}" for k, v in args.items()]) + ")")
                output = run_tool(name, args, cwd=data["cwd"])
                
            lines_list = output.splitlines()
            line_count = len(lines_list)
            char_count = len(output)
            size_kb = round(char_count / 1024, 1)
            
            if blocked_reason:
                console.print(f"  [bold red]✘[/bold red] [bold red]{name}[/bold red] blocked by Gatekeeper.")
            else:
                console.print(f"  [bold green]✔[/bold green] [bold cyan]{name}[/bold cyan] completed. Size: [cyan]{size_kb} KB[/cyan] | Lines: [cyan]{line_count}[/cyan]")
                
            log_debug(f"[ExecutorNode] Tool '{name}' results:\n{output}\n" + "-"*40)
            
            results.append({
                "toolCallId": tc_id,
                "toolName": name,
                "output": output
            })
        return results
```
Here's the breakdown of `exec`'s responsibilities:
1.  **Iterate and Enforce**: It loops through each tool call received from `prep()`. If a `blocked_reason` exists, it skips the actual tool execution, logs a "Permission Denied" message to the user console, and records the `blocked_reason` as the tool's output. This is a critical security enforcement point, ensuring that even if the `PlannerNode` *plans* a disallowed action, it is never executed without explicit user consent.
2.  **Tool Execution**: For approved tool calls, it logs the action to the console and invokes the `run_tool()` utility. This utility, detailed in Chapter 10, dispatches to the appropriate underlying function (e.g., `bash.py` for shell commands, `read.py` for file reads).
3.  **Output Capture and Metainformation**: The `run_tool()` utility returns the command's output. `exec` then calculates metrics like output size and line count, providing immediate feedback to the user on the console. It also writes the detailed output to the debug log (`log_debug`).
4.  **Result Aggregation**: Each tool's output (or `blocked_reason`) is structured into a dictionary containing `toolCallId`, `toolName`, and `output`, and added to a `results` list. This list is then returned to the `post()` method. This is analogous to a batch job processor, executing tasks one by one and accumulating their individual results for a final report.

## Phase 3: `post()` - Logging and Routing

The `ExecutorNode.post()` method receives the `exec_results` and integrates them back into the `PocketFlow` system, specifically by updating the `SessionManager`.

```python
# From pocket_pi/workflow/nodes.py (ExecutorNode.post)
    def post(self, shared, prep_res, exec_results):
        # Format tool results entries inside session log tree
        for res in exec_results:
            # Replicating ToolResultMessage from session-format.md
            tool_content = [
                {"type": "text", "text": res["output"]}
            ]
            shared["session"].append_message(
                role="toolResult",
                content=tool_content,
                tool_call_id=res["toolCallId"],
                tool_name=res["toolName"]
            )
            # Link toolCallId for complete lineage if supported
            
        log_debug("[ExecutorNode] Tool execution completed. Routing back to Planner Node...")
        return "default"
```
Here's the breakdown:
1.  **Session Logging**: For every completed tool execution (whether allowed or blocked), `post` updates the `SessionManager` (`shared["session"]`) by calling `append_message()` with `role="toolResult"`. This is crucial for maintaining an immutable, detailed audit trail of all agent actions, similar to how an event sourcing system records every state change.
2.  **Context for LLM**: The `toolResult` message in the session history is formatted to link the `toolCallId` to the `toolName` and `output`. When the `PlannerNode` next retrieves the session context (via `build_session_context()`), it will see these structured tool results, allowing it to correctly interpret what happened and make informed decisions. This is analogous to a database transaction log, ensuring that every operation leaves a traceable record.
3.  **Routing Back**: Finally, `post` returns the action string `"default"`. As per the `PocketFlow` definition (see `pocket_pi/workflow/flow.py`), a transition after `ExecutorNode` with the action `"default"` leads directly back to the `PlannerNode`. This completes the agentic feedback loop, enabling the LLM to process the tool outputs and continue its reasoning cycle.

## Summary: The ExecutorNode's Role

The `ExecutorNode` is more than just a command runner; it's a meticulously designed component that integrates:
*   **Security Enforcement**: By routing all external interactions through a human-in-the-loop Gatekeeper, it ensures user control and prevents unauthorized operations.
*   **Robust Tool Execution**: It safely dispatches to various tool implementations, managing their execution and capturing their outputs.
*   **Comprehensive Logging**: All tool activities are recorded in the `SessionManager`, providing a persistent, auditable history for the agent's reasoning and user review.
*   **Tight Feedback Loop**: By consistently returning control to the `PlannerNode` after execution, it enables sophisticated self-correction and iterative problem-solving.

This robust `ExecutorNode` is the embodiment of Pocket-Pi's agentic principles, turning LLM plans into tangible actions while maintaining security, transparency, and effective feedback.

Next, we'll dive deeper into the specific tools that the `ExecutorNode` can wield, exploring the design and implementation of Pocket-Pi's extensible **Unified Tool System** in Chapter 10.

---
Generated with Pi Tutorial Builder.