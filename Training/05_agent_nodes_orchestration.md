# Module 5: Workflow Nodes & Context Pruners

This module details how we implement pocket-pi's interactive terminal logic, study our custom autocomplete completer, and examine how we dynamically prune tools and swap system prompts to avoid LLM mental contradictions.

---

## 🏛️ Mapping Terminal Input (`ConsoleInputNode`)

Our **`ConsoleInputNode`** is responsible for reading user prompts and routing slash commands. It leverages the advanced **`prompt_toolkit`** library to provide Fish-style command history and interactive autocomplete tabs:

```python
class ConsoleInputNode(Node):
    def __init__(self):
        super().__init__()
        # Instantiate commands and base completions registry
        commands = ["/new", "/login", "/resume", "/model", "/session", "/compact", "/help", "/quit", "/exit"]
        for skill in get_available_skills():
            commands.append(f"/skill:{skill}")
            
        self.completer = SlashCommandCompleter(commands)
        self.style = Style.from_dict({'prompt': 'ansibrightgreen bold'})
        self.session = PromptSession(completer=self.completer, style=self.style)
```

In `exec()`, we check if we are in an active TTY. If yes, we invoke prompt-toolkit to read the line which enables our dropdown controls. Otherwise, we fallback to standard input readline, ensuring background test pipelines never hang:

```python
    def exec(self, info_str):
        console.print(f"\n{info_str}")
        try:
            if sys.stdin.isatty():
                user_input = self.session.prompt("pocket-pi > ").strip()
            else:
                prompt_text = Text("pocket-pi > ", style="bold rgb(0,255,100)")
                console.print(prompt_text, end="")
                user_input = sys.stdin.readline().strip()
            return user_input
        except (KeyboardInterrupt, EOFError):
            return "/quit"
```

---

## ⌨️ Custom Start-of-Line Autocomplete (`SlashCommandCompleter`)

In standard, naive autocomplete setups, a match list is shown anywhere in the phrase. For example, if you are writing a normal sentence and type "session", the autocompleter might pop up and try to complete it to `/session`. This is incredibly annoying!

To solve this, pocket-pi writes a customized completions subclass of prompt-toolkit's **`Completer`**:

```python
from prompt_toolkit.completion import Completer, Completion

class SlashCommandCompleter(Completer):
    def __init__(self, commands):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text
        # 1. Complete ONLY if the input starts with '/'
        if not text.startswith("/"):
            return
            
        before = document.text_before_cursor
        # 2. Complete ONLY if the cursor is in the first word
        if " " in before:
            return  # Deactivate as soon as spaces/arguments are entered!
            
        # 3. Match and yield standard completions
        for cmd in self.commands:
            if cmd.startswith(before):
                yield Completion(cmd, start_position=-len(before))
```
This is a masterpiece of custom completion: it keeps the completions panel completely silent when writing standard text, but pops up immediately when starting slash instructions!

---

## 💻 Direct Local Bash Executions (`!`) as an In-Node Router Design Pattern

In original `pi`, typing any prompt starting with as exclamation mark `!` (e.g. `!ls -la` or `!!pip install numpy`) executes that command immediately on your system shell.

### The Architectural Design Choice: Why not a new Node?
When designing this feature using PocketFlow, a naive state-machine designer might create a standalone `DirectBashNode` and route transitions to it from `ConsoleInputNode`:
```text
console_input - "bash_direct" >> direct_bash_node
```
While visually pleasing in a graph, this introduces **excessive state mobilization overhead**:
1. It forces the state machine to complete `ConsoleInputNode`, mobilize key contexts, instantiate a new node thread, execute, update state, and route the transition back.
2. It introduces minor but noticeable terminal "lag" when running ultra-fast local actions like checking current directories or directories.

### The Solution: In-Node Pre-Processing
Instead, pocket-pi implements a highly optimized **In-Node Router Pattern** directly inside **`ConsoleInputNode.post()`**:

```python
    def post(self, shared, prep_res, user_input):
        shared["user_input"] = user_input
        
        # 1. Intercept direct shell commands immediately in the same prompt node
        if user_input.startswith("!"):
            exclude = user_input.startswith("!!")
            command = user_input.lstrip("!")
            
            # 2. Execute bash cleanly on your system subprocesses
            output = run_tool("bash", {"command": command}, cwd=str(shared["session"].cwd))
            console.print(Panel(output, title="Process Output", border_style="cyan"))
            
            # 3. Log results tree-compatibly
            shared["session"].append_message(
                role="bashExecution",
                content={"command": command, "output": output, "excludeFromContext": exclude}
            )
            
            # 4. Return "input_again" to LOOP immediately without leaving ConsoleInputNode!
            return "input_again"
```

#### Why are the benefits of this design?
1.  **Sub-millisecond execution**: The local process executes immediately inside the node's post phase, with absolute zero routing latency.
2.  **State Preservation**: It bypasses the reasoning planner model entirely, but still persists the command and stdout cleanly in your session tree under `role: "bashExecution"` so subsequent turns remain fully aware! And if `!!` is used, it sets `excludeFromContext=True`, which is cleanly pruned during completions context building to save input tokens.

This is a beautiful example of matching State-Machine declarative routing with localized algorithmic speed!

---

## 🧠 Dynamic Tool Pruning & System Prompt Swapping

Smaller LLM models (and even larger OpenRouter endpoints) suffer from **Tool-Calling Bias**. If you give them a list of tools (like `bash` and `read`) inside your API payload, they feel intensely obligated to use them—generating unnecessary `ls -la` tool calls for simple greetings (like "hi" or general questions).

Pocket-Pi solves this cleanly inside **`PlannerNode.prep()`**:

### Step 1: Query Keyword Inspection
We scan the user's latest message for coding, file, or search indicators:

```python
            coding_keywords = ["file", "read", "write", "edit", "code", "run", "bash", "ls", "grep", ...]
            search_keywords = ["search", "web", "news", "latest", "tavily", "google", "about", ...]
            
            has_coding_marker = any(kw in user_msg for kw in coding_keywords)
            has_search_marker = any(kw in user_msg for kw in search_keywords)
            has_path_marker = "/" in user_msg or "." in user_msg or "\\" in user_msg
```

### Step 2: Tool-Pruning and Prompt-Swapping
If no markers are found, we set **`use_tools = False`** and pass **`tools=[]`** to the model:

```python
        tools_list = TOOLS_SCHEMA if use_tools else []
```

But wait! If `tools` is empty, but our system prompt still tells the model: *"You possess file editing and web search tools. Use web_search to find facts"*, the model gets trapped in an **Instruction Contradiction**. This contradiction causes smaller models like Gemini 3.5 Flash to mute themselves, outputting empty content (`""`).

To solve this, **we dynamically swap the System Prompt** based on tool availability:

```python
        if use_tools:
            # Full Coding Prompt
            system_prompt = f"""You are pocket-pi, an expert coding assistant... Available tools: - read, - write, - edit, - bash, - web_search ..."""
        else:
            # Simple, Clean Conversational Prompt (Zero contradictions!)
            system_prompt = "You are pocket-pi, a helpful and friendly assistant. Answer the user's questions clearly, directly, and concisely using direct conversational text."
```

This dual-state compiler completely resolves both tool bias and system contradictions, ensuring that the model is always confident, fast, and stable!

---

## 🛡️ Human-In-The-Loop Permissions (The Gatekeeper)

To guarantee that the running LLM cannot perform dangerous, unprompted network requests or shell operations without the user's explicit consent, Pocket-Pi weaves a state-machine authorization hook natively into the node transition structure of **`ExecutorNode`**.

Using PocketFlow's architecture, we divide validation and tool execution into distinct stages across `prep()` and `exec()`:

### Step 1: `prep()` Verification & Prompting
In `prep()`, we scan the queued tool calls before execution. 
- For standard shell commands (`bash`), we extract commands and target hostnames using specialized regex parsers (`extract_commands_from_bash` and `extract_urls_from_bash`).
- For standard search commands (`search`), we verify host access (e.g. `api.tavily.com`).

If a command or host represents a new, unauthorized resource in the local `.pocket_pi/permissions.json` file, we halt the flow and prompt the user in the TTY terminal:

```python
    def prep(self, shared):
        cwd = str(shared["session"].cwd)
        tool_calls = shared["last_tool_calls"]
        
        gatekeeper_tool_calls = []
        for tc in tool_calls:
            tc_copy = dict(tc)
            name = tc["name"]
            args = tc["arguments"]
            
            # Check permissions & query user interactively if missing
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

This updates the state mapping for specific commands dynamically as `"allow"` or `"block"` in `.pocket_pi/permissions.json`.

### Step 2: `exec()` Enforcement
In `exec()`, we loop through the prepared tool calls. If a tool call was marked as blocked by the user/Gatekeeper:
- We bypass calling `run_tool()`.
- We immediately write a `Permission Denied` log return.
- If not blocked, it executes as normal.

```python
    def exec(self, data):
        results = []
        for tc in data["tool_calls"]:
            name = tc["name"]
            args = tc["arguments"]
            blocked_reason = tc.get("blocked_reason")
            
            if blocked_reason:
                console.print(f"\n[bold red]🛑 Gatekeeper: Blocked Tool Call [/bold red][bold cyan]'{name}'[/bold cyan]")
                output = blocked_reason
            else:
                # Run the actual tool safely
                output = run_tool(name, args, cwd=data["cwd"])
                
            results.append({
                "toolCallId": tc["id"],
                "toolName": name,
                "output": output
            })
        return results
```

---

## 🎨 Aesthetics: Muted Thoughts & Response Panels

We render thinking process blocks and final responses inside styled Rich Panels, using soft-intensity colors to establish a clear visual hierachy:

```python
        # Super-muted, less-intense gray thinking Process
        if result.get("thinking"):
            console.print(Panel(
                Text(result["thinking"].strip(), style="rgb(90,90,90) italic"),
                title="💭 Thinking Process", title_align="left",
                border_style="rgb(70,70,70)"  # Dim gray borders
            ))
            
        # Bold green, crisp Final Response
        if result.get("text"):
            console.print(Panel(
                Markdown(result["text"].strip()),
                title="🤖 Response", title_align="left",
                border_style="bold rgb(0,200,100)"
            ))
```

This keeps the terminal workspace gorgeously designed, easy on the eyes, and highly legible!

---

## 🧠 Spatial Awareness vs. Heuristic Project Bias

An extremely interesting and advanced aspect of agent behavior in terminal environments is the distinction between **Structural CWD Injection** and **LLM Heuristic Project Bias**.

### The Scenario
Imagine you start the pocket-pi agent inside a parent container directory (e.g. `/workspaces/uv`). 
Your `pocket_pi/main.py` correctly detects the current working directory, and injects it into the system prompt:
```text
Current Working Directory: /workspaces/uv
```
The model is now **fully aware** that its physical process path is `/workspaces/uv`. 

However, imagine the user asks the model to: *"Create a new skill for yourself"*. The model runs a search probe using the `find` tool and discovers a subdirectory named `pi-universe/` which houses existing, structured folders like `pi-universe/package.json`, `pi-universe/skills/`, and `pi-universe/.pi/skills/bowser/SKILL.md`.

Instead of writing the new files directly to the root `/workspaces/uv/`, the model **heuristically decides to write the files inside `pi-universe/.pi/skills/` instead!**

### Why does this happen? (The Heuristic Decision)
This is not an injection error—it is an active **reasoning bias**:
1.  **Project Context Hierarchy**: Because `/workspaces/uv` was a completely empty parent container (lacking any structured package settings or existing skill assets), the model's attentionlayers identified `pi-universe/` as the *actual, active project* that it was brought in to assist with.
2.  **Structural Sincerity**: The model assumed that writing files to the empty root folder would be unhelpful, as those files wouldn't be registered or imported by the subproject's active dependencies. To integrate the skill correctly, it chose to write it into the discovered project subfolder's filesystem.

### How to Mitigate Project Bias in Agent Design
When designing developer-assisting agents, we can prevent this heuristic drift using two primary methods:

1.  **Strict CWD Guidelines**: Add a specific directive in the system instructions telling the model:
    *   *`"Always default to reading, writing, and executing files within the exact, highlighted Current Working Directory (CWD) first, unless the user explicitly refers to a subproject subdirectory."`*
2.  **Explicit User Prompts**: If the user wants to force a direct root file write, they can overrule the heuristic bias by stating the directory explicitly:
    *   *`"Create a new skill and write it directly to the active `.pocket_pi/skills` folder relative to my CWD, do NOT use any subdirectories."`*

This teaches students that **providing spatial context (CWD) is only half the battle**—guiding how the model *prioritizes* that spatial context relative to surrounding folders and repositories is what guarantees clean system-wide executions!

---

## 👩‍💻 Exercises for Students

1.  **Compact Trigger**: Implement a `/compact` command router inside `ConsoleInputNode.post`. It should return a custom action string `"compact"`, routing execution to `CompactNode`.
2.  **Add a Custom Slash Command**: Write a new slash command named `/about` that displays a summary panel of pocket-pi's authors, version, and license. Register it in autocomplete list and write its custom Node logic.

---

Next, study how we wire the entire flow and boot our application in **[Module 6: Graph Wiring & App Bootstrapping](06_wiring_and_running.md)**! 🔗
