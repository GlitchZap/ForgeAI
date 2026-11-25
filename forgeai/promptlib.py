"""Prompt templates live in forgeai/prompts/*.md (committed, reviewable). `$var` placeholders, no logic."""
from __future__ import annotations

from functools import cache
from pathlib import Path
from string import Template

_DIR = Path(__file__).parent / "prompts"


@cache
def _load(name: str) -> Template:
    return Template((_DIR / f"{name}.md").read_text(encoding="utf-8"))


def P(name: str, **vars) -> list[dict]:
    """Render a template as a single user message. Missing vars raise, so a typo can't ship a half-empty prompt."""
    return [{"role": "user", "content": _load(name).substitute(**{k: str(v) for k, v in vars.items()})}]
