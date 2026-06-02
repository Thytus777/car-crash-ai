# Agent Instructions

This is a **Swift/SwiftUI iOS app** (iOS 17+ / Swift 5.9+). See `.agents/AGENTS.md` for full project instructions, architecture, code conventions, and file structure rules.

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

---

## Git Branching Strategy

**Permanent branches:**
- `main` — production-ready code only. Never commit directly. Merge from `develop` when a release is ready.
- `develop` — integration branch. All feature branches merge here. Always deployable but not necessarily production-ready.

**Feature branches:**
- Branch off `develop`: `git checkout -b feature/<short-name> develop`
- One branch per feature/fix. Keep them small and focused.
- Name format: `feature/<topic>` (e.g. `feature/phase1-database`, `feature/vin-decoder`)
- Merge back to `develop` via PR (or locally) when the feature is complete and tests pass.
- Delete the branch after merging.

**Hotfix branches:**
- Branch off `main`: `git checkout -b hotfix/<description> main`
- Merge into both `main` AND `develop` after fix.

**Commit message format:**
```
<type>: <short description>

Types: feat | fix | refactor | test | docs | chore | perf
Examples:
  feat: add zone-based damage detection prompts
  fix: clamp severity scores from consensus outliers
  docs: update TECHSTACK with database layer
```

**Release flow:**
```
feature/* → develop → (staging test) → main
```

---

## Issue Tracking (beads)

This project uses **bd (beads)** for issue tracking. Install it first:
```bash
pip install beads   # or: check https://github.com/steveyegge/beads for install
bd onboard
```
Until installed, use the Claude Code task list (`TaskCreate`) as a session-local proxy.

---

## Skill Invocation Guide

Two skill libraries are installed. Both should be used **proactively** — read the relevant `SKILL.md` before starting work in that domain, without waiting for the user to ask.

### Skill paths

| Library | Location | What it covers |
|---------|----------|----------------|
| **ECC** | `~/.claude/skills/ecc/<skill-name>/SKILL.md` | Backend, API, DB, Docker, LLM pipelines, testing, deployment |
| **ui-ux-pro-max** | `~/.claude/skills/ui-ux-pro-max/SKILL.md` | All UI/UX work — pages, components, color, typography, accessibility, layout |

### When to invoke (proactively — no user prompt needed)

| Task domain | Skill(s) to read |
|-------------|-----------------|
| Any UI component, page, or design decision (Next.js, Tailwind) | `ui-ux-pro-max` ← **always for frontend work** |
| FastAPI routes, services, Pydantic models | `~/.claude/skills/ecc/backend-patterns/SKILL.md`, `~/.claude/skills/ecc/fastapi-patterns/SKILL.md` |
| API endpoint design or review | `~/.claude/skills/ecc/api-design/SKILL.md` |
| Writing or expanding the test suite | `~/.claude/skills/ecc/e2e-testing/SKILL.md` |
| Docker, containerization, compose changes | `~/.claude/skills/ecc/docker-patterns/SKILL.md` |
| Deployment config, CI/CD, Railway/ECS | `~/.claude/skills/ecc/deployment-patterns/SKILL.md` |
| LLM pipeline (`core/llm.py`, prompts, providers) | `~/.claude/skills/ecc/cost-aware-llm-pipeline/SKILL.md` |
| PostgreSQL, SQLAlchemy, Alembic migrations | `~/.claude/skills/ecc/database-migrations/SKILL.md` |
| Web scraping pipeline (`price_search.py`) | `~/.claude/skills/ecc/data-scraper-agent/SKILL.md` |
| Research tasks (market research, API comparison) | `~/.claude/skills/ecc/deep-research/SKILL.md` |
| Security audit, auth, rate-limiting | `~/.claude/skills/ecc/security-review/SKILL.md` |
| React patterns, hooks, state management | `~/.claude/skills/ecc/react-patterns/SKILL.md` |

### How invocation works

Skills are **not** loaded automatically — they must be explicitly read. Before starting work in a skill domain:

1. Read the `SKILL.md` at the path above using the Read tool
2. Apply its guidance for the duration of the task
3. No user prompt needed — this is self-directed

**ECC rules** (`~/.claude/rules/ecc/`) are different — they ARE loaded automatically every session and apply passively to all code written (immutability, error handling, naming, etc.).

### What "invoking" looks like

When reading a skill, briefly note it so the user knows it's being applied:
> Reading `ui-ux-pro-max` for component design guidance...

Then apply it. Don't skip this for frontend work — the `ui-ux-pro-max` skill enforces anti-template policy, typography, depth, and accessibility standards that prevent generic-looking UI.

---

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds


<!-- BEGIN BEADS INTEGRATION -->
## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Auto-syncs to JSONL for version control
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update bd-42 --status in_progress --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task**: `bd update <id> --status in_progress`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Auto-Sync

bd automatically syncs with git:

- Exports to `.beads/issues.jsonl` after changes (5s debounce)
- Imports from JSONL when newer (e.g., after `git pull`)
- No manual export/import needed!

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems

For more details, see README.md and docs/QUICKSTART.md.

<!-- END BEADS INTEGRATION -->
