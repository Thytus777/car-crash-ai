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

Use the ECC skills installed at `~/.claude/skills/ecc/` for the task types below. Invoke a skill when the work clearly falls into its domain — don't invoke speculatively.

| Task | Skill(s) to invoke |
|------|-------------------|
| Writing or refactoring FastAPI routes, services, models | `backend-patterns`, `coding-standards` |
| Designing new API endpoints or reviewing existing ones | `api-design` |
| Writing or expanding the test suite | `e2e-testing` |
| Docker, containerization, or compose changes | `docker-patterns` |
| Deployment config, CI/CD, Railway/ECS/Fly setup | `deployment-patterns` |
| Changes to the LLM call pipeline (`core/llm.py`, prompts) | `cost-aware-llm-pipeline`, `cost-tracking` |
| Adding PostgreSQL, SQLAlchemy, or schema migrations | `database-migrations` |
| Web scraping pipeline (`price_search.py`, trafilatura) | `data-scraper-agent` |
| Research tasks (market research, API comparison, pricing) | `deep-research` |
| Security audit or adding auth/rate-limiting | invoke `/security-review` |

### How to invoke a skill

At the top of your response when working in a skill domain, state:
> "Invoking skill: `<skill-name>`"

Then follow the guidance from that skill's `SKILL.md` for the duration of that task.

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
