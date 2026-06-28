# Logging & Session Storage

Pocket-Pi implements structured, highly transparent session and execution logging. Every user message, tool call, reasoning path, and compilation step is captured, formatted, and persisted for active traceability.

---

## 🌲 Tree-based Session Log Storage

Unlike flat linear timeline logs that destroy history when a user back-tracks/re-prompts, Pocket-Pi logs conversation and edits in a **Directed Acyclic Graph (Tree)** format using line-delimited JSON (JSONL).

### 1. Active Path Records
All logs for a specific Current Working Directory (CWD) are stored in individual JSONL files under:
`~/.pocket_pi/agent/sessions/--<cwd-path-replacements>--/`

Each line contains a single JSON entry with an `id` and a `parentId` which defines its exact position within the conversational path:

```json
{"type": "session", "id": "session-uuid", "parentId": null, "version": 3, "timestamp": 178273642.0}
{"type": "session_info", "id": "info-uuid", "parentId": "session-uuid", "name": "Feature Implementation", "timestamp": 178273645.0}
{"type": "message", "id": "msg-user-1", "parentId": "info-uuid", "message": {"role": "user", "content": "How do tool calls work?"}}
```

### 2. How Tool Calls are Recorded in Session Logs
Every tool call initiated by the LLM and executed by the internal dispatcher (`pocket_pi.tools.run_tool`) is logged directly into the JSONL database:

*   **Execution Logs**: When the LLM requests a tool call, a message node of `role: "assistant"` is stored with blocks representing the text and raw tool call requests.
*   **Result Logs**: Once the tool completes execution, the returned output is appended as an independent node with the role **`toolResult`**:
    ```json
    {
      "type": "message",
      "id": "tool-res-uuid",
      "parentId": "assistant-msg-uuid",
      "message": {
        "role": "toolResult",
        "timestamp": 178273648000,
        "toolCallId": "call_abc123",
        "toolName": "read",
        "content": "File contents here..."
      },
      "timestamp": 178273648.0
    }
    ```
*   **Excluded Bash Execution**: Direct user commands typed using `!` are recorded under a specialized role `bashExecution` specifying the command and process output:
    ```json
    {
      "type": "message",
      "id": "bash-exec-uuid",
      "parentId": "previous-id",
      "message": {
        "role": "bashExecution",
        "command": "ls -l",
        "output": "total 40...",
        "excludeFromContext": false
      }
    }
    ```

---

## 🐛 System Debug Logger

Apart from conversational session logs, Pocket-Pi maintains a rolling system-wide diagnostic/debug file:
`~/.pocket_pi/agent/pocket-pi-debug.log`

### 1. What does the Debug Log Record?
- The startup sequence (loading global and local configurations).
- Trust checks and decisions.
- LLM connections, latency measurements, and provider token usage.
- Raw tool input arguments and stack traces of any crashed tools or network errors.

### 2. Example Debug Log Format
```text
2026-06-28 16:44:12 - [CONFIG] Initializing local settings...
2026-06-28 16:44:12 - [TRUST] Checking trust for /Users/username/project
2026-06-28 16:44:12 - [TRUST] Directory verified as trusted.
2026-06-28 16:44:15 - [PLANNER] Querying LLM Provider: openrouter/google/gemini-3.5-flash...
2026-06-28 16:44:18 - [TOOL] Dispatched: bash, Arguments: {'command': 'pytest'}
2026-06-28 16:44:19 - [TOOL] Finished: bash, returned size: 1.2 KB
```
