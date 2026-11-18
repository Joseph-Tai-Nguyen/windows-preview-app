---
description: Lint, format-check and test the project; fix anything that fails
---

Run the project's quality gate from the repo root:

1. `.venv/Scripts/ruff check src tests`
2. `.venv/Scripts/ruff format --check src tests`
3. `.venv/Scripts/python -m pytest -q`

If something fails, fix the cause. Run `ruff format` for formatting-only failures. Never weaken or skip a test to make it pass. Re-run until everything is green, then give a one-line summary of the results. $ARGUMENTS
