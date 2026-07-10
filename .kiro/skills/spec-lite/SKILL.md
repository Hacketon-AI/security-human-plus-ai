---
name: spec-lite
description: Use this when creating Kiro specs, requirements, design, tasks, implementation plans, bugfix specs, or plan-first workflows with minimal token usage.
---

# Spec Lite Workflow

Create the smallest useful spec.

Rules:
- Do not scan the entire repository.
- Ask for or use only relevant files/folders.
- Keep requirements short.
- Keep design short.
- Keep tasks actionable.
- Do not include long explanations.
- Do not include full code unless implementation starts.
- Do not create broad architecture unless explicitly requested.

Requirements format:
- Max 5 requirements.
- Each requirement must be useful for implementation.
- Avoid obvious requirements.

Design format:
- Summary
- Affected files
- Data/API changes
- UI/behavior changes
- Risk/edge cases

Tasks format:
- Max 6 tasks.
- Each task should touch minimal files.
- Tasks must be sequential unless clearly independent.

Before coding:
- Wait for task approval.
- Implement one task at a time.
- Read only files needed for the selected task.