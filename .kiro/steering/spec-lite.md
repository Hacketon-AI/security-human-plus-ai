# Spec Lite Rules

When creating specs, prioritize minimal planning and token efficiency.

Requirements:
- Maximum 5 requirements.
- Use concise EARS-style acceptance criteria only when needed.
- Avoid duplicate or obvious requirements.
- Do not document unrelated flows.

Design:
- Maximum 1 page.
- Mention only affected modules, files, APIs, schemas, or components.
- Avoid broad architecture explanations.
- Do not include full code blocks.
- Do not analyze unrelated folders.

Tasks:
- Maximum 6 tasks.
- Each task must be directly implementable.
- Prefer small, safe changes.
- Avoid broad refactors.
- Do not create tasks for optional improvements unless requested.

Implementation:
- Read only files required by the approved task.
- Do not scan the whole repository.
- Do not open node_modules, build output, dist, .next, coverage, logs, or generated files.
- Edit only files listed in the task unless required.
- If more files are needed, explain why first.

Response:
- Keep explanations short.
- Show only changed files and commands to test.