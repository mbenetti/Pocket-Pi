# Permissions & Security Boundaries

Pocket-Pi employs a strict **Trust and Permission Model** designed to prevent rogue project directories from silently executing untrusted local configurations, loading unauthorized tools, or triggering local scripts without user oversight.

---

## ⚡ The Project Trust System

When Pocket-Pi is started, the first action it takes is to run the directory trust check via `is_project_trusted()`. This verifies whether the active Current Working Directory (CWD) has been explicitly trusted by the user.

```
                          [ Start Pocket-Pi ]
                                   │
                                   ▼
                       [ Check is_project_trusted() ]
                                   │
                 ┌─────────────────┴─────────────────┐
                 ▼ (Trusted)                         ▼ (Not Trusted)
     [ Load Local settings.json ]             [ Ignore Local Settings ]
     [ Load Local Skills         ]             [ Fallback to Global Defaults ]
```

### 1. Default Configurations
The `ConfigManager` loads settings sequentially:
1. **Global Settings**: Located in `~/.pocket_pi/agent/settings.json`.
2. **Local Settings**: Optional directory-specific file `.pocket_pi/settings.json`.

If the current directory is **not trusted**:
- Any local settings under `.pocket_pi/settings.json` are completely ignored (rendered inert).
- Local skills are omitted from the available modules.
- The framework falls back purely on safe, globally approved options.

### 2. The Verification DB (`trust.json`)
The validation state is recorded globally inside:
`~/.pocket_pi/agent/trust.json`

This file is a simple structured key-value mapping of resolved absolute directory paths to boolean trust decisions:
```json
{
  "/Users/username/projects/safe-repo": true,
  "/Users/username/downloads/untrusted-dir": false
}
```

### 3. Prompting for Permission
If a local settings or development directory is detected, and its path is missing from `trust.json`, the user is presented with an interactive trust prompt in the console:

```text
┌──────────────────────────────────────────────────────────┐
│ Project directory: /Users/username/projects/demo
│ This project contains local settings, resources, or skills.
│ Do you trust this project folder?
│ Y = Yes (allows local settings & execution)
│ N = No (ignores local settings entirely)
└──────────────────────────────────────────────────────────┘
```

Selecting `Y` updates the persistent `trust.json` database as `true` and reloads local overrides dynamically. Selecting `N` stores `false` globally, disabling all local skills and setting files permanently for that folder path.

---

## 🔒 Configuration Control Options
Users can configure the global trust behavior via two system-wide options in `~/.pocket_pi/agent/settings.json`:

*   **`defaultProjectTrust: "always"`**: Skips files prompt; automatically trusts and loads local configs in every project directory.
*   **`defaultProjectTrust: "never"`**: Skips prompting; ignores and blocks all local configurations universally.
*   **`defaultProjectTrust: "ask"`** *(Default)*: Prompt the user once per untracked CWD path.

---

## 🛎️ The Pocket-Pi Gatekeeper (Human-In-The-Loop)

To prevent the agent from running arbitrary executables in `bash` or accessing external targets without consent, Pocket-Pi features an advanced real-time security gatekeeper within `ExecutorNode`.

```
                        [ Tool Call Disposed ]
                                  │
                                  ▼
                     [ Gatekeeper Parses Command ]
                                  │
                    ┌─────────────┴─────────────┐
                    ▼ (Authorized)              ▼ (Unauthorized)
            [ Execute Tool ]           [ Prompt Interactive Options ]
                                                │
                                  ┌─────────────┼─────────────┐
                                  ▼ (y)         ▼ (a)         ▼ (n/b)
                             [Run Once]    [Add to Allow]  [Abort Tool]
```

### 1. Gatekeeper Interception
Every time an LLM initiates a tool call, the Gatekeeper:
- **`bash` tool call**: Parses the input string for shell commands (executables) and target domain URLs.
- **`search` tool call**: Inspects request target access (e.g. `api.tavily.com`).

It checks these items against `.pocket_pi/permissions.json` located inside the active project folder.

### 2. Interactive Prompts
If a command or URL is untracked (neither explicitly allowed nor blocked), execution pauses and prompts the user in the active console sessions:

```text
┌──────────────────────────────────────────────────────────┐
│ 🛎️  Pocket-Pi Gatekeeper: Permission Request
│
│  • Type: Command
│  • Resource: npm
│
│  How would you like to handle this request?
│  y = Allow once
│  a = Always allow in this project
│  n = Block once
│  b = Always block in this project
└──────────────────────────────────────────────────────────┘
Select option (y/a/n/b): 
```

### 3. Decisions & Persistent Tracking
Actions chosen by the user map onto distinct outcomes:
*   **Allow Once (`y`)**: Executes the command this single time. Does not write to config.
*   **Always Allow (`a`)**: Writes `"allow"` status for that item under `.pocket_pi/permissions.json` and executes.
*   **Block Once (`n`)**: Instantly aborts execution and returns an aborted message back to the LLM.
*   **Always Block (`b`)**: Writes `"block"` status for that item under `.pocket_pi/permissions.json` and aborts.

### 4. Configuration Write Shields
Since the agent has access to `write`, `edit`, and `bash` tools, it would normally be able to overwrite its own permissions list to bypass restrictions. 

To make the configuration *a secure part of the permissions*, Pocket-Pi implements hardcoded write shields:
- **File Tools (`write_file`, `edit_file`)**: Strictly block and reject any path modification containing `.pocket_pi/` or `.pocket_pi` substrings.
- **Shell Tools (`execute_bash`)**: Rejects any execution strings combining `.pocket_pi` with write or modify shell operations (e.g., `>` redirections, `rm`, `mv`, `cp`, `mkdir`, `touch`, `chmod`, `tee`).
- **Return Status**: Unauthorized modifications yield a flat `Permission Denied` error, maintaining absolute boundaries.

