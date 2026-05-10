"""RunLevelView — active gameplay screen.

This is a minimal stub. Replace PlaceholderLevel in level_factory.py
with your real level implementation and extend this view as needed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import arcade
from agf.ui.text_utils import FONT_MAIN

# Sound effects — uncomment when adding sfx:
# from agf.paths import resource_path
# from agf.sound_manager import SoundManager

if TYPE_CHECKING:
    from src.base_attackers.state import GameStateManager


class RunLevelView(arcade.View):

    def __init__(self, manager: "GameStateManager") -> None:
        super().__init__()
        self._manager = manager
        self._keys_held: set[int] = set()
        self._level = None
        self._ship = None
        self._ship_list = arcade.SpriteList()
        self._hud = None
        self._paused = False
        self._setup()

    def _setup(self) -> None:
        from src.base_attackers.sprites.player_ship import PlayerShip
        from src.base_attackers.ui.hud import HUD

        ctx = self._manager.context
        cfg = ctx.get("config")
        scale = cfg.sprite_scale if cfg else 1.0
        self._cfg = cfg

        self._level = ctx.get("current_level")
        self._ship = PlayerShip(
            self.window.width, self.window.height, scale=scale
        )
        self._ship_list.append(self._ship)
        players = ctx.get("players", [])
        self._hud = HUD(self.window.width, self.window.height,
                        len(players))

        # Sound effects example — load each sound once, wrap in a
        # SoundManager (one per sound type) to throttle simultaneous
        # playbacks. Uncomment and adapt:
        # self._snd_hit = arcade.Sound(resource_path("assets/sounds/hit.wav"))
        # self._sm_hit = SoundManager(max_simultaneous=3)

    def on_show_view(self) -> None:
        arcade.set_background_color(arcade.color.BLACK)

    def on_update(self, delta_time: float) -> None:
        from src.base_attackers.state import GameState

        delta_time = min(delta_time, 1 / 15)
        self.window.star_field.update(delta_time)

        if self._paused:
            return

        if self._ship:
            self._ship.apply_movement(self._keys_held, delta_time)
            self._ship.update(delta_time)

        # Example sfx playback — pass effects_volume (0-100) as 0.0-1.0:
        # self._sm_hit.play(self._snd_hit, volume=self._cfg.effects_volume / 100)

        if self._level:
            events = self._level.update(delta_time, self._ship)
            for event in events:
                from agf.events import GameEvent
                if event == GameEvent.LEVEL_COMPLETE:
                    self._manager.transition(GameState.LEVEL_COMPLETE)
                    return
                elif event == GameEvent.PLAYER_KILLED:
                    self._manager.transition(GameState.PLAYER_KILLED)
                    return

        ctx = self._manager.context
        players = ctx.get("players", [])
        idx = ctx.get("active_player_index", 0)
        level_num = players[idx].current_level if players else 1
        if self._hud:
            self._hud.update(players, idx, level_num)

    def on_draw(self) -> None:
        self.clear()
        self.window.background.draw()
        self.window.star_field.draw()

        if self._level:
            self._level.draw()

        self._ship_list.draw()

        if self._hud:
            self._hud.draw()

        if self._paused:
            w, h = self.window.width, self.window.height
            arcade.draw_lrbt_rectangle_filled(0, w, 0, h, (0, 0, 0, 140))
            arcade.draw_text(
                "PAUSED",
                w / 2, h / 2,
                arcade.color.WHITE, 48,
                font_name=FONT_MAIN,
                anchor_x="center", anchor_y="center",
            )

    def on_key_press(self, key: int, modifiers: int) -> None:
        from src.base_attackers.state import GameState

        if key == arcade.key.P:
            self._paused = not self._paused
            return

        # Debug shortcuts — remove when real level is implemented
        if key == arcade.key.W:
            self._manager.transition(GameState.LEVEL_COMPLETE)
            return
        if key == arcade.key.L:
            self._manager.transition(GameState.PLAYER_KILLED)
            return

        self._keys_held.add(key)

    def on_key_release(self, key: int, modifiers: int) -> None:
        self._keys_held.discard(key)
