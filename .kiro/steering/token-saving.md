# Token Saving Rules

Use minimal context and avoid scanning the whole repository unless explicitly requested.

Before editing:
- Identify only the relevant files.
- Read only files needed for the task.
- Do not open build outputs, logs, generated files, node_modules, dist, .next, coverage, or lock files unless required.

Response style:
- Keep explanations concise.
- Do not repeat large code blocks unless necessary.
- Show only changed snippets or file paths.
- Prefer direct patches over long explanations.
- Ask before doing broad refactors.

Implementation rules:
- Make the smallest safe change.
- Do not rewrite unrelated files.
- Do not run expensive analysis across the whole codebase unless requested.
- When debugging, inspect error logs and directly related source files first.

For TypeScript/React projects:
- Prioritize files imported by the failing component/page.
- Avoid reading unrelated routes, pages, or components.
- Preserve existing architecture and style.