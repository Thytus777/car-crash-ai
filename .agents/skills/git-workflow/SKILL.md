---
name: git-workflow
description: "Git branching model, commit conventions, and workflow rules. Use when creating branches, committing, or merging."
---

# Git Workflow for Car Crash AI

## Branching Model — Git Flow

- `main` — Production-ready code only. Never commit directly.
- `develop` — Integration branch. All feature branches merge here.
- `feature/*` — Individual features, branched from `develop`.

## Branch Naming

Format: `feature/<short-description>`

Examples:
- `feature/swift-project-scaffold`
- `feature/ai-service-layer`
- `feature/swiftui-views`
- `feature/damage-detection`
- `feature/cost-estimation`

## Commit Messages — Conventional Commits

Format: `type: short description`

Types:
- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation changes
- `test:` — Adding or updating tests
- `refactor:` — Code change that neither fixes a bug nor adds a feature
- `chore:` — Build process, dependencies, tooling
- `style:` — Formatting, missing semicolons (no code change)

Examples:
```
feat: add AIService with Gemini provider
feat: implement damage detection service
fix: handle empty AI response in vehicle ID
docs: update TECHSTACK.md for Swift/iOS
test: add VehicleIDService unit tests
chore: add GoogleGenerativeAI SPM dependency
```

## Workflow Rules

1. **Always branch from `develop`**: `git checkout develop && git checkout -b feature/my-feature`
2. **Never commit to `main` directly** — main is for production releases only
3. **Stage only related files**: Never use `git add -A` or `git add .`
4. **Always ask user before git operations** (commit, push, merge, branch creation)
5. **Merge back to `develop`** only when the user confirms the feature is complete
6. **Keep commits atomic** — one logical change per commit
7. **Push before ending a session** — work is not complete until `git push` succeeds

## Pre-Commit Checklist

Before committing:
- [ ] Code compiles (if on Mac with Xcode)
- [ ] Tests pass (if on Mac with Xcode)
- [ ] No API keys or secrets in committed files
- [ ] Only task-related files are staged
- [ ] Commit message follows conventional format
