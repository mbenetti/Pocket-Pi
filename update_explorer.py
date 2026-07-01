import json
import os
import re
from pathlib import Path

SESSIONS_DIR = Path(".pocket_pi/sessions")
EXPLORER_HTML = Path("session_explorer.html")


def build_sessions_data():
    sessions = {}
    if SESSIONS_DIR.exists():
        for f in SESSIONS_DIR.glob("*.jsonl"):
            entries = []
            try:
                with open(f, "r", encoding="utf-8") as file:
                    for line in file:
                        if line.strip():
                            entries.append(json.loads(line.strip()))
            except Exception as e:
                print(f"Error reading {f.name}: {e}")
                continue

            if not entries:
                continue

            # Extract Session Metadata
            header = next((e for e in entries if e.get("type") == "session"), None)
            session_info = next(
                (e for e in entries if e.get("type") == "session_info"), None
            )
            model_changes = [e for e in entries if e.get("type") == "model_change"]

            display_name = (
                session_info.get("name") if session_info else "Untitled Session"
            )
            active_model = "Unknown Model"
            active_provider = "Unknown Provider"

            if model_changes:
                last_change = model_changes[-1]
                active_model = last_change.get("modelId") or active_model
                active_provider = last_change.get("provider") or active_provider
            else:
                msg_with_model = next(
                    (
                        e
                        for e in entries
                        if e.get("type") == "message" and e.get("model")
                    ),
                    None,
                )
                if msg_with_model:
                    active_model = msg_with_model.get("model")
                    active_provider = msg_with_model.get("provider") or "Unknown"

            # Find all leaf nodes
            parent_ids = {e.get("parentId") for e in entries if e.get("parentId")}
            leaf_nodes = [
                e
                for e in entries
                if e.get("id")
                and e.get("id") not in parent_ids
                and e.get("type") == "message"
            ]
            all_leaf_nodes = (
                leaf_nodes
                if leaf_nodes
                else [
                    e for e in entries if e.get("id") and e.get("id") not in parent_ids
                ]
            )

            sessions[f.name] = {
                "filename": f.name,
                "displayName": display_name,
                "header": header,
                "entries": entries,
                "leaves": all_leaf_nodes,
                "activeModel": active_model,
                "activeProvider": active_provider,
                "size": f.stat().st_size,
                "timestamp": header.get("timestamp") if header else f.stat().st_mtime,
            }
    return sessions


def update_explorer():
    if not EXPLORER_HTML.exists():
        print("session_explorer.html not found in the root directory!")
        return

    print("Scanning .pocket_pi/sessions/ and building data...")
    sessions_data = build_sessions_data()
    print(f"Found {len(sessions_data)} session files.")

    html_content = EXPLORER_HTML.read_text(encoding="utf-8")

    # Find the start and end markers
    start_marker = "// START_EMBEDDED_SESSIONS"
    end_marker = "// END_EMBEDDED_SESSIONS"

    start_idx = html_content.find(start_marker)
    end_idx = html_content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print(
            "Error: Could not find EMBEDDED_SESSIONS markers in session_explorer.html!"
        )
        return

    # Build the new embedded block
    json_str = json.dumps(sessions_data, indent=2)
    new_block = f"{start_marker}\n            const EMBEDDED_SESSIONS = {json_str};\n            {end_marker}"

    # Replace the block
    new_html_content = (
        html_content[:start_idx] + new_block + html_content[end_idx + len(end_marker) :]
    )
    EXPLORER_HTML.write_text(new_html_content, encoding="utf-8")
    print("Successfully updated session_explorer.html with embedded session data!")


if __name__ == "__main__":
    update_explorer()
