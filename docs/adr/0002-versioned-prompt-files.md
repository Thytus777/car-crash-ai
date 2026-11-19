# 0002. Keep prompts in immutable, versioned template files

- **Status:** Accepted
- **Date:** 2026-11-19
- **Issue:** #25

## Context

Prompts lived as Python string constants across five modules. Nothing recorded which prompt text produced a given result, so an eval run, a bug report and a cost figure couldn't be tied back to a prompt. The move also surfaced a bug the code structure had hidden: the vehicle-ID prompt was written with `str.format()` escapes but sent unformatted, so the model saw doubled braces.

## Decision

- Each prompt is a file, `backend/prompts/<version>/<name>.md`, rendered with `string.Template` (`${var}`, literal `$$`). `_<partial>.md` files hold fragments shared between prompts.
- `settings.prompt_version` selects the directory. The app checks at startup that every prompt exists.
- **Versions are immutable.** To change any prompt, copy the directory to a new version and edit there. Old versions stay so evals can compare them.
- Every `/analyze` response and stored estimate carries `meta.prompt_version`, plus the models and token counts used.
- Golden renders in `tests/golden/prompts/` pin `v1` byte for byte. A test asserts exactly which files differ between consecutive versions.

## Alternatives considered

- **Jinja2 templates.** Jinja is already a dependency (PDF reports), but prompts need only substitution. `string.Template` has no logic to drift into, and its `$` syntax leaves JSON braces alone.
- **Edit prompts in place and rely on git history.** That's cheaper on files, but a running service and its eval results couldn't say which text they used. Comparing two versions would mean checking out two commits.
- **A prompt-management service (e.g. Langfuse prompts).** Revisit with observability in Phase 4. Files in the repo keep prompts reviewable in PRs and work offline in tests.

## Consequences

- Prompt changes show up in PRs as new files, with a clear diff against the previous version.
- The eval harness can run any version by name and attribute regressions to it.
- Unchanged prompts are duplicated across versions. That's acceptable: they're small text files, and immutability is the point.
