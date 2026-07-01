import json
import os
from pathlib import Path

from rich.console import Console

console = Console()

# Global Singleton Flag representing active logger status
_LOGGING_ENABLED = True


class ConfigManager:
    def __init__(self, cwd=None):
        self.cwd = Path(cwd or os.getcwd()).resolve()
        self.global_dir = Path("~/.pocket_pi/agent").expanduser()
        self.global_config_path = self.global_dir / "settings.json"
        self.trust_file_path = self.global_dir / "trust.json"

        self.local_dir = self.cwd / ".pocket_pi"
        self.local_config_path = self.local_dir / "settings.json"

        # Load Defaults
        self.settings = {
            "defaultProvider": "openrouter",
            "defaultModel": "google/gemini-3.5-flash",
            "defaultThinkingLevel": "medium",
            "hideThinkingBlock": False,
            "thinkingBudgets": {
                "minimal": 1024,
                "low": 4096,
                "medium": 10240,
                "high": 32768,
                "xhigh": 65536,
            },
            "compaction": {
                "enabled": True,
                "reserveTokens": 16384,
                "keepRecentTokens": 20000,
            },
            "theme": "dark",
            "defaultProjectTrust": "ask",
            "enableLogging": True,
        }

        self._load_global_settings()
        self._check_and_load_project_settings()
        self.load_provider_keys_to_env()

        # Seed the global logging flag state
        global _LOGGING_ENABLED
        _LOGGING_ENABLED = bool(self.settings.get("enableLogging", True))

    def load_provider_keys_to_env(self):
        providers = self.settings.get("providers", {})
        for provider, data in providers.items():
            if isinstance(data, dict) and "apiKey" in data:
                if provider.lower() == "ollama":
                    os.environ["OLLAMA_BASE_URL"] = data["apiKey"]
                else:
                    env_var_name = f"{provider.upper()}_API_KEY"
                    os.environ[env_var_name] = data["apiKey"]

    def save_provider_key(self, provider: str, api_key: str):
        if "providers" not in self.settings:
            self.settings["providers"] = {}
        if provider not in self.settings["providers"]:
            self.settings["providers"][provider] = {}
        self.settings["providers"][provider]["apiKey"] = api_key

        self.global_dir.mkdir(parents=True, exist_ok=True)

        global_data = {}
        if self.global_config_path.exists():
            try:
                with open(self.global_config_path, "r", encoding="utf-8") as f:
                    global_data = json.load(f)
            except Exception:
                pass

        if "providers" not in global_data:
            global_data["providers"] = {}
        if provider not in global_data["providers"]:
            global_data["providers"][provider] = {}
        global_data["providers"][provider]["apiKey"] = api_key

        try:
            with open(self.global_config_path, "w", encoding="utf-8") as f:
                json.dump(global_data, f, indent=2)
            self.load_provider_keys_to_env()
        except Exception as e:
            console.print(f"[red]Error saving API key to settings.json: {e}[/red]")

    def save_project_model(self, provider: str, model: str):
        """
        Saves the active provider and model permanently inside the project local directory .pocket_pi/settings.json
        """
        self.settings["defaultProvider"] = provider
        self.settings["defaultModel"] = model

        # Automatically trust directory if writing local settings
        trust_db = {}
        if self.trust_file_path.exists():
            try:
                with open(self.trust_file_path, "r", encoding="utf-8") as f:
                    trust_db = json.load(f)
            except Exception:
                pass
        trust_db[str(self.cwd)] = True
        try:
            with open(self.trust_file_path, "w", encoding="utf-8") as f:
                json.dump(trust_db, f, indent=2)
        except Exception:
            pass

        self.local_dir.mkdir(parents=True, exist_ok=True)
        local_data = {}
        if self.local_config_path.exists():
            try:
                with open(self.local_config_path, "r", encoding="utf-8") as f:
                    local_data = json.load(f)
            except Exception:
                pass

        local_data["defaultProvider"] = provider
        local_data["defaultModel"] = model

        try:
            with open(self.local_config_path, "w", encoding="utf-8") as f:
                json.dump(local_data, f, indent=2)
        except Exception as e:
            console.print(f"[red]Error saving local directory settings: {e}[/red]")

    def _load_global_settings(self):
        if self.global_config_path.exists():
            try:
                with open(self.global_config_path, "r", encoding="utf-8") as f:
                    global_settings = json.load(f)
                    self._deep_update(self.settings, global_settings)
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Failed to load global settings from {self.global_config_path}: {e}[/yellow]"
                )

    def _check_and_load_project_settings(self):
        """
        Check if local project settings exist. If so, check trust.
        """
        if not self.local_config_path.exists():
            return

        # Check trust decision
        trusted = self.is_project_trusted()
        if trusted:
            try:
                with open(self.local_config_path, "r", encoding="utf-8") as f:
                    local_settings = json.load(f)
                    self._deep_update(self.settings, local_settings)
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Failed to load local settings from {self.local_config_path}: {e}[/yellow]"
                )
        else:
            console.print(
                f"[yellow]Skipped loading local settings from {self.local_config_path} because this project is not trusted.[/yellow]"
            )

    def is_project_trusted(self) -> bool:
        """
        A project is trusted if:
        1. defaultProjectTrust is "always"
        2. Its CWD path has a true mapping in global trust.json
        """
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
        if cwd_str in trust_db:
            return bool(trust_db[cwd_str])

        # Fallback to visual check if interactive/ask
        return False

    def ask_and_save_project_trust(self) -> bool:
        """
        Interactively ask user to trust this project directory, and save decision to ~/.pocket_pi/agent/trust.json
        """
        if self.settings.get("defaultProjectTrust") == "always":
            return True
        if self.settings.get("defaultProjectTrust") == "never":
            return False

        # Check current DB
        trust_db = {}
        if self.trust_file_path.exists():
            try:
                with open(self.trust_file_path, "r", encoding="utf-8") as f:
                    trust_db = json.load(f)
            except Exception:
                pass

        cwd_str = str(self.cwd)
        if cwd_str in trust_db:
            return bool(trust_db[cwd_str])

        # Prompt user
        console.print(
            "\n[bold yellow]┌──────────────────────────────────────────────────────────┐[/bold yellow]"
        )
        console.print(
            f"[bold yellow]│[/bold yellow] Project directory: [cyan]{cwd_str}[/cyan]"
        )
        console.print(
            "[bold yellow]│[/bold yellow] This project contains local settings, resources, or skills."
        )
        console.print("[bold yellow]│[/bold yellow] Do you trust this project folder?")
        console.print(
            "[bold yellow]│[/bold yellow] [bold rgb(0,255,0)]Y[/bold rgb(0,255,0)] = Yes (allows local settings & execution)"
        )
        console.print(
            "[bold yellow]│[/bold yellow] [bold red]N[/bold red] = No (ignores local settings entirely)"
        )
        console.print(
            "[bold yellow]└──────────────────────────────────────────────────────────┘[/bold yellow]"
        )

        try:
            choice = input("Trust folder? (y/n): ").strip().lower()
            decision = choice.startswith("y")
        except Exception:
            decision = False

        # Create global dir if needed
        self.global_dir.mkdir(parents=True, exist_ok=True)
        trust_db[cwd_str] = decision
        try:
            with open(self.trust_file_path, "w", encoding="utf-8") as f:
                json.dump(trust_db, f, indent=2)
        except Exception as e:
            console.print(f"[red]Error saving trust database: {e}[/red]")

        # Reload configuration in case it is now trusted
        if decision:
            self._check_and_load_project_settings()

        return decision

    def _deep_update(self, d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._deep_update(d[k], v)
            else:
                d[k] = v

    @property
    def provider(self) -> str:
        return self.settings.get("defaultProvider", "anthropic")

    @property
    def model(self) -> str:
        return self.settings.get("defaultModel", "claude-3-7-sonnet-20250219")

    @property
    def thinking_level(self) -> str:
        return self.settings.get("defaultThinkingLevel", "medium")

    @property
    def thinking_budget(self) -> int:
        level = self.thinking_level
        budgets = self.settings.get("thinkingBudgets", {})
        return budgets.get(level, budgets.get("medium", 10240))

    @property
    def compaction_settings(self) -> dict:
        return self.settings.get(
            "compaction",
            {"enabled": True, "reserveTokens": 16384, "keepRecentTokens": 20000},
        )

    def apply_http_proxy(self):
        """
        Check for 'httpProxy' setup inside the settings, and inject environment variables if present.
        """
        proxy = self.settings.get("httpProxy")
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy


def log_debug(message: str):
    """
    Log background debug messages to ~/.pocket_pi/agent/pocket-pi-debug.log
    """
    global _LOGGING_ENABLED
    if not _LOGGING_ENABLED:
        return

    log_dir = Path("~/.pocket_pi/agent").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pocket-pi-debug.log"
    import time

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass
