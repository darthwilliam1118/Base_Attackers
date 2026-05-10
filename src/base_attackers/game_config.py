"""Game configuration — extends agf BaseGameConfig."""
from __future__ import annotations

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
class GameConfig(BaseGameConfig):
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    ui: UIConfig = field(default_factory=UIConfig)

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
        return cls(
            starting_level=int(game.get("starting_level", cls.starting_level)),
            num_lives=int(game.get("num_lives", cls.num_lives)),
            music_volume=int(game.get("music_volume", cls.music_volume)),
            effects_volume=int(game.get("effects_volume", cls.effects_volume)),
            debug=bool(game.get("debug", cls.debug)),
            god_mode=bool(game.get("god_mode", cls.god_mode)),
            max_window_height=int(
                game.get("max_window_height", cls.max_window_height)
            ),
            sprite_scale=float(game.get("sprite_scale", cls.sprite_scale)),
            background=bg,
            ui=ui,
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
