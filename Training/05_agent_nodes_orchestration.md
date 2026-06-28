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

## 👩‍💻 Exercises for Students

1.  **Compact Trigger**: Implement a `/compact` command router inside `ConsoleInputNode.post`. It should return a custom action string `"compact"`, routing execution to `CompactNode`.
2.  **Add a Custom Slash Command**: Write a new slash command named `/about` that displays a summary panel of pocket-pi's authors, version, and license. Register it in autocomplete list and write its custom Node logic.

---

Next, study how we wire the entire flow and boot our application in **[Module 6: Graph Wiring & App Bootstrapping](06_wiring_and_running.md)**! 🔗
