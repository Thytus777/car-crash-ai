"""Versioned prompt templates.

Prompt text lives in ``backend/prompts/<version>/<name>.md``, rendered with
``string.Template`` (``${placeholder}``; a literal dollar is ``$$``). Files
named ``_<partial>.md`` are shared fragments, inserted verbatim wherever a
template references ``${partial}``.

``settings.prompt_version`` selects the directory, and every response records
it, so an eval result or a bug report can be tied to the exact prompt text.
Changing a prompt means a new version directory, not editing one in place.
"""

from functools import cache
from pathlib import Path
from string import Template
from typing import Literal, get_args

from app.core.config import settings

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"

PromptName = Literal[
    "vehicle_identification",
    "damage_zone",
    "damage_full",
    "price_extraction",
    "price_estimation",
    "sanity_check",
]
PROMPT_NAMES: tuple[PromptName, ...] = get_args(PromptName)


@cache
def _load(version: str) -> tuple[dict[PromptName, Template], dict[str, str]]:
    directory = PROMPTS_ROOT / version
    if not directory.is_dir():
        raise RuntimeError(f"Prompt version {version!r} not found in {PROMPTS_ROOT}")

    def read(path: Path) -> str:
        return path.read_text(encoding="utf-8").rstrip("\n")

    partials = {p.stem.removeprefix("_"): read(p) for p in directory.glob("_*.md")}
    templates = {
        name: Template(read(directory / f"{name}.md")) for name in PROMPT_NAMES
    }
    return templates, partials


def render(name: PromptName, version: str | None = None, **values: object) -> str:
    """Render a prompt (default: configured version). Missing values: KeyError."""
    templates, partials = _load(version or settings.prompt_version)
    return templates[name].substitute(partials, **values)


def validate_prompts() -> None:
    """Fail fast at startup if the configured prompt version is incomplete."""
    _load(settings.prompt_version)
