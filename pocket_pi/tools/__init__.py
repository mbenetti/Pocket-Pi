from pocket_pi.tools.read import read_file
from pocket_pi.tools.write import write_file
from pocket_pi.tools.edit import edit_file
from pocket_pi.tools.bash import execute_bash
from pocket_pi.tools.search import web_search

# Schema details to send to the LLM (functions mapped to Anthropics/OpenAI json tool definitions)
# This will make our model execution extremely simple.

TOOLS_SCHEMA = [
    {
        "name": "read",
        "description": "Read the contents of a file. Supports text files. Output is truncated to 2000 lines or 50KB by default. Use offset/limit for large files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read (relative or absolute)"
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (1-indexed)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (default is 2000)"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write",
        "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. Automatically creates parent directories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write (relative or absolute)"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "edit",
        "description": "Edit a file using exact text replacements. oldText must match exactly (including spacing). Edits are assessed on the original, non-incrementally.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit (relative or absolute)"
                },
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {
                                "type": "string",
                                "description": "Exact text block to match. Must be unique in target file context."
                            },
                            "newText": {
                                "type": "string",
                                "description": "Replacement text block."
                            }
                        },
                        "required": ["oldText", "newText"]
                    },
                    "description": "List of targeted replacements."
                }
            },
            "required": ["path", "edits"]
        }
    },
    {
        "name": "bash",
        "description": "Execute a bash command in the current working directory. Returns stdout and stderr, truncated to 2000 lines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to run"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "web_search",
        "description": "Search the web using Tavily for real-time news, score updates, facts, or external information. ALWAYS perform a broad, general query first (e.g., 'Venezuela news') instead of multiple narrow, highly specific searches or pre-guessing events. Make a single search call per turn whenever possible.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Broad, general search query (e.g., 'Argentina football matches' or 'Venezuela news') rather than narrow guessing."
                }
            },
            "required": ["query"]
        }
    }
]

def run_tool(name: str, args: dict, cwd: str = ".") -> str:
    """Helper to dispatch tool execution by name."""
    if name == "read":
        return read_file(
            path=args.get("path"),
            offset=args.get("offset", 1),
            limit=args.get("limit", 2000),
            cwd=cwd
        )
    elif name == "write":
        return write_file(
            path=args.get("path"),
            content=args.get("content", ""),
            cwd=cwd
        )
    elif name == "edit":
        return edit_file(
            path=args.get("path"),
            edits=args.get("edits", []),
            cwd=cwd
        )
    elif name == "bash":
        return execute_bash(
            command=args.get("command"),
            cwd=cwd
        )
    elif name == "web_search":
        return web_search(
            query=args.get("query")
        )
    else:
        return f"Error: Tool name '{name}' is unknown."
