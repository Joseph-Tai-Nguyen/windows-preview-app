# GEMINI.md

The shared agent instructions live in AGENTS.md and are imported here, so they never drift apart:

@./AGENTS.md

## Gemini CLI specifics

- This is Windows. Run the helpers with `pwsh -File scripts/check.ps1` (or `powershell -File ...`) and always use `.venv\Scripts\python`.
- Run `scripts/check.ps1` before reporting a task complete.
- Project settings are in `.gemini/settings.json`. Keep secrets in `.gemini/.env` (git-ignored).
