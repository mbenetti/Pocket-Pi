import http.server
import json
import os
import socketserver
import webbrowser
from pathlib import Path
from urllib.parse import unquote, urlparse

PORT = 8000
DIRECTORY = Path(".")
SESSIONS_DIR = Path(".pocket_pi/sessions")


class ExplorerHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Serve session_explorer.html for the root path
        parsed_url = urlparse(path)
        if parsed_url.path == "/" or parsed_url.path == "/index.html":
            return str(DIRECTORY / "session_explorer.html")
        return super().translate_path(path)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path_parts = parsed_url.path.strip("/").split("/")

        # API: List all sessions
        if (
            path_parts[0] == "api"
            and len(path_parts) == 2
            and path_parts[1] == "sessions"
        ):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            sessions = []
            if SESSIONS_DIR.exists():
                for f in SESSIONS_DIR.glob("*.jsonl"):
                    display_name = "Untitled Session"
                    mtime = f.stat().st_mtime
                    size = f.stat().st_size
                    model = "Unknown Model"
                    provider = "Unknown Provider"
                    msg_count = 0

                    try:
                        with open(f, "r", encoding="utf-8") as file:
                            for line in file:
                                entry = json.loads(line.strip())
                                if entry.get("type") == "session_info":
                                    display_name = entry.get("name") or display_name
                                elif entry.get("type") == "model_change":
                                    model = entry.get("modelId") or model
                                    provider = entry.get("provider") or provider
                                elif entry.get("type") == "message":
                                    msg_count += 1
                                    if not model and entry.get("model"):
                                        model = entry.get("model")
                                        provider = entry.get("provider") or "Unknown"
                    except Exception:
                        pass

                    sessions.append(
                        {
                            "filename": f.name,
                            "displayName": display_name,
                            "timestamp": mtime,
                            "size": size,
                            "model": model,
                            "provider": provider,
                            "msgCount": msg_count,
                        }
                    )
            # Sort newest first
            sessions.sort(key=lambda x: x["timestamp"], reverse=True)
            self.wfile.write(json.dumps(sessions).encode("utf-8"))
            return

        # API: Get specific session content
        elif (
            path_parts[0] == "api"
            and len(path_parts) == 3
            and path_parts[1] == "session"
        ):
            filename = unquote(path_parts[2])
            file_path = SESSIONS_DIR / filename

            # Security check: ensure file is inside SESSIONS_DIR and is a .jsonl file
            if (
                file_path.exists()
                and file_path.parent.resolve() == SESSIONS_DIR.resolve()
                and filename.endswith(".jsonl")
            ):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "Session file not found")
                return

        # Serve static files
        super().do_GET()


def run_server():
    # Ensure sessions directory exists
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    Handler = ExplorerHTTPRequestHandler
    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Starting Pocket-Pi Session Explorer on http://localhost:{PORT}")
        # Open browser automatically
        webbrowser.open(f"http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping server...")


if __name__ == "__main__":
    run_server()
