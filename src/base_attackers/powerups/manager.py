"""BAPowerUpManager — Base Attackers power-up effect manager.

Subclasses agf PowerUpManager but **does not** use the agf screen-space
spawner.  Base Attackers spawns pickups in world space via
``WorldSpacePowerUpSpawner`` owned by ``RunLevelView``; this class only
tracks active effects and creates concrete effect instances per type.

The agf base ``__init__`` insists on a ``PowerUpConfigBase`` and builds
a ``PowerUpSpawner`` from it.  We pass a default config and ignore the
spawner — our overridden ``update()`` never calls it.
"""

from __future__ import annotations

from typing import Any

from agf.powerups.config import PowerUpConfigBase
from agf.powerups.effect_base import PowerUpEffect
from agf.powerups.manager import PowerUpManager

from src.base_attackers.game_config import PowerUpSettings
from src.base_attackers.powerups.effects import (
    BigGunEffect,
    FuelCanisterEffect,
    HealthRestoreEffect,
    MultiShotEffect,
    RapidFireEffect,
    ShieldEffect,
)


class BAPowerUpManager(PowerUpManager):
    def __init__(
        self,
        cfg: PowerUpSettings,
        fuel_canister_restore: float,
        window_width: int,
        window_height: int,
        ship_scale: float,
    ) -> None:
        # The agf base stores a sprite_scale used by the screen-space
        # spawner (which we override away), so the value passed here is
        # inert.  Our own ``_ship_scale`` is what ShieldEffect uses to
        # match the player ship size.
        super().__init__(
            config=PowerUpConfigBase(),
            window_width=window_width,
            window_height=window_height,
            sprite_scale=1.0,
        )
        self._cfg = cfg
        self._fuel_canister_restore = fuel_canister_restore
        self._ship_scale = ship_scale

    # ------------------------------------------------------------------
    # Effect factory
    # ------------------------------------------------------------------

    def create_effect(self, effect_type: str) -> PowerUpEffect:
        if effect_type == "health":
            return HealthRestoreEffect()
        if effect_type == "fuel_canister":
            return FuelCanisterEffect(self._fuel_canister_restore)
        if effect_type == "rapid_fire":
            return RapidFireEffect(
                duration=self._cfg.rapid_fire_duration,
                cooldown_multiplier=self._cfg.rapid_fire_cooldown_multiplier,
            )
        if effect_type == "big_gun":
            return BigGunEffect(
                duration=self._cfg.big_gun_duration,
                damage_bonus=self._cfg.big_gun_damage_bonus,
            )
        if effect_type == "multi_shot":
            return MultiShotEffect(duration=self._cfg.multi_shot_duration)
        if effect_type == "shield":
            return ShieldEffect(
                duration=self._cfg.shield_duration,
                ship_scale=self._ship_scale,
            )
        raise ValueError(f"Unknown power-up effect_type: {effect_type!r}")

    # ------------------------------------------------------------------
    # Frame tick — only ticks active effects.  The world-space spawner
    # is driven from RunLevelView; the agf screen-space spawner is
    # deliberately ignored.
    # ------------------------------------------------------------------

    def update_effects(self, delta_time: float, ship: Any, context: dict) -> None:
        expired: list[PowerUpEffect] = []
        for effect in self._active_effects:
            if not effect.update(delta_time, ship):
                expired.append(effect)
        for effect in expired:
            self.remove_effect(effect, ship, context)

    # ------------------------------------------------------------------
    # Public wrapper around agf's _add_effect (the brief's apply_effect).
    # ------------------------------------------------------------------

    def apply_effect(self, effect: PowerUpEffect, ship: Any, context: dict) -> None:
        self._add_effect(effect, ship, context)
