import os
from pathlib import Path

def write_file(path: str, content: str, cwd: str = ".") -> str:
    """
    Write content to a file. Creates the file if it doesn't exist, overwrites if it does.
    Automatically creates parent directories.
    """
    abs_path = Path(cwd).resolve() / path
    try:
        # Create directories if needed
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return f"Successfully wrote {len(content)} characters to '{path}'."
    except Exception as e:
        return f"Error writing file '{path}': {str(e)}"
