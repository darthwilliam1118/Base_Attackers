"""Base Attackers concrete power-up effects.

Six types:
  HealthRestoreEffect — InstantEffect: +1 HP capped at MAX_HP.
  FuelCanisterEffect  — InstantEffect: ship.add_fuel(restore).
  RapidFireEffect     — StatModifierEffect on ship.player_fire_cooldown.
  BigGunEffect        — StatModifierEffect on ship.player_bullet_damage.
  MultiShotEffect     — BehaviorEffect flag; firing branch lives in
                        RunLevelView._try_fire (PlayerBullet/SFX coupling).
  ShieldEffect        — OverlayEffect; 3-hit capacity that degrades the
                        shield3 → shield2 → shield1 textures.
"""

from __future__ import annotations

from typing import Any

import arcade

from agf.powerups.effect_categories import (
    BehaviorEffect,
    InstantEffect,
    OverlayEffect,
    StatModifierEffect,
)

# ---------------------------------------------------------------------------
# Instant effects
# ---------------------------------------------------------------------------


class HealthRestoreEffect(InstantEffect):
    @property
    def effect_type(self) -> str:
        return "health"

    def apply(self, ship: Any, context: dict) -> None:
        ship.hp = min(ship.MAX_HP, ship.hp + 1)


class FuelCanisterEffect(InstantEffect):
    def __init__(self, restore: float) -> None:
        self._restore = restore

    @property
    def effect_type(self) -> str:
        return "fuel_canister"

    def apply(self, ship: Any, context: dict) -> None:
        ship.add_fuel(self._restore)


# ---------------------------------------------------------------------------
# Stat modifiers — mutate ship attributes directly via the base class.
# ---------------------------------------------------------------------------


class RapidFireEffect(StatModifierEffect):
    def __init__(self, duration: float, cooldown_multiplier: float) -> None:
        super().__init__(
            attribute="player_fire_cooldown",
            duration=duration,
            multiplier=cooldown_multiplier,
            effect_type_name="rapid_fire",
            label="RAPID FIRE",
        )


class BigGunEffect(StatModifierEffect):
    def __init__(self, duration: float, damage_bonus: int) -> None:
        super().__init__(
            attribute="player_bullet_damage",
            duration=duration,
            multiplier=1.0,
            additive=float(damage_bonus),
            effect_type_name="big_gun",
            label="BIG GUN",
        )


# ---------------------------------------------------------------------------
# Behavior — pure flag; RunLevelView._try_fire checks get_active_behavior().
# ---------------------------------------------------------------------------


class MultiShotEffect(BehaviorEffect):
    @property
    def effect_type(self) -> str:
        return "multi_shot"

    def get_bullets(self, ship: Any) -> list[Any]:
        # Bullet spawn lives in RunLevelView._fire_multi_shot — keeping
        # PlayerBullet + SFX + cooldown coupled with the existing firing
        # pipeline rather than threading them through this effect.
        return []


# ---------------------------------------------------------------------------
# Overlay — shield with degrading texture and 3-hit capacity.
# Texture loading, swapping, and pulse live on ShieldSprite.
# ---------------------------------------------------------------------------


class ShieldEffect(OverlayEffect):
    def __init__(
        self,
        duration: float,
        hit_capacity: int = 3,
        ship_scale: float = 1.0,
    ) -> None:
        super().__init__(duration)
        self._capacity = hit_capacity
        self._hits_left = hit_capacity
        self._ship_scale = ship_scale

    @property
    def effect_type(self) -> str:
        return "shield"

    def create_overlay_sprite(self, scale: float) -> arcade.Sprite:
        # Ignore the context-supplied ``scale`` (which is for power-up
        # pickups, sized at native 1.0 in this game) and use the ship
        # scale stored at construction so the shield wraps the ship.
        from src.base_attackers.sprites import ShieldSprite

        return ShieldSprite(scale=self._ship_scale * 1.4)

    def update_overlay_sprite(self, ship_x: float, ship_y: float) -> None:
        if self._overlay_sprite is None:
            return
        from src.base_attackers.sprites import ShieldSprite

        if isinstance(self._overlay_sprite, ShieldSprite):
            self._overlay_sprite.update_state(self._hits_left, ship_x, ship_y)

    def on_hit_absorbed(self) -> bool:
        self._hits_left -= 1
        return self._hits_left <= 0
