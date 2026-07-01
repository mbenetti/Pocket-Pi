# Chapter 14: Project Trust Boundary

Having meticulously explored Pocket-Pi's intricate internal workings, from its `uv`-based bootstrapping (Chapter 1) and hierarchical configuration (`ConfigManager` in Chapter 5) to its robust `ExecutorNode` (Chapter 9) and `Unified Tool System` (Chapter 10), we now confront a critical aspect of agentic safety: the **Project Trust Boundary**. This feature directly addresses the inherent risks of allowing an AI agent, especially one with code execution capabilities, to operate in your local development environment.

Imagine your project directory as a secure facility. The Project Trust Boundary acts as a digital gatekeeper at the main entrance. When Pocket-Pi, acting as a new contractor, attempts to access or modify resources within this facility based on a potentially unfamiliar or externally provided configuration (`.pocket_pi/settings.json`), the gatekeeper performs a security check. This is designed to prevent untrusted code configurations from running automatically and potentially causing unintended damage, ensuring you always retain explicit control over what the agent does in your workspace.

The significance of this boundary cannot be overstated. An LLM agent, by design, processes instructions and executes arbitrary code or commands. If an unknowingly malicious or poorly configured `.pocket_pi/settings.json` file were downloaded or generated (e.g., from an untrusted Git repository), it could, without this boundary, immediately override crucial default behaviors, load harmful custom tools, or introduce security vulnerabilities. This feature enforces a crucial **human-in-the-loop** decision for environment-specific configurations.

## The Threat Model: Why Trust Matters

The primary threat model addressed by the Project Trust Boundary is the execution of arbitrary, potentially dangerous code specified in a local configuration file. Consider these scenarios:

1.  **Malicious Overrides**: An untrusted `.pocket_pi/settings.json` could redefine standard tools to execute malicious scripts instead of their intended functions.
2.  **Sensitive Data Exposure**: Custom tools or configurations could attempt to exfiltrate sensitive environment variables, API keys, or project source code.
3.  **Unintended System Modification**: Misconfigured `bash` commands could delete critical files (`rm -rf /`), alter system settings, or install unwanted software.
4.  **Resource Exhaustion**: An agent could be instructed to maliciously use excessive CPU, memory, or network resources, impacting system stability.

The Project Trust Boundary mitigates these risks by requiring explicit user consent before any local, project-specific configuration (which might contain such instructions) is loaded and applied. This is similar to how a web browser warns you about downloading files from untrusted sources or how an operating system requests elevated permissions before installing new software.

## Mechanisms of the Trust Boundary

The `ConfigManager` (Chapter 5) is the component primarily responsible for enforcing the Project Trust Boundary. It orchestrates the loading of hierarchical settings, and crucially, inserts a trust verification step before applying any local project-specific configurations.

The process for evaluating and enforcing project trust can be visualized as follows:

```mermaid
graph TD
    A[Pocket-Pi Starts in CWD] --> B{ConfigManager Initializes};
    B --> C[Load Internal Defaults];
    C --> D[Load Global User Settings: ~/.pocket_pi/agent/settings.json];
    D --> E{Local Project Config Exists? (.pocket_pi/settings.json)};
    E -- No --> H[Final Merged Configuration (without local)];
    E -- Yes --> F{Check Trust Status (Internal DB & Policy)};
    F -- Trusted (or Policy="always") --> I[Load Local Project Settings];
    F -- Untrusted & Policy="ask" --> G(Present Interactive Trust Prompt);
    G -- User Approves --> J[Record Trust, Load Local Settings];
    G -- User Denies --> H;
    I --> H;
    J --> H;
    H --> K[Project Trust Boundary Enforcement Complete];
```

Let's examine the core logic within `pocket_pi/config.py` that implements this boundary.

### 1. Trust Policy Configuration (`defaultProjectTrust`)

The `ConfigManager` allows developers to set a `defaultProjectTrust` policy in their global `~/.pocket_pi/agent/settings.json` (or inherited from defaults):

```python
# From pocket_pi/config.py
        self.settings = {
            # ... other settings ...
            "defaultProjectTrust": "ask", # Can be "always", "never", "ask"
            # ...
        }
```
*   `"ask"` (default and recommended): Prompts the user interactively if an untrusted project folder contains local configurations.
*   `"always"`: Automatically trusts all project folders with local configurations without prompting. This should be used with caution.
*   `"never"`: Never trusts local project configurations, effectively ignoring any `.pocket_pi/settings.json` file.

This policy-driven approach gives the user granular control over the security posture of their agent, similar to how an Active Directory Group Policy or Cloud IAM policy dictates access rules across a network.

### 2. The Trust Database (`~/.pocket_pi/agent/trust.json`)

User trust decisions are not ephemeral; they are persisted in a simple JSON file, `~/.pocket_pi/agent/trust.json`. This database acts as a whitelist for specific project directories.

```python
# From pocket_pi/config.py
    def is_project_trusted(self) -> bool:
        if self.settings.get("defaultProjectTrust") == "always":
            return True
        if self.settings.get("defaultProjectTrust") == "never":
            return False
            
        trust_db = {}
        if self.trust_file_path.exists():
            try:
                with open(self.trust_file_path, "r", encoding="utf-8") as f:
                    trust_db = json.load(f)
            except Exception:
                pass
                
        cwd_str = str(self.cwd)
        # Check if current project's CWD is in the trust database
        if cwd_str in trust_db:
            return bool(trust_db[cwd_str])
            
        return False # Not explicitly trusted
```
The `is_project_trusted` method first checks the global policy. If `"ask"`, it then consults the `trust_db` for a previously recorded decision for the current working directory (`self.cwd`). If an entry exists and is `True`, the project is trusted. Otherwise, the decision defaults to `False`. This persistent record-keeping prevents repetitive prompts for directories already vetted by the user.

### 3. Interactive User Confirmation (`ask_and_save_project_trust`)

If `is_project_trusted()` returns `False` and the `defaultProjectTrust` policy is `"ask"`, Pocket-Pi engages in an interactive console prompt to seek explicit user consent.

```python
# From pocket_pi/config.py
    def ask_and_save_project_trust(self) -> bool:
        # ... (checks for defaultProjectTrust "always"/"never" or existing trust in DB) ...
            
        # Draw panels using rich console ...
        console.print("\n[bold yellow]┌──────────────────────────────────────────────────────────┐[/bold yellow]")
        console.print(f"[bold yellow]│[/bold yellow] Project directory: [cyan]{cwd_str}[/cyan]")
        console.print("[bold yellow]│[/bold yellow] This project contains local settings, resources, or skills.")
        console.print("[bold yellow]│[/bold yellow] Do you trust this project folder?")
        console.print("[bold yellow]│[/bold yellow] [bold rgb(0,255,0)]Y[/bold rgb(0,255,0)] = Yes (allows local settings & execution)")
        console.print("[bold yellow]│[/bold yellow] [bold red]N[/bold red] = No (ignores local settings entirely)")
        console.print("[bold yellow]└──────────────────────────────────────────────────────────┘[/bold yellow]")
        
        try:
            choice = input("Trust folder? (y/n): ").strip().lower()
            decision = choice.startswith("y")
        except Exception:
            decision = False
            
        # ... (save decision to trust_db and then to trust.json) ...
            
        if decision:
            self._check_and_load_project_settings() # Reload config to apply newly trusted settings
            
        return decision
```
This method displays a clear, visually distinct prompt using `rich.console`, outlining the implications of trusting (or not trusting) the folder. The user's input (`y`/`n`) directly determines whether the local `.pocket_pi/settings.json` is loaded. The decision is then saved to `trust.json` for future sessions. If the user approves, `_check_and_load_project_settings` is re-invoked to apply the now-trusted configuration. This ensures that the user is actively involved in sensitive security decisions, much like a sudo prompt before executing administrative commands.

### 4. Automatic Trust on Local Save

An interesting point of integration for the trust boundary is when a user explicitly saves a project-specific model (`/model` command). If a user uses `/model` to set a model that's specific to the current directory, it signals that the user inherently trusts that directory. Thus, the `ConfigManager` automatically records a trust decision for that directory.

```python
# From pocket_pi/config.py
    def save_project_model(self, provider: str, model: str):
        # ... (save defaultProvider and defaultModel to local_config_path) ...
        
        # Automatically trust directory if writing local settings
        trust_db = {}
        if self.trust_file_path.exists():
            try:
                with open(self.trust_file_path, "r", encoding="utf-8") as f:
                    trust_db = json.load(f)
            except Exception:
                pass
        trust_db[str(self.cwd)] = True # Explicitly record trust for current CWD
        try:
            with open(self.trust_file_path, "w", encoding="utf-8") as f:
                json.dump(trust_db, f, indent=2)
        except Exception:
            pass
        # ... rest of the saving logic ...
```
This convenience feature streamlines the user experience by implicitly acknowledging trust when the user performs an action that implies intent to manage project-specific settings.

## Integration with the `Unified Tool System`

The Project Trust Boundary directly impacts the `Unified Tool System` (Chapter 10). Tools like `write_file` and `execute_bash` contain explicit security checks to prevent tampering with the `.pocket_pi/` directory, even if the project is trusted.

```python
# Example from pocket_pi/tools/write.py
def write_file(path: str, content: str, cwd: str = ".") -> str:
    abs_path = Path(cwd).resolve() / path
    local_pocket_pi_dir = Path(cwd).resolve() / ".pocket_pi"
    if abs_path.is_relative_to(local_pocket_pi_dir) or ".pocket_pi" in str(abs_path).lower():
        # Even if trusted, prevent writing to the config directory itself
        return "Permission Denied: Modifying files in the '.pocket_pi/' configuration directory is strictly prohibited."
    # ... rest of write logic ...
```
This layered security ensures that even a trusted project cannot internally modify the very configuration files or trust database that define its security context. This is a robust defense mechanism, similar to how a trusted root certificate authority (CA) restricts how its own certificate can be revoked to protect the integrity of the trust chain.

## Summary

The Project Trust Boundary is a fundamental security cornerstone of Pocket-Pi. By introducing a human-in-the-loop decision point for local project configurations and persistently recording those decisions, Pocket-Pi ensures:

*   **Explicit User Control**: No untrusted local configuration can be loaded or executed without explicit consent.
*   **Protection Against Malicious Configurations**: Safeguards against arbitrary code execution or unintended system modifications.
*   **Persistent Trust Management**: User-approved projects are remembered, streamlining subsequent interactions.
*   **Layered Security**: Even trusted projects face restrictions on modifying core configuration files, preventing self-compromise.

This feature embodies Pocket-Pi's commitment to both powerful agentic capabilities and robust user-centric security, making it a reliable and transparent tool for developers.

Having thoroughly covered the Project Trust Boundary and how it safeguards your operations, we have now concluded our deep dive into Pocket-Pi's core architecture and features. You are now equipped with a comprehensive understanding of how this sophisticated agent functions, from its foundational bootstrapping to its intelligent reasoning and secure execution.

---

## 🔗 Next Lesson

*   **Back to Index:** [Unified Learning & Training Portal Index](00_index.md)

---
Generated with Pi Tutorial Builder.