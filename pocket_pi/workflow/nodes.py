import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from pocketflow import Node
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from pocket_pi.config import ConfigManager, log_debug
from pocket_pi.session import SessionManager
from pocket_pi.tools import run_tool, TOOLS_SCHEMA
from pocket_pi.workflow.utils import call_llm
from prompt_toolkit.completion import Completer, Completion

console = Console()

def get_available_skills() -> List[str]:
    """Scans global and local skill directories and returns unique skill names."""
    skill_dirs = [
        Path("~/.pi/agent/skills/").expanduser(),
        Path(".pi/skills/"),
        Path(".pocket_pi/skills/"),
        Path("~/.agents/skills/").expanduser(),
        Path(".agents/skills/"),
    ]
    skills = []
    for base in skill_dirs:
        if base.exists() and base.is_dir():
            for child in base.iterdir():
                if child.is_dir():
                    skills.append(child.name)
    return sorted(list(set(skills)))

def find_skill_content(skill_name: str) -> Optional[str]:
    """Finds and reads SKILL.md under active skill directories."""
    skill_dirs = [
        Path("~/.pi/agent/skills/").expanduser(),
        Path(".pi/skills/"),
        Path(".pocket_pi/skills/"),
        Path("~/.agents/skills/").expanduser(),
        Path(".agents/skills/"),
    ]
    for base in skill_dirs:
        if base.exists() and base.is_dir():
            skill_folder = base / skill_name
            if skill_folder.exists() and skill_folder.is_dir():
                skill_md_path = skill_folder / "SKILL.md"
                if skill_md_path.exists():
                    with open(skill_md_path, "r", encoding="utf-8") as f:
                        return f.read()
                # Fallback to direct .md in folder
                md_path = base / f"{skill_name}.md"
                if md_path.exists():
                    with open(md_path, "r", encoding="utf-8") as f:
                        return f.read()
    return None

class SlashCommandCompleter(Completer):
    """
    Custom Completer that:
    1. Only triggers if the text starts with '/'
    2. Only shows options if the cursor is in the first word
    3. Implements progressive multi-stage completions for skills
    """
    def __init__(self, commands, skills):
        self.commands = commands
        self.skills = skills

    def get_completions(self, document, complete_event):
        text = document.text
        if not text.startswith("/"):
            return
            
        before = document.text_before_cursor
        if " " in before:
            # Past first command word, disable dropdown
            return
            
        # Progressive Completion for skills
        if before.startswith("/skill:"):
            typed_part = before[len("/skill:"):]
            for skill in self.skills:
                full_option = f"/skill:{skill}"
                if skill.startswith(typed_part):
                    yield Completion(full_option, start_position=-len(before))
        else:
            # Standard command completions (includes "/skill:" as a single option)
            for cmd in self.commands:
                if cmd.startswith(before):
                    yield Completion(cmd, start_position=-len(before))

def print_session_info(shared):
    """Prints active session display metadata (Session name, model, thinking)."""
    session_name = shared["session"].get_session_name()
    model_name = shared["config"].model
    provider = shared["config"].provider
    thinking = shared["config"].thinking_level
    console.print(f"\n[bold dim]Session: {session_name} | Model: {provider}/{model_name} | Thinking: {thinking}[/bold dim]")

class ConsoleInputNode(Node):
    """
    Reads the user's conversational text or slash commands from the terminal.
    """
    def __init__(self):
        super().__init__()
        from prompt_toolkit import PromptSession
        from prompt_toolkit.styles import Style
        
        commands = ["/new", "/login", "/resume", "/model", "/session", "/compact", "/help", "/quit", "/exit", "/skill:"]
        skills = get_available_skills()
            
        self.completer = SlashCommandCompleter(commands, skills)
        self.style = Style.from_dict({
            'prompt': 'ansibrightgreen bold',
        })
        self.session = PromptSession(
            completer=self.completer,
            style=self.style,
            complete_while_typing=True
        )

    def prep(self, shared):
        return None

    def exec(self, info_str):
        try:
            # Use prompt_toolkit only if standard input is an active terminal (TTY)
            if sys.stdin.isatty():
                user_input = self.session.prompt("pocket-pi > ").strip()
            else:
                prompt_text = Text("pocket-pi > ", style="bold rgb(0,255,100)")
                console.print(prompt_text, end="")
                user_input = sys.stdin.readline().strip()
            return user_input
        except (KeyboardInterrupt, EOFError):
            return "/quit"

    def post(self, shared, prep_res, user_input):
        shared["user_input"] = user_input
        
        if not user_input:
            # Empty input, just render again
            return "input_again"
            
        # Direct local bash execution (starts with "!" or "!!")
        if user_input.startswith("!"):
            exclude = user_input.startswith("!!")
            command = user_input.lstrip("!")
            
            if not command.strip():
                console.print("[bold red]Please specify a bash command, e.g. !ls[/bold red]")
                return "input_again"
                
            console.print(f"\n[cyan]💻 Executing direct bash command:[/cyan] [bold]{command}[/bold]")
            
            # Execute bash safely using our robust tool dispatcher
            output = run_tool("bash", {"command": command}, cwd=str(shared["session"].cwd))
            
            # Print output block nicely
            console.print(Panel(output, title="Process Output", border_style="cyan"))
            
            # Log directly in the session tree as a "bashExecution" role message
            bash_msg_obj = {
                "command": command,
                "output": output,
                "excludeFromContext": exclude
            }
            shared["session"].append_message(
                role="bashExecution",
                content=bash_msg_obj
            )
            return "input_again"
            
        if user_input.startswith("/"):
            parts = user_input.split()
            cmd = parts[0].lower()
            
            if cmd in ["/quit", "/exit"]:
                return "quit"
            elif cmd == "/compact":
                return "compact"
            elif cmd == "/model":
                return "model"
            elif cmd == "/resume":
                return "resume"
            elif cmd == "/session":
                return "session"
            elif cmd == "/new":
                return "new"
            elif cmd == "/login":
                return "login"
            elif cmd.startswith("/skill:"):
                try:
                    skill_name = cmd.split(":")[1].strip()
                except IndexError:
                    skill_name = ""
                    
                if not skill_name:
                    console.print("[bold red]Please specify a skill name, e.g. /skill:sciverse[/bold red]")
                    return "input_again"
                    
                skill_content = find_skill_content(skill_name)
                if not skill_content:
                    console.print(f"[bold red]Skill '{skill_name}' not found.[/bold red]")
                    return "input_again"
                    
                # Inject instructions to session context
                instructions = f"[SKILL SYSTEM INSTRUCTIONS FOR {skill_name.upper()}]\n{skill_content}\n[END SKILL SYSTEM INSTRUCTIONS]"
                shared["session"].append_message(role="system", content=instructions)
                console.print(f"[bold green]Loaded skill instructions: {skill_name}[/bold green]")
                
                # Check for arguments
                arguments = " ".join(parts[1:])
                if arguments:
                    shared["session"].append_message(role="user", content=arguments)
                    return "default"
                else:
                    console.print(f"[bold green]Skill '{skill_name}' successfully loaded into conversation context. Please ask your question now![/bold green]")
                    return "input_again"
            elif cmd in ["/help", "/hotkeys"]:
                return "help"
            else:
                console.print(f"[bold red]Unknown command:[/bold red] {cmd}. Type /help for available actions.")
                return "input_again"
                
        # Normal conversant text prompt, append immediately to the session tree logs
        shared["session"].append_message(role="user", content=user_input)
        return "default"


class HelpNode(Node):
    """displays lists of command shortcuts."""
    def prep(self, shared):
        return None
        
    def exec(self, arg):
        help_text = """
### Available Slash Commands

| Command | Action / Description |
|---|---|
| `/new` | Start a completely empty, fresh coding session |
| `/login` | Interactively setup provider credentials (persisted in global settings) |
| `/resume` | Interactively select and load a past log session |
| `/model` | Switch model providers or specific model IDs |
| `/session` | Inspect active session file name, cost details, and stats |
| `/compact` | Summarize earlier messages manually to save context window |
| `/quit`, `/exit` | Exit the pocket-pi terminal loop gracefully |
| `/help` | Display this helpful table |
"""
        return help_text
        
    def post(self, shared, prep_res, help_content):
        console.print(Panel(Markdown(help_content), title="[bold cyan]Pocket-Pi Manual[/bold cyan]", border_style="cyan"))
        return "loop"


class LoginNode(Node):
    """
    Subflow node to prompt user for API keys and store them globally under settings.json
    """
    def prep(self, shared):
        return shared["config"]

    def exec(self, config):
        console.print("\n[bold cyan]─── Provider Authenticator (/login) ───[/bold cyan]")
        console.print("1. Anthropic")
        console.print("2. OpenAI")
        console.print("3. OpenRouter")
        console.print("4. Cancel")
        
        try:
            choice = input("\nSelect Provider option (1-4): ").strip()
            if choice == "1":
                provider = "anthropic"
            elif choice == "2":
                provider = "openai"
            elif choice == "3":
                provider = "openrouter"
            else:
                return None
                
            import getpass
            key = getpass.getpass(f"Enter API key for {provider}: ").strip()
            if not key:
                console.print("[yellow]Empty API key entered. Cancelled.[/yellow]")
                return None
                
            return {"provider": provider, "key": key}
        except Exception as e:
            console.print(f"[red]Authentication prompt aborted: {e}[/red]")
            return None

    def post(self, shared, prep_res, result):
        if result:
            config = prep_res
            config.save_provider_key(result["provider"], result["key"])
            console.print(f"[green]Successfully saved API key for [bold]{result['provider']}[/bold] in settings.json[/green]")
        return "loop"


class ModelNode(Node):
    """
    Subflow node to change model parameters.
    """
    def prep(self, shared):
        return {
            "current_model": shared["config"].model,
            "current_provider": shared["config"].provider,
            "current_thinking": shared["config"].thinking_level
        }

    def exec(self, current):
        console.print(f"\nCurrent Provider: [cyan]{current['current_provider']}[/cyan]")
        console.print(f"Current Model: [cyan]{current['current_model']}[/cyan]")
        console.print(f"Current Thinking Level: [cyan]{current['current_thinking']}[/cyan] (off/minimal/low/medium/high/xhigh)")
        
        console.print("\n[bold]Select Option:[/bold]")
        console.print("1. Switch to Anthropic Claude 3.7 Sonnet")
        console.print("2. Switch to OpenAI GPT-4o")
        console.print("3. Switch to OpenRouter Gemini 3.5 Flash")
        console.print("4. Switch to Custom model ID")
        console.print("5. Toggle Thinking Level")
        console.print("6. Cancel")
        
        try:
            choice = input("Enter option (1-6): ").strip()
            if choice == "1":
                return {"provider": "anthropic", "model": "claude-3-7-sonnet-20250219"}
            elif choice == "2":
                return {"provider": "openai", "model": "gpt-4o"}
            elif choice == "3":
                return {"provider": "openrouter", "model": "google/gemini-3.5-flash"}
            elif choice == "4":
                prov = input("Enter provider (anthropic/openai/openrouter): ").strip().lower()
                m_id = input("Enter model ID block: ").strip()
                return {"provider": prov, "model": m_id}
            elif choice == "5":
                level = input("Enter level (off/minimal/low/medium/high/xhigh): ").strip().lower()
                return {"thinking_level": level}
            else:
                return {}
        except Exception:
            return {}

    def post(self, shared, prep_res, result):
        if not result:
            return "loop"
            
        if "thinking_level" in result:
            shared["config"].settings["defaultThinkingLevel"] = result["thinking_level"]
            shared["session"].append_thinking_level_change(result["thinking_level"])
            console.print(f"[green]Thinking level changed to: {result['thinking_level']}[/green]")
            print_session_info(shared)
        elif "model" in result:
            shared["config"].save_project_model(result["provider"], result["model"])
            shared["session"].append_model_change(result["model"], result["provider"])
            console.print(f"[green]Swapped model permanently for this project to: {result['provider']}/{result['model']}[/green]")
            print_session_info(shared)
            
        return "loop"


class ResumeNode(Node):
    """
    Lists past session histories inside the project folder, lets user select one.
    """
    def prep(self, shared):
        cwd = shared["session"].cwd
        return cwd

    def exec(self, cwd):
        sessions = SessionManager.list_sessions(cwd)
        if not sessions:
            console.print("[yellow]No past sessions found for this directory.[/yellow]")
            return None
            
        console.print("\n[bold cyan]Select Past Session to Resume:[/bold cyan]")
        for idx, (path, name, mtime) in enumerate(sessions):
            time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
            console.print(f" {idx + 1}. [green]{name}[/green] [dim]({time_str})[/dim]")
            
        console.print(" C. Cancel")
        
        try:
            choice = input("\nEnter choice: ").strip()
            if choice.lower() == "c":
                return None
            val = int(choice)
            if 0 < val <= len(sessions):
                return sessions[val - 1][0] # return filepath
        except Exception:
            pass
        return None

    def post(self, shared, prep_res, selected_file):
        if selected_file:
            shared["session"] = SessionManager(cwd=str(prep_res), session_file_path=selected_file)
            console.print(f"[green]Successfully loaded session log: {shared['session'].get_session_name()}[/green]")
            print_session_info(shared)
        return "loop"


class SessionNode(Node):
    """displays active session metadata."""
    def prep(self, shared):
        return {
            "file": str(shared["session"].session_file),
            "name": shared["session"].get_session_name(),
            "leaf_id": shared["session"].current_leaf_id,
            "total_nodes": len(shared["session"].entries)
        }

    def exec(self, info):
        metadata = f"""
- **Session File Path**: `{info['file']}`
- **Display Name**: `{info['name']}`
- **Current Leaf UUID**: `{info['leaf_id']}`
- **Total Logged Entries**: `{info['total_nodes']}`
"""
        return metadata

    def post(self, shared, prep_res, details):
        console.print(Panel(Markdown(details), title="[bold green]Active Session Stats[/bold green]"))
        return "loop"


class NewSessionNode(Node):
    """Initializes an empty session state."""
    def prep(self, shared):
        return str(shared["session"].cwd)

    def exec(self, cwd):
        try:
            name = input("Enter display name for new session (or press Enter): ").strip()
            return name if name else None
        except Exception:
            return None

    def post(self, shared, prep_res, name):
        shared["session"] = SessionManager(cwd=prep_res)
        if name:
            shared["session"].append_session_info(name) # Store as type: "session_info" correctly!
        console.print("[green]Created a fresh session![/green]")
        print_session_info(shared)
        return "loop"


class CompactNode(Node):
    """
    Compaction controller: Summarizes earlier messages on path to shrink context bounds.
    """
    def prep(self, shared):
        # Fetch current history to summarize
        context = shared["session"].build_session_context()
        # Find cutting bound (everything except the last 3-4 blocks)
        path = shared["session"].get_path_to_root()
        return {
            "context": context,
            "path": path,
            "config": shared["config"]
        }

    def exec(self, data):
        # If there are fewer than 4 messages, skip compaction
        path = data["path"]
        messages_to_summarize = [p for p in path if p.get("type") == "message"]
        if len(messages_to_summarize) < 4:
            return "skipped"
            
        console.print("\n[dim italic]Core: Running context compaction summary...[/dim italic]")
        
        # Build raw serialization
        serialize_text = ""
        for item in messages_to_summarize[:-2]: # Keep the last 2 entries untouched
            msg = item.get("message", {})
            role = msg.get("role", "user")
            content = msg.get("content", "")
            serialize_text += f"{role.upper()}: {content}\n"
            
        # Call LLM to summarises this serialization
        system_prompt = "You are a highly efficient session compacting helper. Write a brief, dense, single-paragraph summary of the conversation and files modified so far. Keep it under 250 words."
        compaction_messages = [
            {"role": "user", "content": f"Please summarize this conversation history briefly. Focus only on the goals accomplished and code edits made:\n\n{serialize_text}"}
        ]
        
        try:
            result = call_llm(
                provider=data["config"].provider,
                model=data["config"].model,
                messages=compaction_messages,
                system_prompt=system_prompt,
                tools=[],
                thinking_level="off"  # Turn off thinking for cheap summary
            )
            summary_text = result["text"]
            
            # The first kept entry is the oldest message that was NOT summarized
            first_kept_id = messages_to_summarize[-2]["id"]
            
            return {
                "summary": summary_text,
                "first_kept_id": first_kept_id,
                "tokens_before": result.get("usage", {}).get("input", 5000)
            }
        except Exception as e:
            console.print(f"[red]Failed to generate compaction summary: {e}[/red]")
            return "failed"

    def post(self, shared, prep_res, result):
        if result == "skipped":
            console.print("[yellow]Not enough messages to perform compaction.[/yellow]")
        elif result == "failed":
            console.print("[red]Compaction was aborted due to LLM error.[/red]")
        else:
            new_id = shared["session"].append_compaction(
                summary=result["summary"],
                first_kept_entry_id=result["first_kept_id"],
                tokens_before=result["tokens_before"]
            )
            console.print(f"[green]Successfully compacted session. Summary saved.[/green]")
            
        return "loop"


class PlannerNode(Node):
    """
    LLM Reasoner node. Receives state context, executes Call_LLM,
    and returns thoughts / requested tool calls.
    """
    def prep(self, shared):
        log_debug("[PlannerNode] Rebuilding session context history...")
        # 1. Build session messages context (respecting compaction boundaries)
        messages = shared["session"].build_session_context()
        
        # 2. Determine if model needs tools (defeats tool-call bias on smaller models)
        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break
                
        use_tools = True
        if user_msg:
            if isinstance(user_msg, list):
                user_msg = "".join([m.get("text", "") for m in user_msg if m.get("type") == "text"])
                
            user_msg_lower = str(user_msg).lower().strip()
            
            # Coding indicators
            coding_keywords = [
                "file", "read", "write", "edit", "code", "run", "bash", "execute", "command",
                "folder", "directory", "ls", "grep", "find", "python", "script", "terminal",
                "install", "pip", "uv", "modify", "replace", "refactor", "create", "delete",
                "rm", "make", "git", "diff", "patch", "package", "lock", "pyproject", "setup",
                "cat", "mkdir", "sh", "yarn", "npm", "node", "compile"
            ]
            search_keywords = [
                "search", "web", "news", "latest", "recent", "tavily", "google", "find out", "who is", "weather",
                "current", "vanguard", "what's the", "how is", "update", "stock", "score", "match", "about"
            ]
            has_coding_marker = any(kw in user_msg_lower for kw in coding_keywords)
            has_search_marker = any(kw in user_msg_lower for kw in search_keywords)
            has_path_marker = "/" in user_msg_lower or "." in user_msg_lower or "\\" in user_msg_lower
            
            if not (has_coding_marker or has_search_marker or has_path_marker):
                use_tools = False
                
        tools_list = TOOLS_SCHEMA if use_tools else []
        
        # 3. Setup System instructions based on tool availability (avoids contradictions)
        current_date = time.strftime("%Y-%m-%d")
        current_time = time.strftime("%H:%M:%S")
        cwd_str = str(shared["session"].cwd)
        
        if use_tools:
            system_prompt = f"""Current Working Directory: {cwd_str}

You are an expert coding assistant operating inside pocket-pi, a coding agent harness. You help users by reading files, executing commands, editing code, and writing new files.

Available tools:
- read: Read the contents of a file. Supports text files; output is truncated. Use offset/limit for large files.
- write: Create or overwrite a file. Automatically creates parent directories.
- edit: Edit a file using exact text replacements.
- bash: Execute a bash command in the current working directory.
- web_search: Search the web using Tavily for real-time news, facts, scores, or information.

Guidelines:
- Use bash for file operations like ls, rg, find
- When searching the web, always prioritize a single, broad, general query first. Do not make multiple sequential specific searches or pre-restrict query scopes with narrow dates/sub-events.
- Be concise in your responses
- Show file paths clearly when working with files

Current Date: {current_date}
Current Time: {current_time}
"""
        else:
            system_prompt = f"Current Working Directory: {cwd_str}\n\nYou are pocket-pi, a highly capable, helpful, and friendly assistant. Answer the user's questions clearly, directly, and concisely using direct conversational text.\n\nCurrent Date: {current_date}\nCurrent Time: {current_time}"
        
        return {
            "config": shared["config"],
            "messages": messages,
            "system_prompt": system_prompt,
            "tools": tools_list
        }

    def exec(self, data):
        provider = data["config"].provider
        model = data["config"].model
        budget = data["config"].thinking_budget
        level = data["config"].thinking_level
        
        log_debug(f"[PlannerNode] Querying LLM Provider: {provider}/{model}...")
        try:
            # Invoke standard API caller bindings with tools schema
            response = call_llm(
                provider=provider,
                model=model,
                messages=data["messages"],
                system_prompt=data["system_prompt"],
                tools=data["tools"],
                thinking_level=level,
                thinking_budget=budget
            )
            return response
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"LLM execution failed: {str(e)}"}

    def post(self, shared, prep_res, result):
        if "error" in result:
            # Clean up the orphaned user message from the JSONL tree so it stays unpolluted
            session = shared["session"]
            if session.current_leaf_id:
                parent_id = session.entries.get(session.current_leaf_id, {}).get("parentId")
                if parent_id:
                    if session.current_leaf_id in session.entries:
                        del session.entries[session.current_leaf_id]
                    if session.current_leaf_id in session.entries_ordered:
                        session.entries_ordered.remove(session.current_leaf_id)
                    session.current_leaf_id = parent_id
            
            # Print beautiful prominent red connection warning
            console.print(Panel(
                f"[bold red]⚠️ Connection Failed:[/bold red] {result['error']}",
                title="[bold red]API Error[/bold red]",
                border_style="red"
            ))
            log_debug(f"[PlannerNode] Connection failure: {result['error']}. Routing back to prompt loop.")
            return "loop"

        # Displays thinking block beautifully (less intense gray, dim borders)
        if result.get("thinking"):
            thinking_content = result["thinking"].strip()
            console.print(Panel(
                Text(thinking_content, style="rgb(90,90,90) italic"),
                title="💭 Thinking Process",
                title_align="left",
                border_style="rgb(70,70,70)"
            ))
            
        # Displays assistant's standard text output inside a response box
        if result.get("text"):
            response_content = result["text"].strip()
            console.print(Panel(
                Markdown(response_content),
                title="🤖 Response",
                title_align="left",
                border_style="bold rgb(0,200,100)"
            ))
            
        # Write response to the active session manager tree logs
        shared["last_response"] = result["text"]
        shared["last_thinking"] = result["thinking"]
        shared["last_tool_calls"] = result["tool_calls"]
        
        # Create corresponding assistant message record in JSONL tree
        # Standard block layout
        content_blocks = []
        if result.get("text"):
            content_blocks.append({"type": "text", "text": result["text"]})
        for tc in result.get("tool_calls", []):
            content_blocks.append({
                "type": "toolCall",
                "id": tc["id"],
                "name": tc["name"],
                "arguments": tc["arguments"]
            })
            
        shared["session"].append_message(
            role="assistant",
            content=content_blocks,
            thinking=result["thinking"] if result["thinking"] else None
        )
        
        if result.get("tool_calls"):
            log_debug(f"[PlannerNode] Routing to Executor with {len(result['tool_calls'])} tool call(s)...")
            return "tools"
        log_debug("[PlannerNode] Reasoning finished. Routing back to user input.")
        return "loop"


class ExecutorNode(Node):
    """
    Tool execution runner. Loops over last_tool_calls, compiles execution results,
    writes them to the session tree logs, and routes back to the planner.
    """
    def prep(self, shared):
        log_debug("[ExecutorNode] Preparing tool execution environment...")
        return {
            "tool_calls": shared["last_tool_calls"],
            "cwd": str(shared["session"].cwd)
        }

    def exec(self, data):
        results = []
        for tc in data["tool_calls"]:
            name = tc["name"]
            args = tc["arguments"]
            tc_id = tc["id"]
            
            console.print(f"\n[cyan]🛠️ Calling Tool:[/cyan] [bold]{name}[/bold](" + ", ".join([f"{k}={repr(v)}" for k, v in args.items()]) + ")")
            
            # Execute tool safely
            output = run_tool(name, args, cwd=data["cwd"])
            
            # Compute sizes and lines
            lines_list = output.splitlines()
            line_count = len(lines_list)
            char_count = len(output)
            size_kb = round(char_count / 1024, 1)
            
            # Print compact single-line indicator representing tool status (hidden by default!)
            console.print(f"  [bold green]✔[/bold green] [bold cyan]{name}[/bold cyan] completed. Size: [cyan]{size_kb} KB[/cyan] | Lines: [cyan]{line_count}[/cyan]")
            
            # Log full details cleanly in our background debug log file for advanced references
            log_debug(f"[ExecutorNode] Tool '{name}' results:\n{output}\n" + "-"*40)
            
            results.append({
                "toolCallId": tc_id,
                "toolName": name,
                "output": output
            })
        return results

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


class QuitNode(Node):
    """Shuts down the orchestration flow gracefully."""
    def prep(self, shared):
        return None
    def exec(self, arg):
        return None
    def post(self, shared, prep_res, exec_res):
        shared["exit"] = True
        console.print("[bold green]Goodbye from Pocket-Pi![/bold green] 👋\n")
        return "exit"
