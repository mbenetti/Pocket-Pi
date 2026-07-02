import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SessionManager:
    def __init__(self, cwd: str, session_file_path: Optional[str] = None):
        self.cwd = Path(cwd).resolve()
        self.project_session_dir = self.cwd / ".pocket_pi" / "sessions"

        if session_file_path:
            self.session_file = Path(session_file_path).resolve()
        else:
            self.session_file = None

        self.entries: Dict[str, Dict[str, Any]] = {}
        self.entries_ordered: List[str] = []  # Preserve file chronological order
        self.header: Optional[Dict[str, Any]] = None
        self.current_leaf_id: Optional[str] = None

        if self.session_file and self.session_file.exists():
            self.load_session()
        else:
            self.new_session()

    @classmethod
    def list_sessions(cls, cwd: str) -> List[Tuple[str, str, float]]:
        """
        List all sessions for a project CWD. Returns [(file_path, display_name, mtime)].
        """
        project_dir = Path(cwd).resolve() / ".pocket_pi" / "sessions"

        results = []
        if project_dir.exists():
            for f in project_dir.glob("*.jsonl"):
                display_name = "Untitled Session"
                mtime = f.stat().st_mtime

                # Try to parse the display name from the first session_info or first message
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        for line in file:
                            entry = json.loads(line.strip())
                            if entry.get("type") == "session_info":
                                display_name = entry.get("name") or display_name
                                break
                            elif (
                                entry.get("type") == "message"
                                and not display_name
                                or display_name == "Untitled Session"
                            ):
                                # Extract sample text from first user message
                                message = entry.get("message", {})
                                if message.get("role") == "user":
                                    content = message.get("content", "")
                                    if isinstance(content, list):
                                        content = "".join(
                                            [
                                                c.get("text", "")
                                                for c in content
                                                if c.get("type") == "text"
                                            ]
                                        )
                                    display_name = (
                                        (content[:50] + "...")
                                        if len(content) > 50
                                        else content
                                    )
                except Exception:
                    pass

                results.append((str(f), display_name, mtime))

        # Sort newest first
        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def new_session(self, name: Optional[str] = None):
        """
        Initialize a new session tree structure and save the initial header.
        """
        self.project_session_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = f"{int(time.time())}"
        session_uuid = str(uuid.uuid4())[:8]

        if not self.session_file:
            self.session_file = (
                self.project_session_dir / f"{timestamp_str}_{session_uuid}.jsonl"
            )

        self.entries = {}
        self.entries_ordered = []
        self.current_leaf_id = None

        # Write Session Header
        self.header = {
            "type": "session",
            "id": str(uuid.uuid4()),
            "parentId": None,
            "version": 3,
            "timestamp": time.time(),
        }
        self._write_entry(self.header)

        if name:
            self.append_session_info(name)

    def load_session(self):
        """
        Load session entries from the JSONL file.
        """
        self.entries = {}
        self.entries_ordered = []
        self.current_leaf_id = None

        if not self.session_file or not self.session_file.exists():
            return

        with open(self.session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_id = entry.get("id")
                    if not entry_id:
                        continue

                    self.entries[entry_id] = entry
                    self.entries_ordered.append(entry_id)

                    if entry.get("type") == "session":
                        self.header = entry
                    else:
                        # By default, the leaf of the session is the last appended message or branch-switch entry on the active tree structure.
                        # We will compute the default leaf as the last entry that has a parent which exists in the file.
                        self.current_leaf_id = entry_id
                except Exception:
                    pass

        # Confirm that the leaf's tree resolution reaches the root
        if self.current_leaf_id:
            self.current_leaf_id = self._verify_leaf_path(self.current_leaf_id)

    def _verify_leaf_path(self, leaf_id: str) -> str:
        """
        Ensure the path to root is intact, if broken, fall back to last valid node.
        """
        visited = set()
        curr = leaf_id
        while curr:
            if curr in visited:  # Cycle detected
                return self.entries_ordered[-1] if self.entries_ordered else ""
            visited.add(curr)

            entry = self.entries.get(curr)
            if not entry:
                # Broken link on path, fall back to root or parent
                return self.entries_ordered[-1] if self.entries_ordered else ""
            curr = entry.get("parentId")
        return leaf_id

    def _write_entry(self, entry: Dict[str, Any]):
        """
        Serialize an entry immediately onto the JSONL file.
        """
        entry_id = entry["id"]
        self.entries[entry_id] = entry
        self.entries_ordered.append(entry_id)

        if self.session_file:
            # Assure project session directory exists
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.session_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    # Appending Methods

    def append_message(
        self,
        role: str,
        content: Any,
        thinking: Optional[str] = None,
        usage: Optional[Dict] = None,
        tool_call_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> str:
        """
        Append a new message (user, assistant, or tool) to the tree, returning its ID.
        """
        entry_id = str(uuid.uuid4())

        # Structure matching original messages.ts
        message_obj = {"role": role, "timestamp": int(time.time() * 1000)}

        # Build contents
        if role == "assistant":
            blocks = []
            if thinking:
                blocks.append({"type": "thinking", "thinking": thinking})
            if isinstance(content, str):
                blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                blocks.extend(content)
            message_obj["content"] = blocks
            message_obj["provider"] = "pocket_pi"
            message_obj["model"] = "active_model"
            if usage:
                message_obj["usage"] = usage
        elif role == "toolResult":
            message_obj["content"] = content
            message_obj["toolCallId"] = tool_call_id
            message_obj["toolName"] = tool_name
        else:
            # user or system
            message_obj["content"] = content

        entry = {
            "type": "message",
            "id": entry_id,
            "parentId": self.current_leaf_id,
            "message": message_obj,
            "timestamp": time.time(),
        }

        self._write_entry(entry)
        self.current_leaf_id = entry_id
        return entry_id

    def append_compaction(
        self, summary: str, first_kept_entry_id: str, tokens_before: int
    ) -> str:
        """
        Append a compaction marker with a summary of preceding history, shifting the window bounds.
        """
        entry_id = str(uuid.uuid4())
        entry = {
            "type": "compaction",
            "id": entry_id,
            "parentId": self.current_leaf_id,
            "summary": summary,
            "firstKeptEntryId": first_kept_entry_id,
            "tokensBefore": tokens_before,
            "timestamp": time.time(),
        }
        self._write_entry(entry)
        self.current_leaf_id = entry_id
        return entry_id

    def append_session_info(self, name: str) -> str:
        """
        Set or change the display name of this session folder.
        """
        entry_id = str(uuid.uuid4())
        entry = {
            "type": "session_info",
            "id": entry_id,
            "parentId": self.current_leaf_id,
            "name": name,
            "timestamp": time.time(),
        }
        self._write_entry(entry)
        self.current_leaf_id = entry_id
        return entry_id

    def append_model_change(self, model_id: str, provider: str) -> str:
        """
        Track model configurations changes dynamically.
        """
        entry_id = str(uuid.uuid4())
        entry = {
            "type": "model_change",
            "id": entry_id,
            "parentId": self.current_leaf_id,
            "modelId": model_id,
            "provider": provider,
            "timestamp": time.time(),
        }
        self._write_entry(entry)
        self.current_leaf_id = entry_id
        return entry_id

    def append_thinking_level_change(self, level: str) -> str:
        """
        Track thinking budget configuration level changes.
        """
        entry_id = str(uuid.uuid4())
        entry = {
            "type": "thinking_level_change",
            "id": entry_id,
            "parentId": self.current_leaf_id,
            "thinkingLevel": level,
            "timestamp": time.time(),
        }
        self._write_entry(entry)
        self.current_leaf_id = entry_id
        return entry_id

    # Tree Navigation and Context Building

    def get_path_to_root(self, leaf_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Walks backward from leaf_id to root, and returns chronologically ordered entries.
        """
        curr_id = leaf_id or self.current_leaf_id
        path = []
        visited = set()

        while curr_id:
            if curr_id in visited:
                break  # Prevent cycle crashes
            visited.add(curr_id)

            entry = self.entries.get(curr_id)
            if not entry:
                break

            path.append(entry)
            curr_id = entry.get("parentId")

        # Since we walked backwards, reverse list to restore chronology (oldest to newest)
        path.reverse()
        return path

    def build_session_context(
        self, leaf_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Replicates buildSessionContext():
        1. Walks path from leaf to root.
        2. Scans for CompactionEntry on path.
        3. If compaction exists:
           - Injects compaction summary content at the beginning (usually as a system or special user message).
           - Drops/skips all path elements that are older than firstKeptEntryId.
           - Appends all path elements starting from firstKeptEntryId onwards.
        4. Serializes entries to ChatCompletion message format: [{"role": ..., "content": ...}].
        """
        path = self.get_path_to_root(leaf_id)

        # 1. Look for the latest CompactionEntry on the active path
        compaction_entry = None
        for entry in reversed(path):
            if entry.get("type") == "compaction":
                compaction_entry = entry
                break

        context_messages = []

        if compaction_entry:
            # We found a compaction!
            comp_summary = compaction_entry["summary"]
            first_kept_id = compaction_entry["firstKeptEntryId"]

            # Format compaction summary block nicely as an initial context guide
            context_messages.append(
                {
                    "role": "system",
                    "content": f'[COMPACTED SESSION CONTEXT SUMMARY]\nThis is a brief summary of earlier messages in this conversation (the preceding history was pruned to fit context bounds):\n\n"{comp_summary}"\n[END COMPACTED SUMMARY]',
                }
            )

            # Keep only entries on the path that occur AFTER or correspond to the first_kept_id
            keep = False
            for entry in path:
                if entry["id"] == first_kept_id:
                    keep = True
                if (
                    keep and entry["id"] != compaction_entry["id"]
                ):  # Skip the compaction marker itself
                    msg = self._serialize_entry_to_chat(entry)
                    if msg:
                        context_messages.append(msg)
        else:
            # Simple linear tree pathway with no compaction boundaries
            for entry in path:
                msg = self._serialize_entry_to_chat(entry)
                if msg:
                    context_messages.append(msg)

        return context_messages

    def _serialize_entry_to_chat(
        self, entry: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Map a session entry record to standard ChatGPT message format.
        Preserves fully structured tool calls and tool result alignments.
        """
        if entry.get("type") != "message":
            return None

        msg_obj = entry.get("message", {})
        role = msg_obj.get("role")
        content = msg_obj.get("content")

        # 1. Format User & System Messages
        if role in ("user", "system"):
            text_content = ""
            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                text_content = "\n".join(
                    [b.get("text", "") for b in content if b.get("type") == "text"]
                )
            return {"role": role, "content": text_content}

        # 2. Format Assistant Messages (Preserves Tool Calls)
        elif role == "assistant":
            text_lines = []
            tool_calls = []

            if isinstance(content, str):
                text_lines.append(content)
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        text_lines.append(block.get("text", ""))
                    elif block.get("type") == "toolCall":
                        tool_calls.append(
                            {
                                "id": block.get("id"),
                                "type": "function",
                                "function": {
                                    "name": block.get("name"),
                                    "arguments": json.dumps(block.get("arguments", {})),
                                },
                            }
                        )

            text_content = "\n".join(text_lines) if text_lines else None

            res = {"role": "assistant", "content": text_content}
            if tool_calls:
                res["tool_calls"] = tool_calls
                if text_content is None:
                    res["content"] = None

            return res

        # 3. Format Tool Result Messages
        elif role == "toolResult":
            text_content = ""
            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                text_content = "\n".join(
                    [b.get("text", "") for b in content if b.get("type") == "text"]
                )

            return {
                "role": "tool",
                "tool_call_id": msg_obj.get("toolCallId") or "unknown_id",
                "content": text_content,
            }

        # 4. Format Direct Local Bash Execution Messages
        elif role == "bashExecution":
            if isinstance(content, dict) and content.get("excludeFromContext"):
                return None

            command = content.get("command", "") if isinstance(content, dict) else ""
            output = content.get("output", "") if isinstance(content, dict) else ""
            return {
                "role": "user",
                "content": f"[Direct Local Terminal Execution]\nCommand: !{command}\nOutput:\n{output}",
            }

        return None

    def branch_to(self, entry_id: str):
        """
        Moves current leaf position to any earlier entry in the tree structure.
        """
        if entry_id not in self.entries:
            raise ValueError(
                f"Entry {entry_id} does not exist in the session database."
            )
        self.current_leaf_id = entry_id

    def get_session_name(self) -> str:
        """
        Scan session_info entries on the path to find the current session display name.
        """
        path = self.get_path_to_root()
        for entry in reversed(path):
            if entry.get("type") == "session_info":
                return entry.get("name", "Untitled Session")
        return "Untitled Session"

    def get_session_id(self) -> str:
        """
        Return a unique, stable UUID for this session.
        """
        if self.header and "id" in self.header:
            return self.header["id"]
        if self.session_file:
            return self.session_file.stem
        return "default_session"

    def clear_history(self):
        """
        Resets conversation leaf back to the session_info entry (or root),
        wiping active chat memory while preserving the session file name and identity!
        """
        info_id = None
        for entry in self.entries.values():
            if entry.get("type") == "session_info":
                info_id = entry.get("id")
                break
        self.current_leaf_id = info_id
