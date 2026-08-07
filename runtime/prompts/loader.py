from __future__ import annotations

from functools import lru_cache
from pathlib import Path


class PromptLoader:
    """
    Loads prompt templates from disk.

    Prompt templates are treated as application assets.
    The loader is the only component allowed to access
    the filesystem for prompt loading.
    """

    def __init__(self) -> None:
        self._template_dir = (
            Path(__file__).parent / "templates"
        )

    @lru_cache(maxsize=64)
    def load(self, name: str) -> str:
        """
        Load a prompt template by filename.

        Example:
            load("planner.md")
        """

        path = self._template_dir / name

        if not path.exists():
            raise FileNotFoundError(
                f"Prompt template '{name}' not found."
            )

        return path.read_text(
            encoding="utf-8"
        )