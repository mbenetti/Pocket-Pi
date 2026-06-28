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
