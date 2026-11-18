# CLAUDE.md

The shared agent instructions live in AGENTS.md and are imported here, so they never drift apart:

@AGENTS.md

## Claude Code specifics

- Shell: this is Windows. Prefer the PowerShell tool for the `scripts/*.ps1` helpers. In Git Bash use forward slashes: `.venv/Scripts/python -m pytest`.
- `/check` (in `.claude/commands/check.md`) runs lint, the format check and the tests. Run it before saying a task is done.
- `.claude/settings.json` pre-approves the routine test and lint commands. Personal overrides go in `.claude/settings.local.json` (git-ignored).
- To *see* a UI change, render the window offscreen and grab it instead of launching a visible window:
  `QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=C:/Windows/Fonts`, build a `MainWindow`, call `open_file(...)`, then `window.grab().save("shot.png")`. Write the throwaway script in your scratchpad, not in the repo.
- For a multi-step feature, check `docs/REQUIREMENTS.md` for the requirement ID and update its status when you finish.
