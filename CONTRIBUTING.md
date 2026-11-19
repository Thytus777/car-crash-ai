# Contributing

## Setup

You need [uv](https://docs.astral.sh/uv/) and GNU make (on Windows: `winget install ezwinports.make`).

```bash
make setup     # dependencies + pre-commit and commit-msg hooks
make help      # every available target
```

## Workflow

We use trunk-based development. `main` is always deployable, and nobody commits to it directly.

1. **Start from an issue.** Open one, or pick an existing one, so the change has a reason on record.
2. **Branch from the latest `main`** with the name `<type>/<short-description>`, e.g. `feat/eval-harness`, `fix/pricing-timeout`, `chore/ci-setup`.
3. **Commit small and often.** Each commit builds and passes `make test`. Keep refactors and behaviour changes in separate commits.
4. **Open a PR** with `gh pr create` and fill in the template.
5. **Merge once CI is green.** Squash-merge, then delete the branch.

Keep branches short-lived (days, not weeks) and rebase on `main` rather than merging it in.

## Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/). The commit-msg hook enforces this.

```
<type>(<optional scope>): <imperative summary, ≤ 72 chars>

<body: why the change was needed, when it isn't obvious>

<footer: Closes #12, BREAKING CHANGE: ...>
```

| Type | Use for |
|---|---|
| `feat` | New behaviour |
| `fix` | Bug fix (with a regression test that fails first) |
| `refactor` | Code change with no behaviour change |
| `perf` | Performance improvement |
| `test` | Tests only |
| `docs` | Documentation only |
| `ci` | GitHub Actions |
| `build` | Dependencies, packaging, Docker |
| `chore` | Repo maintenance |
| `style` | Formatting only |

Add a `BREAKING CHANGE:` footer whenever the HTTP API contract changes.

## Before you push

```bash
make lint typecheck    # ruff + mypy --strict
make coverage          # unit + integration with the coverage gate
```

The pre-commit hooks also run ruff, mypy, gitleaks and the whitespace and large-file checks on every commit.

## Tests

- `backend/tests/unit/`: fast and deterministic. No network, DB or real LLM.
- `backend/tests/integration/`: the FastAPI app through `httpx.AsyncClient` with fixture LLM responses.
- Every bug fix comes with a regression test that fails before the fix.
- The coverage floor (`COV_MIN` in the `Makefile`) only goes up.

## Pull requests

A PR should do one thing. The template asks for:
- what changed and why
- how it was tested
- eval impact (a before/after table when prompts, models or the pipeline change)
- screenshots for UI changes
- the linked issue

## Design decisions

Record significant decisions as an ADR in `docs/adr/`. Copy `0000-template.md` and take the next number.

## Secrets

Never commit `.env` files, API keys, or model responses that contain personal data. gitleaks runs both in pre-commit and in CI. If a secret does land in a commit, rotate it first, then tell the maintainer; rewriting history needs their sign-off.
