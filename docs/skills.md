# Skills & Extensions

Pocket-Pi supports a lightweight, highly decoupled extension format known as **Skills**. Skills let you inject specialized system prompts, guidelines, and behavioral models into the LLM conversation context on the fly.

---

## 📂 Physical Directory Layout
Skills are packaged as specialized directories with custom documentation. When starting, the agent scans two primary locations relative to the workspace:

1.  **`.pocket_pi/skills/`** (Project-specific skills)
2.  **`.agents/skills/`** (Shared workspace/team skills)

Each skill inside these folders represents its own isolated directory named after the skill, containing a **`SKILL.md`** file:

```text
.pocket_pi/
└── skills/
    ├── custom-refactoring/
    │   └── SKILL.md
    └── cloud-deployment/
        └── SKILL.md
```

---

## ⚙️ Loading and Injecting Skills in Conversations

Skills are loaded using the direct slash command **`/skills:<skill_name>`** or **`/skill:<skill_name>`** (e.g., `/skills:grill-me`).

### ⚡ Ergonomic Tab Completion
When entering `/` inside the terminal, pocket-pi displays the list of all available commands *automatically*. You can use the **Up/Down arrow keys** to navigate and find `/skills:`, then hit **Tab** to select/complete it.

Once selected, the input becomes `/skills:` and instantly displays all locally available skill options in the dropdown. Simply navigate to the desired skill with **arrow keys**, hit **Tab** to select it, and you can immediately continue typing parameters or prompt details on the same line (separating arguments with a space) before hitting **Enter** to submit!

### 1. Verification & Matching
When a skill command is inputted:
1.  The `ConsoleInputNode` checks whether `<skill_name>` exists in the matched scan folders.
2.  If the skill directory is not found, the agent displays a list of detected local skills or guidance on how to initialize one.
3.  If found, the content of `SKILL.md` is loaded.

### 2. Context Prompt Injection
Once loaded, the content of the skill's `SKILL.md` is appended to the active session history as a **`system`** message:

```json
{
  "role": "system",
  "content": "Loaded skill instructions: [SKILL_NAME]\n---\n[SKILL.MD CONTENT]"
}
```

This immediately teaches the active LLM session the conventions, guidelines, and specialized templates outlined in the skill file, and advises it how to act for subsequent queries.

---

## 🎨 Creating a New Skill

Creating a skill is as simple as creating a folder and matching markdowns. 

To build a custom skill:
1.  Create a directory inside `.pocket_pi/skills/` (for example, `.pocket_pi/skills/react-expert/`).
2.  Create a file named `SKILL.md` inside that folder.
3.  Add explicit instructions, constraints, and templates:

```markdown
# React Expert Skill

You are a senior frontend engineer specializing in React, Next.js, and TypeScript.

## Rules
- Always use functional components with hooks.
- Favor Tailwind CSS utility classes.
- Ensure strict type-safety with zero 'any' assertions.
```

Once saved, the skill will instantly appear in the `/skills` auto-completer when you type `/` or `/skills`, and can be loaded dynamically into any active chat session!
