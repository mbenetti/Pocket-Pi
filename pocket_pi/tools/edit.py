import os
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Tuple

def normalize_to_lf(text: str) -> str:
    """Normalize line endings to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")

def detect_line_ending(content: str) -> str:
    """Detect local line ending in a file."""
    crlf_idx = content.find("\r\n")
    lf_idx = content.find("\n")
    if lf_idx == -1:
        return "\n"
    if crlf_idx == -1:
        return "\n"
    return "\r\n" if crlf_idx < lf_idx else "\n"

def normalize_for_fuzzy_match(text: str) -> str:
    """
    Identical representation of TS normalizeForFuzzyMatch:
    - NFKC normalize
    - Trim trailing whitespaces from individual lines
    - Smart quotes/single quotes to ASCII
    - Various dashes/hyphens to ASCII hyphen '-'
    - Special spaces (NBSP, em spaces) to regular space ' '
    """
    normalized = unicodedata.normalize("NFKC", text)
    
    # Trim trailing whitespaces from individual lines
    lines = normalized.split("\n")
    trimmed_lines = [line.rstrip() for line in lines]
    normalized = "\n".join(trimmed_lines)
    
    # Smart single quotes
    for char in ["\u2018", "\u2019", "\u201A", "\u201B"]:
        normalized = normalized.replace(char, "'")
        
    # Smart double quotes
    for char in ["\u201C", "\u201D", "\u201E", "\u201F"]:
        normalized = normalized.replace(char, '"')
        
    # Various dashes/hyphens
    for char in ["\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212"]:
        normalized = normalized.replace(char, "-")
        
    # Special spaces to regular space
    for char in ["\u00A0", "\u2002", "\u2003", "\u2004", "\u2005", "\u2006", "\u2007", "\u2008", "\u2009", "\u200A", "\u202F", "\u205F", "\u3000"]:
        normalized = normalized.replace(char, " ")
        
    return normalized

def get_line_offsets(content: str) -> List[Tuple[int, int]]:
    """Returns a list of (start_char_offset, end_char_offset) for each line in the content."""
    lines = content.split("\n")
    offsets = []
    current = 0
    for line in lines:
        start = current
        end = current + len(line)
        offsets.append((start, end))
        current = end + 1 # +1 for the '\n' character
    return offsets

def find_target_line_range(offsets: List[Tuple[int, int]], start_char: int, end_char: int) -> Tuple[int, int]:
    """Finds which line index range (start_line, end_line) boundary maps to char index boundaries (0-indexed)."""
    start_line = -1
    for idx, (s, e) in enumerate(offsets):
        # Check if the character index falls within this line (including the boundary or line endings)
        if start_char >= s and start_char <= e + 1:
            start_line = idx
            break
            
    if start_line == -1:
        start_line = 0
        
    end_line = start_line
    for idx in range(start_line, len(offsets)):
        s, e = offsets[idx]
        if s <= end_char:
            end_line = idx
        else:
            break
            
    return start_line, end_line

def apply_text_edit(original_content: str, edits: List[Dict[str, str]], path: str) -> str:
    """
    Substance of applyEditsToNormalizedContent():
    1. Working in LF-normalized content.
    2. Check each edit block's unique occurrences.
    3. Apply replacements in reverse order so offsets remain stable or perform Line-Preserving overlays.
    """
    content = normalize_to_lf(original_content)
    orig_lines = content.split("\n")
    
    # Process each edit and pre-resolve matches
    replacements = [] # list of (is_fuzzy, start_line, end_line, search_block_len, new_text)
    
    for edit_idx, edit in enumerate(edits):
        old_text = normalize_to_lf(edit.get("oldText", ""))
        new_text = normalize_to_lf(edit.get("newText", ""))
        
        if not old_text:
            raise ValueError(f"edits[{edit_idx}].oldText must not be empty in {path}.")
            
        # Try Exact Match on LF first
        idx_exact = content.find(old_text)
        if idx_exact != -1:
            # Check uniqueness
            occ = content.count(old_text)
            if occ > 1:
                raise ValueError(f"Found {occ} occurrences of edits[{edit_idx}] in {path}. Each oldText must be unique. Please provide more context to make it unique.")
                
            # Maps to lines
            offsets = get_line_offsets(content)
            s_line, e_line = find_target_line_range(offsets, idx_exact, idx_exact + len(old_text))
            replacements.append((False, s_line, e_line, len(old_text), new_text, idx_exact))
        else:
            # Try Fuzzy Match fallbacks
            fuzzy_content = normalize_for_fuzzy_match(content)
            fuzzy_old = normalize_for_fuzzy_match(old_text)
            
            idx_fuzzy = fuzzy_content.find(fuzzy_old)
            if idx_fuzzy == -1:
                raise ValueError(f"Could not find edits[{edit_idx}] in {path}. The oldText must match exactly including all whitespace and newlines.")
                
            occ_fuzzy = fuzzy_content.count(fuzzy_old)
            if occ_fuzzy > 1:
                raise ValueError(f"Found {occ_fuzzy} fuzzy occurrences of edits[{edit_idx}] in {path}. Each oldText must be unique. Please provide more context to make it unique.")
                
            # Maps to lines in fuzzy space
            fuzzy_offsets = get_line_offsets(fuzzy_content)
            s_line, e_line = find_target_line_range(fuzzy_offsets, idx_fuzzy, idx_fuzzy + len(fuzzy_old))
            replacements.append((True, s_line, e_line, len(fuzzy_old), new_text, idx_fuzzy))

    # Apply replacements from newest to oldest / reverse line index to keep line swaps stable
    sorted_replacements = sorted(replacements, key=lambda x: x[1], reverse=True)
    
    for fuzzy, s_line, e_line, _, new_text, _ in sorted_replacements:
        # Replaces lines [s_line, e_line] with the target new text block
        # Wide replacement bounds: keep unchanged lines intact
        prefix = orig_lines[:s_line]
        suffix = orig_lines[e_line + 1:]
        
        # Split new_text into lines
        new_lines = new_text.split("\n")
        orig_lines = prefix + new_lines + suffix
        
    return "\n".join(orig_lines)

def edit_file(path: str, edits: List[Dict[str, str]], cwd: str = ".") -> str:
    """
    Apply precise line edits to a file.
    """
    abs_path = Path(cwd).resolve() / path
    if not abs_path.exists():
        return f"Error: File '{path}' does not exist."
        
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            original_content = f.read()
            
        # Keep track of BOM and line endings
        has_bom = original_content.startswith("\uFEFF")
        if has_bom:
            original_content = original_content[1:]
            
        line_ending = detect_line_ending(original_content)
        
        # Apply edits
        modified_content = apply_text_edit(original_content, edits, path)
        
        if modified_content == original_content:
            return f"Error: No changes made to {path}. The replacements produced identical content."
            
        # Restore line endings and BOM
        if line_ending == "\r\n":
            modified_content = modified_content.replace("\n", "\r\n")
            
        if has_bom:
            modified_content = "\uFEFF" + modified_content
            
        # Write back changes
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(modified_content)
            
        return f"Successfully applied {len(edits)} edits to '{path}'."
    except Exception as e:
        return f"Error editing file '{path}': {str(e)}"
