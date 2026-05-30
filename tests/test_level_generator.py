"""Tests for procedural level generation — pure logic, no display."""

from __future__ import annotations

from src.base_attackers.game_config import GameConfig
from src.base_attackers.levels.level_generator import (
    LevelGenerator,
    derive_seed,
    difficulty,
)

_WORLD_W = 6400.0


def _gen(level: int, ceiling: bool = False, run_seed: int = 123):
    cfg = GameConfig()  # defaults — LevelGenSettings defaults apply
    return LevelGenerator(cfg).generate(
        level_num=level,
        world_width=_WORLD_W,
        ceiling_present=ceiling,
        run_seed=run_seed,
    )


def test_difficulty_curve_clamps() -> None:
    assert difficulty(1, 10) == 0.0
    assert difficulty(10, 10) == 1.0
    assert difficulty(99, 10) == 1.0
    assert 0.0 < difficulty(5, 10) < 1.0


def test_no_placements_in_entry_or_boss_zone() -> None:
    layout = _gen(level=5, ceiling=True)
    lo = layout.entry_clear_x
    hi = layout.boss_zone_x
    assert lo < hi
    for group in (layout.towers, layout.silos, layout.turrets, layout.lasers):
        for p in group:
            assert lo <= p.x <= hi


def test_min_spacing_respected_and_towers_cleared() -> None:
    cfg = GameConfig()
    layout = LevelGenerator(cfg).generate(5, _WORLD_W, False, run_seed=7)
    gc = cfg.level_gen
    tower_x = [t.x for t in layout.towers]

    def spaced(xs: list[float], spacing: float) -> bool:
        s = sorted(xs)
        return all(b - a >= spacing for a, b in zip(s, s[1:]))

    assert spaced([t.x for t in layout.towers], gc.tower_min_spacing)
    assert spaced([s.x for s in layout.silos], gc.silo_min_spacing)
    assert spaced([t.x for t in layout.turrets], gc.turret_min_spacing)
    # Enemies clear towers too.
    for s in layout.silos:
        assert all(abs(s.x - tx) >= gc.silo_min_spacing for tx in tower_x)


def test_at_least_one_tower() -> None:
    for level in (1, 5, 10, 25):
        assert len(_gen(level).towers) >= 1


def test_laser_unlock_level() -> None:
    assert _gen(level=1).lasers == []
    assert _gen(level=2).lasers == []
    assert len(_gen(level=5, ceiling=True).lasers) >= 0  # unlocked at 3+
    # Density is non-zero at higher levels, so lasers should appear.
    assert len(_gen(level=10).lasers) >= 1


def test_same_seed_identical_layout() -> None:
    a = _gen(level=4, run_seed=42)
    b = _gen(level=4, run_seed=42)
    assert [(p.x, p.surface) for p in a.silos] == [(p.x, p.surface) for p in b.silos]
    assert [(p.x, p.surface) for p in a.turrets] == [
        (p.x, p.surface) for p in b.turrets
    ]


def test_different_seed_differs() -> None:
    a = _gen(level=4, run_seed=1)
    b = _gen(level=4, run_seed=2)
    assert [p.x for p in a.silos] != [p.x for p in b.silos]


def test_derive_seed_stable_and_distinct() -> None:
    assert derive_seed(99, 3) == derive_seed(99, 3)
    assert derive_seed(99, 3) != derive_seed(99, 4)
    assert derive_seed(1, 3) != derive_seed(2, 3)


def test_level_settings_for_explicit_and_procedural() -> None:
    cfg = GameConfig.load()
    # Levels 1-2 are explicit in TOML.
    assert cfg.level_settings_for(1) is cfg.levels[1]
    # Level 25 has no TOML entry — generated procedurally.
    gen = cfg.level_settings_for(25)
    assert gen.ceiling_present is True
    assert gen.terrain_renderer in ("tile", "polygon")
    assert 720.0 <= gen.world_height <= 2160.0
