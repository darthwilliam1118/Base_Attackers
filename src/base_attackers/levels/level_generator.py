"""LevelGenerator — procedural placement of terrain-mounted objects.

Produces a ``LevelLayout`` (tower / silo / turret / laser X-positions and
surfaces) for a level from the difficulty curve and ``[level_gen]`` config.
Pure Python — no arcade, constructible and testable without a display.

Determinism: ``generate`` seeds ``random.Random(run_seed if run_seed is
not None else level_num)``.  RunLevelView passes a per-game-derived seed
(see ``derive_seed``) so a level looks identical across a respawn but
differs between games; passing ``run_seed=None`` falls back to a
level-number seed (handy for tests / reproducible debugging).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.base_attackers.game_config import GameConfig


def difficulty(level: int, max_level: int = 10) -> float:
    """Returns 0.0 at level 1, 1.0 at level ``max_level`` and beyond."""
    return min(1.0, (level - 1) / max(1, max_level - 1))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def derive_seed(run_seed: int, level_num: int) -> int:
    """Combine the per-game seed and level number into a stable seed.

    Pure function of its inputs, so the same (run_seed, level_num) always
    yields the same level — the basis for identical respawns.
    """
    return (run_seed * 1_000_003 + level_num) & 0x7FFFFFFF


@dataclass
class TowerPlacement:
    x: float
    surface: str  # "floor" or "ceiling"


@dataclass
class SiloPlacement:
    x: float
    surface: str


@dataclass
class TurretPlacement:
    x: float
    surface: str


@dataclass
class LaserPlacement:
    x: float
    surface: str


@dataclass
class LevelLayout:
    """Complete procedural layout for one level."""

    level_num: int
    towers: list[TowerPlacement]
    silos: list[SiloPlacement]
    turrets: list[TurretPlacement]
    lasers: list[LaserPlacement]
    boss_zone_x: float  # world X where the boss zone begins
    entry_clear_x: float  # world X where the entry clear zone ends


class LevelGenerator:
    """Generates a complete procedural level layout from difficulty params."""

    def __init__(self, cfg: "GameConfig") -> None:
        self._cfg = cfg
        self._gen_cfg = cfg.level_gen

    def generate(
        self,
        level_num: int,
        world_width: float,
        ceiling_present: bool,
        run_seed: int | None = None,
    ) -> LevelLayout:
        rng = random.Random(run_seed if run_seed is not None else level_num)

        gc = self._gen_cfg
        d = difficulty(level_num, gc.max_difficulty_level)

        boss_zone_x = world_width * gc.boss_zone_fraction
        entry_clear_x = world_width * gc.entry_clear_fraction
        playfield_w = boss_zone_x - entry_clear_x

        towers = self._place_towers(
            rng, d, entry_clear_x, boss_zone_x, ceiling_present, level_num
        )
        # Enemies must clear towers as well as their own kind, so seed each
        # enemy pass with the tower X positions.
        tower_x = [t.x for t in towers]

        silos = self._place_enemies(
            rng,
            d,
            entry_clear_x,
            boss_zone_x,
            playfield_w,
            gc.silo_density_min,
            gc.silo_density_max,
            gc.silo_min_spacing,
            gc.silo_ceiling_fraction_min,
            gc.silo_ceiling_fraction_max,
            ceiling_present,
            gc.silo_unlock_level,
            level_num,
            SiloPlacement,
            tower_x,
        )
        turrets = self._place_enemies(
            rng,
            d,
            entry_clear_x,
            boss_zone_x,
            playfield_w,
            gc.turret_density_min,
            gc.turret_density_max,
            gc.turret_min_spacing,
            gc.turret_ceiling_fraction_min,
            gc.turret_ceiling_fraction_max,
            ceiling_present,
            gc.turret_unlock_level,
            level_num,
            TurretPlacement,
            tower_x,
        )
        lasers = self._place_enemies(
            rng,
            d,
            entry_clear_x,
            boss_zone_x,
            playfield_w,
            gc.laser_density_min,
            gc.laser_density_max,
            gc.laser_min_spacing,
            gc.laser_ceiling_fraction_min,
            gc.laser_ceiling_fraction_max,
            ceiling_present,
            gc.laser_unlock_level,
            level_num,
            LaserPlacement,
            tower_x,
        )

        return LevelLayout(
            level_num=level_num,
            towers=towers,
            silos=silos,
            turrets=turrets,
            lasers=lasers,
            boss_zone_x=boss_zone_x,
            entry_clear_x=entry_clear_x,
        )

    # ---- placement helpers -----------------------------------------

    def _place_towers(
        self,
        rng: random.Random,
        d: float,
        x_min: float,
        x_max: float,
        ceiling_present: bool,
        level_num: int,
    ) -> list[TowerPlacement]:
        gc = self._gen_cfg
        count = round(lerp(gc.tower_count_max, gc.tower_count_min, d))
        count = max(1, count)  # always at least one tower
        towers: list[TowerPlacement] = []
        used_x: list[float] = []
        for _ in range(count * 10):  # retry loop
            if len(towers) >= count:
                break
            x = rng.uniform(x_min, x_max)
            if not self._clear_of(x, used_x, gc.tower_min_spacing):
                continue
            can_ceil = ceiling_present and level_num >= gc.tower_ceiling_unlock_level
            surface = "ceiling" if (can_ceil and rng.random() < 0.3) else "floor"
            towers.append(TowerPlacement(x=x, surface=surface))
            used_x.append(x)
        return towers

    def _place_enemies(
        self,
        rng: random.Random,
        d: float,
        x_min: float,
        x_max: float,
        playfield_w: float,
        density_min: float,
        density_max: float,
        min_spacing: float,
        ceil_frac_min: float,
        ceil_frac_max: float,
        ceiling_present: bool,
        unlock_level: int,
        level_num: int,
        placement_cls: type,
        exclude_x: list[float],
    ) -> list:
        if level_num < unlock_level:
            return []
        density = lerp(density_min, density_max, d)
        count = max(0, round(density * playfield_w))
        ceil_frac = lerp(ceil_frac_min, ceil_frac_max, d) if ceiling_present else 0.0
        placed: list = []
        # Start the exclusion set with towers (and grows with placed enemies)
        # so nothing sits within min_spacing of a tower or another enemy.
        used_x: list[float] = list(exclude_x)
        for _ in range(count * 10):
            if len(placed) >= count:
                break
            x = rng.uniform(x_min, x_max)
            if not self._clear_of(x, used_x, min_spacing):
                continue
            surface = (
                "ceiling" if (ceiling_present and rng.random() < ceil_frac) else "floor"
            )
            placed.append(placement_cls(x=x, surface=surface))
            used_x.append(x)
        return placed

    @staticmethod
    def _clear_of(x: float, used: list[float], spacing: float) -> bool:
        return all(abs(x - ux) >= spacing for ux in used)
