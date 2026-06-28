# Pocket-Pi Internal Developer Documentation Index

This directory contains the authoritative technical documentation for the **Pocket-Pi** agentic framework. It is packaged and shipped with the agent to enable both developers and LLM coding assistants to fully understand its architecture, permission models, logging behaviors, and extensibility interfaces.

## 🧭 Documentation Map

| Document | Purpose / Target Coverage |
|:---|:---|
| [**Architecture & State-Machine**](architecture.md) | High-level orchestration, `pocketflow` nodes, prompt loops, and wiring topology. |
| [**Permissions & Security Boundaries**](permissions.md) | The CWD Trust system, `trust.json`, safe tools, default execution boundaries, and sandbox safety. |
| [**Logging & Session Storage**](logging.md) | Tree-based JSONL session entries, branch tracking, debug logs, and tool execution logs. |
| [**Skills & Extensions**](skills.md) | Loading custom skill descriptions, local skill folders, and customizing the agent. |

---

## ⚡ Quick Architecture Overview
Pocket-Pi is built as a highly deterministic **state-machine** using the declarative **PocketFlow** framework. Every turn begins at `ConsoleInputNode`, routes via a central planner/router, coordinates tool dispatches asynchronously, and safely rolls up outcomes to the loop state.
