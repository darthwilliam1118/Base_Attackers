"""Game configuration — extends agf BaseGameConfig."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agf.background.background_config import BackgroundConfig
from agf.config.base_config import BaseGameConfig
from agf.paths import writable_root


@dataclass
class UIConfig:
    popup_duration: float = 0.8
    popup_rise_speed: float = 60.0


@dataclass
class ShipSettings:
    accel: float = 400.0
    friction: float = 0.85
    max_speed_x: float = 350.0
    max_speed_y: float = 300.0
    hp: int = 3
    hit_radius: float = 16.0
    gravity: float = 0.0  # px/s² toward the world floor; 0 disables
    # Fuel
    fuel_capacity: float = 100.0
    fuel_drain_rate: float = 4.0
    fuel_gravity: float = 150.0  # px/s² downward when fuel is empty
    fuel_canister_restore: float = 25.0


@dataclass
class FuelTowerSettings:
    transfer_rate: float = 20.0
    snap_distance: float = 40.0
    tower_capacity: float = 60.0
    spawn_pressure_interval: float = 3.0


@dataclass
class CombatSettings:
    player_bullet_speed: float = 600.0
    player_fire_cooldown: float = 0.25
    player_bullet_damage: int = 1
    enemy_bullet_speed: float = 250.0
    missile_speed: float = 200.0
    missile_proximity_trigger: float = 180.0
    turret_fire_cooldown: float = 2.0
    turret_aim_jitter: float = 0.15
    turret_rotation_speed: float = 90.0
    silo_hp: int = 2
    turret_hp: int = 3
    bullet_cull_margin: float = 64.0
    # Patrol ships
    patrol_hp: int = 2
    patrol_speed_min: float = 150.0
    patrol_speed_max: float = 280.0
    patrol_intercept_lead: float = 0.6
    patrol_ram_damage: int = 1
    patrol_spawn_margin: float = 60.0
    patrol_spawn_interval: float = 6.0  # seconds between autonomous spawns
    patrol_fire_cooldown: float = 2.5  # seconds between patrol shots (non-kamikaze)
    # Laser turrets
    laser_turret_hp: int = 4
    laser_turret_fire_cooldown: float = 3.5
    laser_telegraph_duration: float = 0.6
    laser_beam_duration: float = 0.12
    laser_beam_damage: int = 1
    laser_beam_width: float = 3.0
    laser_proximity_trigger: float = 260.0
    laser_beam_color: list[int] = field(default_factory=lambda: [255, 60, 60, 220])
    laser_telegraph_color: list[int] = field(
        default_factory=lambda: [255, 180, 60, 120]
    )


@dataclass
class PowerUpSettings:
    fall_speed_min: float = 40.0
    fall_speed_max: float = 100.0
    spawn_interval_level_1: float = 20.0
    spawn_interval_level_2: float = 14.0
    spawn_interval_level_3: float = 10.0
    spawn_interval_default: float = 8.0
    rapid_fire_duration: float = 8.0
    big_gun_duration: float = 10.0
    multi_shot_duration: float = 8.0
    shield_duration: float = 12.0
    rapid_fire_cooldown_multiplier: float = 0.4
    big_gun_damage_bonus: int = 1
    weights: dict[str, dict[str, int]] = field(default_factory=dict)

    def weight_table_for_level(self, level: int) -> dict[str, int]:
        return self.weights.get(f"level_{level}", self.weights.get("default", {}))

    def spawn_interval_for_level(self, level: int) -> float:
        return getattr(
            self, f"spawn_interval_level_{level}", self.spawn_interval_default
        )


@dataclass
class TerrainSettings:
    chunk_width: int = 64
    cull_buffer_chunks: int = 3


@dataclass
class LevelSettings:
    world_width: float = 6400.0
    world_height: float = 720.0
    terrain_amplitude: float = 80.0
    terrain_frequency: float = 0.008
    terrain_half_width: float = 280.0
    ceiling_present: bool = False
    terrain_renderer: str = "tile"  # "tile" | "polygon"
    terrain_seed: int = 0  # 0 means random per run


_LEVEL_SECTION_RE = re.compile(r"^level_(\d+)$")


@dataclass
class GameConfig(BaseGameConfig):
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    ship: ShipSettings = field(default_factory=ShipSettings)
    fuel_tower: FuelTowerSettings = field(default_factory=FuelTowerSettings)
    combat: CombatSettings = field(default_factory=CombatSettings)
    powerups: PowerUpSettings = field(default_factory=PowerUpSettings)
    terrain: TerrainSettings = field(default_factory=TerrainSettings)
    levels: dict[int, LevelSettings] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "GameConfig":
        if path is None:
            path = writable_root() / "game_config.toml"
        try:
            with open(path, "rb") as fh:
                data = tomllib.load(fh)
        except Exception:
            return cls()

        game = data.get("game", {})
        bg_raw = data.get("background", {})
        ui_raw = data.get("ui", {})
        ship_raw = data.get("ship", {})
        fuel_tower_raw = data.get("fuel_tower", {})
        combat_raw = data.get("combat", {})
        powerups_raw = data.get("powerups", {})
        terrain_raw = data.get("terrain", {})

        bg = BackgroundConfig(
            background_image=str(
                bg_raw.get("background_image", BackgroundConfig.background_image)
            ),
            star_count=int(bg_raw.get("star_count", BackgroundConfig.star_count)),
            star_speed_min=float(
                bg_raw.get("star_speed_min", BackgroundConfig.star_speed_min)
            ),
            star_speed_max=float(
                bg_raw.get("star_speed_max", BackgroundConfig.star_speed_max)
            ),
        )
        ui = UIConfig(
            popup_duration=float(ui_raw.get("popup_duration", UIConfig.popup_duration)),
            popup_rise_speed=float(
                ui_raw.get("popup_rise_speed", UIConfig.popup_rise_speed)
            ),
        )
        ship = ShipSettings(
            accel=float(ship_raw.get("accel", ShipSettings.accel)),
            friction=float(ship_raw.get("friction", ShipSettings.friction)),
            max_speed_x=float(ship_raw.get("max_speed_x", ShipSettings.max_speed_x)),
            max_speed_y=float(ship_raw.get("max_speed_y", ShipSettings.max_speed_y)),
            hp=int(ship_raw.get("hp", ShipSettings.hp)),
            hit_radius=float(ship_raw.get("hit_radius", ShipSettings.hit_radius)),
            gravity=float(ship_raw.get("gravity", ShipSettings.gravity)),
            fuel_capacity=float(
                ship_raw.get("fuel_capacity", ShipSettings.fuel_capacity)
            ),
            fuel_drain_rate=float(
                ship_raw.get("fuel_drain_rate", ShipSettings.fuel_drain_rate)
            ),
            fuel_gravity=float(ship_raw.get("fuel_gravity", ShipSettings.fuel_gravity)),
            fuel_canister_restore=float(
                ship_raw.get(
                    "fuel_canister_restore", ShipSettings.fuel_canister_restore
                )
            ),
        )
        fuel_tower = FuelTowerSettings(
            transfer_rate=float(
                fuel_tower_raw.get("transfer_rate", FuelTowerSettings.transfer_rate)
            ),
            snap_distance=float(
                fuel_tower_raw.get("snap_distance", FuelTowerSettings.snap_distance)
            ),
            tower_capacity=float(
                fuel_tower_raw.get("tower_capacity", FuelTowerSettings.tower_capacity)
            ),
            spawn_pressure_interval=float(
                fuel_tower_raw.get(
                    "spawn_pressure_interval",
                    FuelTowerSettings.spawn_pressure_interval,
                )
            ),
        )
        combat = CombatSettings(
            player_bullet_speed=float(
                combat_raw.get(
                    "player_bullet_speed", CombatSettings.player_bullet_speed
                )
            ),
            player_fire_cooldown=float(
                combat_raw.get(
                    "player_fire_cooldown", CombatSettings.player_fire_cooldown
                )
            ),
            player_bullet_damage=int(
                combat_raw.get(
                    "player_bullet_damage", CombatSettings.player_bullet_damage
                )
            ),
            enemy_bullet_speed=float(
                combat_raw.get("enemy_bullet_speed", CombatSettings.enemy_bullet_speed)
            ),
            missile_speed=float(
                combat_raw.get("missile_speed", CombatSettings.missile_speed)
            ),
            missile_proximity_trigger=float(
                combat_raw.get(
                    "missile_proximity_trigger",
                    CombatSettings.missile_proximity_trigger,
                )
            ),
            turret_fire_cooldown=float(
                combat_raw.get(
                    "turret_fire_cooldown", CombatSettings.turret_fire_cooldown
                )
            ),
            turret_aim_jitter=float(
                combat_raw.get("turret_aim_jitter", CombatSettings.turret_aim_jitter)
            ),
            turret_rotation_speed=float(
                combat_raw.get(
                    "turret_rotation_speed", CombatSettings.turret_rotation_speed
                )
            ),
            silo_hp=int(combat_raw.get("silo_hp", CombatSettings.silo_hp)),
            turret_hp=int(combat_raw.get("turret_hp", CombatSettings.turret_hp)),
            bullet_cull_margin=float(
                combat_raw.get("bullet_cull_margin", CombatSettings.bullet_cull_margin)
            ),
            patrol_hp=int(combat_raw.get("patrol_hp", CombatSettings.patrol_hp)),
            patrol_speed_min=float(
                combat_raw.get("patrol_speed_min", CombatSettings.patrol_speed_min)
            ),
            patrol_speed_max=float(
                combat_raw.get("patrol_speed_max", CombatSettings.patrol_speed_max)
            ),
            patrol_intercept_lead=float(
                combat_raw.get(
                    "patrol_intercept_lead", CombatSettings.patrol_intercept_lead
                )
            ),
            patrol_ram_damage=int(
                combat_raw.get("patrol_ram_damage", CombatSettings.patrol_ram_damage)
            ),
            patrol_spawn_margin=float(
                combat_raw.get(
                    "patrol_spawn_margin", CombatSettings.patrol_spawn_margin
                )
            ),
            patrol_spawn_interval=float(
                combat_raw.get(
                    "patrol_spawn_interval", CombatSettings.patrol_spawn_interval
                )
            ),
            patrol_fire_cooldown=float(
                combat_raw.get(
                    "patrol_fire_cooldown", CombatSettings.patrol_fire_cooldown
                )
            ),
            laser_turret_hp=int(
                combat_raw.get("laser_turret_hp", CombatSettings.laser_turret_hp)
            ),
            laser_turret_fire_cooldown=float(
                combat_raw.get(
                    "laser_turret_fire_cooldown",
                    CombatSettings.laser_turret_fire_cooldown,
                )
            ),
            laser_telegraph_duration=float(
                combat_raw.get(
                    "laser_telegraph_duration",
                    CombatSettings.laser_telegraph_duration,
                )
            ),
            laser_beam_duration=float(
                combat_raw.get(
                    "laser_beam_duration", CombatSettings.laser_beam_duration
                )
            ),
            laser_beam_damage=int(
                combat_raw.get("laser_beam_damage", CombatSettings.laser_beam_damage)
            ),
            laser_beam_width=float(
                combat_raw.get("laser_beam_width", CombatSettings.laser_beam_width)
            ),
            laser_proximity_trigger=float(
                combat_raw.get(
                    "laser_proximity_trigger",
                    CombatSettings.laser_proximity_trigger,
                )
            ),
            laser_beam_color=list(
                combat_raw.get("laser_beam_color", CombatSettings().laser_beam_color)
            ),
            laser_telegraph_color=list(
                combat_raw.get(
                    "laser_telegraph_color", CombatSettings().laser_telegraph_color
                )
            ),
        )
        weights_raw = powerups_raw.get("weights", {})
        weights: dict[str, dict[str, int]] = {}
        for level_key, table in weights_raw.items():
            if isinstance(table, dict):
                weights[level_key] = {str(k): int(v) for k, v in table.items()}
        powerups = PowerUpSettings(
            fall_speed_min=float(
                powerups_raw.get("fall_speed_min", PowerUpSettings.fall_speed_min)
            ),
            fall_speed_max=float(
                powerups_raw.get("fall_speed_max", PowerUpSettings.fall_speed_max)
            ),
            spawn_interval_level_1=float(
                powerups_raw.get(
                    "spawn_interval_level_1",
                    PowerUpSettings.spawn_interval_level_1,
                )
            ),
            spawn_interval_level_2=float(
                powerups_raw.get(
                    "spawn_interval_level_2",
                    PowerUpSettings.spawn_interval_level_2,
                )
            ),
            spawn_interval_level_3=float(
                powerups_raw.get(
                    "spawn_interval_level_3",
                    PowerUpSettings.spawn_interval_level_3,
                )
            ),
            spawn_interval_default=float(
                powerups_raw.get(
                    "spawn_interval_default",
                    PowerUpSettings.spawn_interval_default,
                )
            ),
            rapid_fire_duration=float(
                powerups_raw.get(
                    "rapid_fire_duration", PowerUpSettings.rapid_fire_duration
                )
            ),
            big_gun_duration=float(
                powerups_raw.get("big_gun_duration", PowerUpSettings.big_gun_duration)
            ),
            multi_shot_duration=float(
                powerups_raw.get(
                    "multi_shot_duration", PowerUpSettings.multi_shot_duration
                )
            ),
            shield_duration=float(
                powerups_raw.get("shield_duration", PowerUpSettings.shield_duration)
            ),
            rapid_fire_cooldown_multiplier=float(
                powerups_raw.get(
                    "rapid_fire_cooldown_multiplier",
                    PowerUpSettings.rapid_fire_cooldown_multiplier,
                )
            ),
            big_gun_damage_bonus=int(
                powerups_raw.get(
                    "big_gun_damage_bonus",
                    PowerUpSettings.big_gun_damage_bonus,
                )
            ),
            weights=weights,
        )
        terrain = TerrainSettings(
            chunk_width=int(
                terrain_raw.get("chunk_width", TerrainSettings.chunk_width)
            ),
            cull_buffer_chunks=int(
                terrain_raw.get(
                    "cull_buffer_chunks", TerrainSettings.cull_buffer_chunks
                )
            ),
        )

        levels: dict[int, LevelSettings] = {}
        for key, raw in data.items():
            m = _LEVEL_SECTION_RE.match(key)
            if not m or not isinstance(raw, dict):
                continue
            n = int(m.group(1))
            levels[n] = LevelSettings(
                world_width=float(raw.get("world_width", LevelSettings.world_width)),
                world_height=float(raw.get("world_height", LevelSettings.world_height)),
                terrain_amplitude=float(
                    raw.get("terrain_amplitude", LevelSettings.terrain_amplitude)
                ),
                terrain_frequency=float(
                    raw.get("terrain_frequency", LevelSettings.terrain_frequency)
                ),
                terrain_half_width=float(
                    raw.get("terrain_half_width", LevelSettings.terrain_half_width)
                ),
                ceiling_present=bool(
                    raw.get("ceiling_present", LevelSettings.ceiling_present)
                ),
                terrain_renderer=str(
                    raw.get("terrain_renderer", LevelSettings.terrain_renderer)
                ),
                terrain_seed=int(raw.get("terrain_seed", LevelSettings.terrain_seed)),
            )

        return cls(
            starting_level=int(game.get("starting_level", cls.starting_level)),
            num_lives=int(game.get("num_lives", cls.num_lives)),
            music_volume=int(game.get("music_volume", cls.music_volume)),
            effects_volume=int(game.get("effects_volume", cls.effects_volume)),
            debug=bool(game.get("debug", cls.debug)),
            god_mode=bool(game.get("god_mode", cls.god_mode)),
            max_window_height=int(game.get("max_window_height", cls.max_window_height)),
            sprite_scale=float(game.get("sprite_scale", cls.sprite_scale)),
            background=bg,
            ui=ui,
            ship=ship,
            fuel_tower=fuel_tower,
            combat=combat,
            powerups=powerups,
            terrain=terrain,
            levels=levels,
        )

    def save(self, path: Optional[Path] = None) -> None:
        if path is None:
            path = writable_root() / "game_config.toml"
        bg = self.background
        lines = [
            "[game]\n",
            f"starting_level = {self.starting_level}\n",
            f"num_lives = {self.num_lives}\n",
            f"music_volume = {self.music_volume}\n",
            f"effects_volume = {self.effects_volume}\n",
            f"debug = {'true' if self.debug else 'false'}\n",
            f"god_mode = {'true' if self.god_mode else 'false'}\n",
            f"max_window_height = {self.max_window_height}\n",
            f"sprite_scale = {self.sprite_scale}\n",
            "\n[background]\n",
            f'background_image = "{bg.background_image}"\n',
            f"star_count = {bg.star_count}\n",
            f"star_speed_min = {bg.star_speed_min}\n",
            f"star_speed_max = {bg.star_speed_max}\n",
        ]
        path.write_text("".join(lines), encoding="utf-8")
