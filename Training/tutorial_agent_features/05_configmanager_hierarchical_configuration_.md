# Chapter 5: ConfigManager (Hierarchical Configuration)

In Chapters 2 and 3, we explored the `PocketFlow` State-Machine Framework and the central role of the Shared State (Context Store) as the data bus for Pocket-Pi. A critical component within this Shared State is the agent's configuration, which dictates its behavior, resource allocation, and access credentials. This is where the `ConfigManager` comes into play. Think of the `ConfigManager` as the system's "control panel" or "registry," providing a single, consistent source for all operational parameters, from LLM API keys to project-specific settings.

Just as a modern operating system has a structured `/etc` directory for global system configuration and application-specific settings often found in a user's `~/.config` or project's `.config` directory, `ConfigManager` orchestrates Pocket-Pi's settings across different scopes. It ensures that the agent always operates with the correct parameters, prioritizing project-specific overrides while maintaining secure handling of sensitive information.

## The Hierarchical Configuration Model

The `ConfigManager` employs a hierarchical loading strategy, much like how configuration files are resolved in frameworks such as Spring Boot (e.g., `application.properties` vs `application-dev.properties`) or how environment variables override default settings in Docker containers. This hierarchy ensures flexibility and maintainability:

1.  **Defaults:** A base set of predefined settings is established within the `ConfigManager` itself. These are Pocket-Pi's universally recommended operational parameters.
2.  **Global User Settings:** Pocket-Pi then attempts to load settings from `~/.pocket_pi/agent/settings.json`. These are your personal, machine-wide preferences.
3.  **Local Project Settings:** If a `.pocket_pi/settings.json` file is present in the current working directory, and the project is trusted, these settings are loaded. **These take precedence over global and default settings**, allowing for project-specific overrides.

This layered approach is crucial. For instance, you might have a global default LLM model, but a specific project might require a different, more powerful model for a particular task. The `ConfigManager` handles this gracefully, applying the most specific setting available.

The loading process can be visualized as follows:

```mermaid
graph TD
    A[ConfigManager Initialization] --> B{Load Internal Defaults};
    B --> C{Load Global Settings: ~/.pocket_pi/agent/settings.json};
    C --> D{Check Local Project: ./.pocket_pi/settings.json};
    D -- Local file exists --> E{Is Project Trusted?};
    E -- Yes --> F{Load Local Settings & Override};
    E -- No & defaultProjectTrust="ask" --> G(Prompt User To Trust);
    G -- User trusts --> F;
    G -- User rejects --> H[Continue without local settings];
    D -- No local file --> H;
    F --> I[Final Merged Configuration];
    H --> I;
    I --> J{Extract API Keys to os.environ};
    J --> K{Apply HTTP Proxy};
    K --> L[ConfigManager Ready];
```

Let's look at the core instantiation within the `ConfigManager`:

```python
class ConfigManager:
    def __init__(self, cwd=None):
        self.cwd = Path(cwd or os.getcwd()).resolve()
        self.global_dir = Path("~/.pocket_pi/agent").expanduser()
        self.global_config_path = self.global_dir / "settings.json"
        
        # ... (other path definitions)
        
        self.settings = { # <-- 1. Defaults are initialized here
            "defaultProvider": "openrouter",
            "defaultModel": "google/gemini-3.5-flash",
            # ... (other default settings)
        }
        
        self._load_global_settings() # <-- 2. Global settings loaded
        self._check_and_load_project_settings() # <-- 3. Local settings loaded (with trust check)
        self.load_provider_keys_to_env() # <-- 4. API keys to env
```
The `__init__` method orchestrates the entire loading sequence, ensuring a fully configured `settings` dictionary is available for the agent. The `_deep_update` helper is crucial for merging dictionaries recursively.

```python
    def _deep_update(self, d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._deep_update(d[k], v)
            else:
                d[k] = v
```
This recursive update function allows nested configuration values to be correctly overridden without destroying entire sections, similar to how `kubectl apply -f` merges configuration changes into a running Kubernetes cluster.

## Secure Credential Management

A paramount concern in agentic systems is the secure handling of API keys and other sensitive credentials. `ConfigManager` addresses this by:

1.  **Storing in Global Settings:** API keys are persistently stored encrypted within `~/.pocket_pi/agent/settings.json`.
2.  **Dynamic Environment Variable Injection:** Crucially, upon loading, these keys are extracted and injected into the current process's environment variables (`os.environ`).

This approach simplifies access for downstream components (like LLM clients) and enhances security. Nodes needing an API key don't directly access the `ConfigManager` to retrieve it; instead, they simply read it from `os.environ`, a standard and secure practice for credential management in many applications, analogous to how cloud services often use IAM roles and temporary credentials set as environment variables.

```python
    def load_provider_keys_to_env(self):
        providers = self.settings.get("providers", {})
        for provider, data in providers.items():
            if isinstance(data, dict) and "apiKey" in data:
                # Converts e.g. "openrouter" key to "OPENROUTER_API_KEY"
                env_var_name = f"{provider.upper()}_API_KEY"
                os.environ[env_var_name] = data["apiKey"]
```
This method automatically maps provider names (e.g., "anthropic") to standard environment variable names (e.g., "ANTHROPIC_API_KEY"), eliminating hardcoding of these variables throughout the codebase.

## Project Trust Boundary

Another critical security feature of the `ConfigManager` is the **Project Trust Boundary**. Unlike a simple script, an agent like Pocket-Pi might execute arbitrary code, interact with the local filesystem, or even launch subprocesses based on local project configurations and tools specified in `.pocket_pi/settings.json`. Executing untrusted local code is a severe security risk.

`ConfigManager` handles this by:

1.  **Default Trust Policy:** You can configure a `defaultProjectTrust` policy (`"always"`, `"never"`, or `"ask"`).
2.  **Trust Database:** Decisions are stored in `~/.pocket_pi/agent/trust.json`, acting as a persistent whitelist/blacklist for project directories.
3.  **Interactive Confirmation:** If the `defaultProjectTrust` is `"ask"` (the default and safest option) and a local configuration exists for an untrusted project, the `ConfigManager` prompts the user for explicit confirmation.

This mechanism acts as a critical "security gatekeeper" (a concept we'll delve deeper into in Chapter 13), preventing malicious configurations from being loaded without explicit user consent. This is similar to how operating systems request permissions for applications to access sensitive resources or how a virtual machine monitor might ask for confirmation before allowing a guest OS to access host resources.

```python
    def is_project_trusted(self) -> bool:
        if self.settings.get("defaultProjectTrust") == "always":
            return True
        if self.settings.get("defaultProjectTrust") == "never":
            return False
            
        trust_db = {}
        if self.trust_file_path.exists():
            # Load existing trust decisions
            # ...
        
        cwd_str = str(self.cwd)
        return bool(trust_db.get(cwd_str, False))

    def ask_and_save_project_trust(self) -> bool:
        # Code to display a rich console prompt to the user
        # ...
        
        try:
            choice = input("Trust folder? (y/n): ").strip().lower()
            decision = choice.startswith("y")
        except Exception:
            decision = False
            
        # Save decision to trust_db and then to trust.json
        # ...
        return decision
```
The `is_project_trusted` method quickly checks predefined policies or the trust database. If a decision is needed, `ask_and_save_project_trust` engages the user, making trustworthiness a conscious decision point.

## Silent Debug Logging

In complex terminal applications built with libraries like `rich`, direct `print()` statements can easily disrupt the carefully rendered user interface, leading to "terminal line scrambling." To maintain a clean UI while providing valuable debug information for background processes, `ConfigManager` integrates a silent logging mechanism: `log_debug`.

```python
# Global Singleton Flag representing active logger status
_LOGGING_ENABLED = True

# ... (inside ConfigManager.__init__)
        global _LOGGING_ENABLED
        _LOGGING_ENABLED = bool(self.settings.get("enableLogging", True))

def log_debug(message: str):
    global _LOGGING_ENABLED
    if not _LOGGING_ENABLED:
        return
        
    log_dir = Path(".pocket_pi")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pocket-pi-debug.log"
    import time
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass
```
This `log_debug` function writes messages to `.pocket_pi/pocket-pi-debug.log` only if logging is explicitly enabled in the configuration (`enableLogging: true`). This is analogous to how industrial control systems or distributed microservices might write detailed internal state to separate log files (e.g., using `log4j` or `logback`) to avoid polluting the operational console. This allows for live monitoring of the agent's internal thought process and transitions without interfering with the interactive user experience.

## Accessing Configuration: Properties and Utility Methods

The `ConfigManager` provides convenient property accessors for commonly used settings, reducing boilerplate and ensuring type consistency.

```python
    @property
    def provider(self) -> str:
        return self.settings.get("defaultProvider", "anthropic")

    @property
    def model(self) -> str:
        return self.settings.get("defaultModel", "claude-3-7-sonnet-20250219")
        
    @property
    def thinking_budget(self) -> int:
        level = self.thinking_level
        budgets = self.settings.get("thinkingBudgets", {})
        return budgets.get(level, budgets.get("medium", 10240))
```
These properties allow any `Node` or component accessing the `ConfigManager` instance (through the Shared State) to retrieve settings cleanly: `shared["config"].model`, `shared["config"].thinking_budget`. This abstracts away the internal dictionary access and provides sensible defaults. This pattern is similar to how a `Settings` object in Django or Flask applications provides structured access to application-wide parameters.

The `ConfigManager` also handles specific runtime needs, such as applying HTTP proxy settings:

```python
    def apply_http_proxy(self):
        proxy = self.settings.get("httpProxy")
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
```
This ensures integration with enterprise network environments without requiring manual setup by the user.

## Summary

The `ConfigManager` is essential for Pocket-Pi's robustness and flexibility. It provides:
*   **Hierarchical Configuration:** A clear system for loading global and project-specific settings, with local overrides.
*   **Secure Credential Management:** API keys are stored securely and automatically injected into environment variables.
*   **Project Trust Boundary:** A crucial security mechanism to prevent the execution of untrusted local configurations.
*   **Silent Debug Logging:** A robust way to log internal operations without disrupting the UI.
*   **Convenient Access:** Property-based access for streamlined retrieval of common settings.

By centralizing and structuring configuration management, `ConfigManager` lays the groundwork for a predictable, secure, and adaptable agent that can operate effectively across various environments and projects, making it a cornerstone for the other advanced features within Pocket-Pi.

## Exercises for Students

1.  **Thinking Level Budgets**: Study `ConfigManager.thinking_budget`. Add a new thinking level of `"max"` that returns `131072` tokens in the budget dictionary within the default settings.
2.  **Telemetry Toggle**: Create a boolean helper property `is_analytics_enabled` that reads `enableAnalytics` from settings. Write a test case (or conceptual code snippet) that demonstrates how you might disable writing debugging files if `enableAnalytics` is `False`. Consider how `log_debug` currently uses `_LOGGING_ENABLED`.

Next, we'll explore how Pocket-Pi manages its interaction history and current working context through the `Tree-Based Session Manager` in Chapter 6.

---

## 🔗 Next Lesson

*   **Next Chapter:** [Chapter 6: Tree-Based Session Manager](06_tree_based_session_manager.md)

---
Generated with Pi Tutorial Builder.