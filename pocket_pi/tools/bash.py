import subprocess
import os
import sys
import tempfile
from pathlib import Path

def execute_bash(command: str, timeout: int = None, cwd: str = ".") -> str:
    """
    Execute a bash command in the current working directory. Returns stdout and stderr combined.
    Output is truncated to the last 2000 lines or 50KB (whichever is hit first).
    If truncated, the full output is saved to a temp file.
    """
    command_lower = command.lower()
    if ".pocket_pi" in command_lower:
        for indicator in [">", "rm ", "mv ", "cp ", "mkdir ", "touch ", "chmod ", "chown ", "tee "]:
            if indicator in command_lower:
                return "Permission Denied: Modifying files in the '.pocket_pi/' configuration directory is strictly prohibited."

    # Ensure CWD path is resolved
    cwd_path = str(Path(cwd).resolve())
    
    # We use a shell invocation for standard bash command running compatibility
    shell_env = os.environ.copy()
    
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, # Block stdin waiting
            cwd=cwd_path,
            env=shell_env,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        # Read output
        stdout, _ = process.communicate(timeout=timeout)
        exit_code = process.returncode
        
        # Split lines for metric checks
        lines = stdout.splitlines()
        total_lines = len(lines)
        total_bytes = len(stdout.encode("utf-8", errors="replace"))
        
        truncated = False
        limit_lines = 2000
        limit_bytes = 50 * 1024 # 50 KB
        
        # Check truncation limits
        if total_lines > limit_lines or total_bytes > limit_bytes:
            truncated = True
            # Build truncated text (keep latest lines)
            truncated_lines = lines[-limit_lines:]
            truncated_stdout = "\n".join(truncated_lines)
            
            # Save the full results inside a temp log file for future reading
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log", encoding="utf-8") as temp_file:
                temp_file.write(stdout)
                temp_path = temp_file.name
                
            header = f"--- [Bash Output Truncated (Exit Code: {exit_code}) | Full Output saved to: {temp_path}] ---\n"
            return header + f"...[Truncated {total_lines - limit_lines} preceding lines]...\n" + truncated_stdout
            
        header = f"--- [Bash Output (Exit Code: {exit_code})] ---\n"
        return header + stdout
        
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds."
    except Exception as e:
        return f"Error executing bash command: {str(e)}"
