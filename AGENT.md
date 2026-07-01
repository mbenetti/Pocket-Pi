# Pocket-Pi Custom Agent Guidelines

Welcome to the Pocket-Pi development workspace! When operating within this project, please adhere to the following architectural guidelines, coding standards, and behavioral instructions.

---

## 🏛️ Architectural Principles

1. **State-Machine Topology (`PocketFlow`)**:
   - Do not write monolithic execution loops. All behaviors must be encapsulated within discrete `Node` classes subclassed from `pocketflow.Node`.
   - Ensure all communication between nodes is routed exclusively through the `shared` state dictionary.

2. **Zero-Contradiction Prompts**:
   - Keep system prompts clean and focused. Do not mix conversational instructions with tool schemas.
   - If tools are disabled, use the simplified conversational system prompt to avoid LLM tool-call bias.

3. **Security Boundaries**:
   - Respect the **Project Trust Boundary** (`trust.json`) and the **Security Gatekeeper** (`permissions.json`).
   - Never bypass human-in-the-loop confirmation prompts for executing arbitrary bash commands or accessing external URLs.
   - Prevent any tool from writing to or modifying files within the `.pocket_pi/` configuration directory.

---

## 💻 Coding Standards

1. **Type Hinting & Documentation**:
   - All new functions and classes must include explicit Python type hints (`typing` module).
   - Write clear, concise docstrings explaining the inputs, outputs, and side-effects of nodes and tools.

2. **TUI Presentation (`rich`)**:
   - Use `rich` console markup for terminal outputs.
   - Follow the established color palette: bold green for successful completions, soft-grey for reasoning logs, and bold yellow/red for warnings and errors.

3. **Fuzzy-Matching Line Editor**:
   - When modifying files, prefer exact search-and-replace blocks to prevent file corruption.
   - Preserve original line endings (CRLF/LF) and indentation patterns.

---

## 💬 Communication Style

- **Conciseness**: Prioritize direct, technical, and actionable guidance over verbose explanations.
- **Transparency**: If an action fails or requires user permission, state the exact reason clearly and offer the best next steps.
