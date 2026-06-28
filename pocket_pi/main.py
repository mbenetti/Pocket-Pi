import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from pocket_pi.config import ConfigManager
from pocket_pi.session import SessionManager
from pocket_pi.workflow.flow import PiAgentFlow

console = Console()


def display_banner():
    # Elevated 3D shaded isometric welcome header - POCKET π
    banner_text = Text()
    banner_text.append(
        "  ██████╗  ██████╗  ██████╗██╗  ██╗███████╗████████╗     ╔████████████╗\n",
        style="bold rgb(0,255,100)",
    )
    banner_text.append(
        "  ██╔══██╗██╔═══██╗██╔════╝██║ ██╔╝██╔════╝╚══██╔══╝     ╚═ ██════██╔═╝\n",
        style="bold rgb(0,240,120)",
    )
    banner_text.append(
        "  ██████╔╝██║   ██║██║     █████╔╝ █████╗     ██║           ██║   ██║  \n",
        style="bold rgb(0,220,140)",
    )
    banner_text.append(
        "  ██╔═══╝ ██║   ██║██║     ██╔═██╗ ██╔══╝     ██║           ██║   ██║  \n",
        style="bold rgb(0,200,160)",
    )
    banner_text.append(
        "  ██║     ╚██████╔╝╚██████╗██║  ██╗███████╗   ██║   ██╗     ██║   ██║  \n",
        style="bold rgb(0,180,180)",
    )
    banner_text.append(
        "  ╚═╝      ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝     ╚═╝   ╚═╝  \n",
        style="bold rgb(0,160,200)",
    )

    console.print("\n")
    console.print(Panel(banner_text, border_style="green", expand=False))
    console.print(
        "[dim]Type [/dim][cyan]/help[/cyan][dim] for lists of available terminal commands[/dim]\n"
    )


def main():
    display_banner()

    # 1. Initialize Configuration
    cwd = os.getcwd()
    config = ConfigManager(cwd=cwd)

    # 2. Check for Project Trust interactively
    if config.local_config_path.exists() and not config.is_project_trusted():
        trusted = config.ask_and_save_project_trust()
        if not trusted:
            console.print(
                "[yellow]Continuing with global defaults. Project settings ignored.[/yellow]"
            )

    # Apply proxies
    config.apply_http_proxy()

    # 3. Create or Resume Session
    sessions = SessionManager.list_sessions(cwd)
    if sessions:
        # Load most recent session automatically, mimicking pi's continueRecent()
        latest_file = sessions[0][0]
        session = SessionManager(cwd=cwd, session_file_path=latest_file)
        console.print(
            f"[green]Resumed active session:[/green] [bold cyan]{session.get_session_name()}[/bold cyan]"
        )
    else:
        # Create a new session
        session = SessionManager(cwd=cwd)
        console.print(f"[green]Initialized fresh session in CWD.[/green]")

    # 4. Initialize Shared State
    shared = {"config": config, "session": session, "exit": False}

    # Print beautiful active session info on first boot!
    from pocket_pi.workflow.nodes import print_session_info

    print_session_info(shared)

    # 5. Execute PocketFlow Workflow
    flow = PiAgentFlow()
    try:
        flow.run(shared)
    except KeyboardInterrupt:
        console.print(
            "\n[bold rgb(255,100,0)]Flow execution interrupted. Exiting...[/bold rgb(255,100,0)]"
        )
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Critical Error in Flow Execution:[/bold red] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
