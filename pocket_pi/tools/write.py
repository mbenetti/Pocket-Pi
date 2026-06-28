import os
from pathlib import Path

def write_file(path: str, content: str, cwd: str = ".") -> str:
    """
    Write content to a file. Creates the file if it doesn't exist, overwrites if it does.
    Automatically creates parent directories.
    """
    abs_path = Path(cwd).resolve() / path
    local_pocket_pi_dir = Path(cwd).resolve() / ".pocket_pi"
    if abs_path.is_relative_to(local_pocket_pi_dir) or ".pocket_pi" in str(abs_path).lower():
        return "Permission Denied: Modifying files in the '.pocket_pi/' configuration directory is strictly prohibited."
        
    try:
        # Create directories if needed
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return f"Successfully wrote {len(content)} characters to '{path}'."
    except Exception as e:
        return f"Error writing file '{path}': {str(e)}"
