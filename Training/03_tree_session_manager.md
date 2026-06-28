# Module 3: Tree-based Session Manager

This module details how pocket-pi preserves conversation and edits history in a robust, branching tree structure, explaining why flat timelines fail and how we build structured provider completion payloads including compaction zones.

---

## 🌲 The Flaws of Flat History vs. Tree sessions

Most basic coding agents store chat history as a flat, linear array of messages:
```text
User ➔ Assistant ➔ User ➔ Assistant (Linear)
```
If you want to go back to an earlier message and try a different instruction (branching), a flat array forces you to **delete** all subsequent messages, permanently losing parts of your work!

**Pocket-Pi** resolves this by storing conversations as a **Directed Tree Structure**:
*   Every entry is a row in a `.jsonl` file with a unique `id` and a `parentId` pointer matching the message it branches from.
*   The CWD's path is hashed to form private directories: `~/.pocket_pi/agent/sessions/--<cwd-hash>--/`.
*   Branching to an earlier turn simply creates a new child node pointing back to that parent ID, preserving the original branch in-tact!

```text
[User Msg] ─── [Assistant] ─── [User Msg] ─── [Assistant] ─── [User Msg] (Branch A)
                                           │
                                           └─ [User Msg] ─── [Assistant] (Branch B)
```

---

## 🧭 Navigating the Tree Path dynamically

To build history for the LLM, we start at the active `current_leaf_id` (a pointer representing where we are in the tree) and walk backwards to the root (where `parentId` is `None`):

```python
    def get_path_to_root(self, leaf_id: Optional[str] = None) -> List[Dict[str, Any]]:
        curr_id = leaf_id or self.current_leaf_id
        path = []
        visited = set()
        
        while curr_id:
            if curr_id in visited:
                break  # Cycle safety guard
            visited.add(curr_id)
            
            entry = self.entries.get(curr_id)
            if not entry:
                break
                
            path.append(entry)
            curr_id = entry.get("parentId")
            
        # Since we walked backward from leaf to root, reverse it to restore chronological order!
        path.reverse()
        return path
```

---

## 📦 Context Compaction & Payload Construction

When conversations grow too long, pocket-pi prunes oldest entries to save context budget, replacing them with a single **`CompactionEntry`** containing an LLM-generated summary.

When we build the prompt context via `build_session_context()`, we:
1.  Discover the latest `CompactionEntry` on the active path.
2.  Extract its `summary` and inject it first as a specialized context guide.
3.  Prune and omit all messages preceding `firstKeptEntryId`.
4.  Gather and map all messages from `firstKeptEntryId` up to the leaf chronologically!

```python
    def build_session_context(self, leaf_id: Optional[str] = None) -> List[Dict[str, Any]]:
        path = self.get_path_to_root(leaf_id)
        
        # 1. Discover latest CompactionEntry on our path
        compaction_entry = None
        for entry in reversed(path):
            if entry.get("type") == "compaction":
                compaction_entry = entry
                break
                
        context_messages = []
        
        if compaction_entry:
            # We found active compaction!
            comp_summary = compaction_entry["summary"]
            first_kept_id = compaction_entry["firstKeptEntryId"]
            
            # Format and inject summary at the beginning
            context_messages.append({
                "role": "system",
                "content": f"[COMPACTED SESSION CONTEXT SUMMARY]\n\"{comp_summary}\"\n[END SUMMARY]"
            })
            
            # Append only path elements from first_kept_id onwards
            keep = False
            for entry in path:
                if entry["id"] == first_kept_id:
                    keep = True
                if keep and entry["id"] != compaction_entry["id"]: # Skip compaction marker itself
                    msg = self._serialize_entry_to_chat(entry)
                    if msg:
                        context_messages.append(msg)
        else:
            # Linear tree pathway (no compaction)
            for entry in path:
                msg = self._serialize_entry_to_chat(entry)
                if msg:
                    context_messages.append(msg)
                    
        return context_messages
```

---

## 🛠️ Mapping Rich Entries to Standard API format

To ensure absolute, flawless stability during tool-calling sequences, our jsonl records must convert cleanly to standard API types (OpenAI / Anthropic):

```python
    def _serialize_entry_to_chat(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # ...
        role = msg_obj.get("role")
        content = msg_obj.get("content")
        
        # Formats User Messages
        if role in ("user", "system"):
            return {
                "role": role,
                "content": text_content
            }
            
        # Formats Assistant Messages (Pre-matches Tool Calls)
        elif role == "assistant":
            text_lines, tool_calls = [], []
            for block in content:
                if block.type == "text":
                    text_lines.append(block.text)
                elif block.type == "toolCall":
                    tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.arguments)
                        }
                    })
            res = {"role": "assistant", "content": "\n".join(text_lines) if text_lines else None}
            if tool_calls:
                res["tool_calls"] = tool_calls
                if res["content"] is None:
                    res["content"] = None # OpenAI structural requirement
            return res
            
        # Formats Tool Results Messages
        elif role == "toolResult":
            return {
                "role": "tool",
                "tool_call_id": msg_obj.get("toolCallId") or "unknown_id",
                "content": text_content
            }
```

This structured alignment keeps our payloads robust, matching how standard API endpoints pair tool calls to results!

---

## 👩‍💻 Exercises for Students

1.  **Branch switching helper**: Write a method `branch_to(self, target_id)` that updates `self.current_leaf_id` to `target_id`. If `target_id` is not a valid loaded entry in `self.entries`, raise an explaining `ValueError`.
2.  **Telemetry filter**: Write a filter inside `load_session` that automatically ignores and prunes custom telemetry logs (`customType: "obs-log"`) from being loaded into the memory tree to save space.

---

Next, study how pocket-pi executes files and bash scripts in **[Module 4: Unified File, Bash & Search Tools](04_unified_tool_suite.md)**! 🛠️
