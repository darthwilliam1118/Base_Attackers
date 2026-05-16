"""LevelFactory — maps level number to BaseLevel instance."""

from __future__ import annotations

from typing import Any
from agf.levels.base_level import BaseLevel


def create_level(
    level_number: int,
    config: Any,
    window_width: int,
    window_height: int,
    snapshot: dict | None = None,
) -> BaseLevel:
    """Create or restore a level.

    Replace the placeholder case with your game's level types.
    """
    if snapshot is not None:
        return _restore(snapshot, config, window_width, window_height)
    return _create_fresh(level_number, config, window_width, window_height)


def _create_fresh(
    level_number: int, config: Any, window_width: int, window_height: int
) -> BaseLevel:
    from src.base_attackers.levels.placeholder_level import (
        PlaceholderLevel,
    )

    # TODO: replace with real level types
    # e.g. if level_number % 5 == 0: return BossLevel(...)
    level = PlaceholderLevel(window_width, window_height)
    level.setup(level_number)
    return level


def _restore(
    snapshot: dict, config: Any, window_width: int, window_height: int
) -> BaseLevel:
    from src.base_attackers.levels.placeholder_level import (
        PlaceholderLevel,
    )

    level_type = snapshot.get("level_type", "placeholder")
    match level_type:
        case "placeholder":
            return PlaceholderLevel.from_snapshot(
                snapshot, config, window_width, window_height
            )
        case _:
            raise ValueError(f"Unknown level type: {level_type!r}")
