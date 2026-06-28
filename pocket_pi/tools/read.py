import os
from pathlib import Path

def read_file(path: str, offset: int = 1, limit: int = 2000, cwd: str = ".") -> str:
    """
    Read the contents of a file (relative to cwd).
    Supports text files. Output is truncated to 2000 lines or 50KB by default.
    `offset` is the line number to start reading from (1-indexed).
    `limit` is the maximum number of lines to read.
    """
    abs_path = Path(cwd).resolve() / path
    if not abs_path.exists():
        return f"Error: File '{path}' does not exist."
    if abs_path.is_dir():
        return f"Error: '{path}' is a directory. Use bash command to list files if needed."
        
    try:
        # Check file sizes or binary (images can be skipped/read if useful)
        # For simplicity, we read as plain text:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        if total_lines == 0:
            return f"(Empty file: {path})"
            
        # Offset is 1-indexed
        start_idx = max(0, offset - 1)
        if start_idx >= total_lines:
            return f"Error: Offset {offset} is out of bounds. The file has {total_lines} lines."
            
        end_idx = min(total_lines, start_idx + limit)
        slice_lines = lines[start_idx:end_idx]
        
        content = "".join(slice_lines)
        
        # Add a nice header indicating slice details
        header = f"--- [File: {path} | Lines {start_idx + 1}-{end_idx} of {total_lines}] ---\n"
        footer = f"\n--- [End of Slice | Remaining Lines: {max(0, total_lines - end_idx)}] ---"
        
        return header + content + footer
    except Exception as e:
        return f"Error reading file '{path}': {str(e)}"
