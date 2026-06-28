# Module 4: Unified File, Bash & Search Tools

This module details how pocket-pi implements its standard tool-set, explaining how we build safe, bounded, and highly resilient system wrappers, with a deep dive into our fuzzy-matching file editing algorithm.

---

## 🧭 Bounded File Operations (`read` & `write`)

When giving file tools to LLMs, we must prevent them from downloading giant files completely into memory at once, which could instantly exhaust context windows.

Our **`read_file`** tool supports **Line Slicing** via offsets and limits:

```python
def read_file(path: str, offset: int = 1, limit: int = 2000, cwd: str = ".") -> str:
    abs_path = Path(cwd).resolve() / path
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        start_idx = max(0, offset - 1)
        end_idx = min(total_lines, start_idx + limit)
        slice_lines = lines[start_idx:end_idx]
        
        # Build clean indicators showing exactly what part was read
        header = f"--- [File: {path} | Lines {start_idx + 1}-{end_idx} of {total_lines}] ---\n"
        footer = f"\n--- [Remaining Lines: {max(0, total_lines - end_idx)}] ---"
        
        return header + "".join(slice_lines) + footer
```

Writing files via **`write_file`** is simple but incorporates safe parent directory creations:
```python
def write_file(path: str, content: str, cwd: str = ".") -> str:
    abs_path = Path(cwd).resolve() / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
```

---

## 💻 Process Execution with Limits (`bash`)

Our `bash` execution tool invokes system sub-shells, captures combined `stdout`/`stderr` outputs, and enforces safety truncation ceilings. If output exceeds 2,000 lines or 50KB, it truncates the payload and saves the full log privately to a temp file, ensuring terminal buffer safety:

```python
def execute_bash(command: str, timeout: int = None, cwd: str = ".") -> str:
    cwd_path = str(Path(cwd).resolve())
    process = subprocess.Popen(
        command, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=cwd_path, env=os.environ, text=True, errors="replace"
    )
    stdout, _ = process.communicate(timeout=timeout)
    exit_code = process.returncode
    
    lines = stdout.splitlines()
    if len(lines) > 2000:
        # Save full result to debug log for future reference
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as temp:
            temp.write(stdout)
            temp_path = temp.name
            
        return f"--- [Output Truncated (Exit Code: {exit_code}) | Full saved to: {temp_path}] ---\n" + "\n".join(lines[-2000:])
```

---

## 🌎 Web Search via Tavily REST API

To enrich the agent with real-time news and fact searches, pocket-pi includes standard **`web_search`** via the Tavily web endpoint:

```python
def web_search(query: str) -> str:
    api_key = os.environ.get("TAVILY_API_KEY")
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": 5
    }
    response = requests.post(url, json=payload, timeout=15)
    results = response.json().get("results", [])
    
    output = [f"--- [Tavily Web Search Results for: {query}] ---"]
    for idx, item in enumerate(results):
        output.append(f"[{idx + 1}] {item['title']}\nURL: {item['url']}\nSnippet: {item['content']}\n")
    return "\n".join(output)
```

In the tool's JSON Schema, we tell the model: **“ALWAYS perform a broad, general query first instead of multiple narrow searches”**. This keeps searches exceptionally performant and broad-first!

---

## 🎨 The Masterpiece: Fuzzy-Matching `edit` Tool

Updating code using search-and-replace often fails because of tiny spacing differences, unicode quotes, or carriage return line-ending mismatches. Pocket-pi ports **pi's exact matching engine** in three brilliant steps:

### Step 1: Normalization
We normalize all file contents and replacement blocks to LF endings (`\n`) and strip Unicode byte-order-marks (BOM `\uFEFF`). 

If exact matching fails, we run progressive fuzzy normalizations on both strings using `normalize_for_fuzzy_match`:
1.  NFKC Unicode normalization.
2.  Trimming trailing whitespaces from individual lines.
3.  Mapping smart quotes (`‘`, `’`) to ASCII (`'`).
4.  Mapping Unicode dashes/hyphens (`—`, `–`) to ASCII hyphen (`-`).
5.  Mapping special spaces (NBSP, em-spaces) to standard spaces (` `).

```python
def normalize_for_fuzzy_match(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    trimmed_lines = [line.rstrip() for line in normalized.split("\n")]
    normalized = "\n".join(trimmed_lines)
    # Perform quotes, dashes, and spaces translations...
    return normalized
```

### Step 2: Line Span Mapping
If we had to fallback to fuzzy search, we locate the match index in fuzzy-normalized space. How do we transpose this back to line modifications in our original, untouched code?

We calculate character offset zones for each line:
```python
def get_line_offsets(content: str) -> List[Tuple[int, int]]:
    lines = content.split("\n")
    offsets = []
    current = 0
    for line in lines:
        start = current
        end = current + len(line)
        offsets.append((start, end))
        current = end + 1 # +1 for newline character
    return offsets
```
We can translate char offsets bounds in fuzzy space back to a distinct **Line Range `[start_line, end_line]`**!

### Step 3: Reverse Substitutions
We apply multiple edits in **reverse line-index order** (from bottom of the file to the top). 

Why? Because replacing lines can expand or compress the line numbers. If we went forward, replacing lines at the top would shift the line numbers for all remaining edits at the bottom, breaking subsequent offsets! Going backward guarantees that all preceding edit ranges remain 100% stable throughout:

```python
    # Apply replacements from bottom to top
    sorted_replacements = sorted(replacements, key=lambda x: x[1], reverse=True)
    for fuzzy, s_line, e_line, _, new_text, _ in sorted_replacements:
        prefix = orig_lines[:s_line]
        suffix = orig_lines[e_line + 1:]
        orig_lines = prefix + new_text.split("\n") + suffix
```
This is an incredibly robust line-preserving overlay that preserves ALL original, untouched carriage margins (indentations, trailing spaces, CRLF line-endings) elsewhere in your files perfectly!

---

## 👩‍💻 Exercises for Students

1.  **Strict edit uniqueness**: Verify why we count occurrences of `oldText` in `edit.py`. What error should we raise if a keyword block contains duplicate matches?
2.  **Mime-Type Classifier**: Extend `read_file` so that if a file suffix is `.png` or `.jpg`, instead of reading raw binary bytes, it returns a text description summarizing the image properties.

---

Next, study how we build interactive nodes and contextual pruners in **[Module 5: Workflow Nodes & Context Pruners](05_agent_nodes_orchestration.md)**! 🧠
