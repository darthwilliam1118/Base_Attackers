"""GameStateManager for Base Attackers."""

from __future__ import annotations

import logging
from enum import Enum, auto

from agf.state import BaseGameStateManager

log = logging.getLogger(__name__)


class GameState(Enum):
    SPLASH = auto()
    MAIN = auto()
    GAME_INIT = auto()
    SET_ACTIVE_PLAYER = auto()
    START_LEVEL = auto()
    RUN_LEVEL = auto()
    LEVEL_COMPLETE = auto()
    PLAYER_KILLED = auto()
    GAME_OVER = auto()
    SCORE_ENTRY = auto()
    TERRAIN_TEST = auto()
    EXIT = auto()


class GameStateManager(BaseGameStateManager):

    def _enter_state(self, state: GameState) -> None:
        from src.base_attackers.views.splash import SplashView
        from src.base_attackers.views.main_menu import MainMenuView
        from src.base_attackers.views.run_level import RunLevelView
        from src.base_attackers.views.level_complete import LevelCompleteView
        from src.base_attackers.views.player_killed import PlayerKilledView
        from src.base_attackers.views.game_over import GameOverView
        from src.base_attackers.views.score_entry import ScoreEntryView
        from src.base_attackers.views.terrain_test import TerrainTestView

        match state:
            case GameState.SPLASH:
                self.window.show_view(SplashView(self))
            case GameState.MAIN:
                self.window.show_view(MainMenuView(self))
            case GameState.GAME_INIT:
                self._handle_game_init()
            case GameState.SET_ACTIVE_PLAYER:
                self._handle_set_active_player()
            case GameState.START_LEVEL:
                self._handle_start_level()
            case GameState.RUN_LEVEL:
                self.window.show_view(RunLevelView(self))
            case GameState.LEVEL_COMPLETE:
                self.window.show_view(LevelCompleteView(self))
            case GameState.PLAYER_KILLED:
                self.window.show_view(PlayerKilledView(self))
            case GameState.GAME_OVER:
                self.window.show_view(GameOverView(self))
            case GameState.SCORE_ENTRY:
                self.window.show_view(ScoreEntryView(self))
            case GameState.TERRAIN_TEST:
                self.window.show_view(TerrainTestView(self))
            case GameState.EXIT:
                import arcade

                arcade.exit()

    def _handle_game_init(self) -> None:
        import random

        from agf.player_state import PlayerState
        from src.base_attackers.game_config import GameConfig

        cfg = self.context.get("config") or GameConfig.load()
        num_players = self.context.get("num_players", 1)
        self.context["config"] = cfg
        # Per-game seed: a fixed non-zero config value reproduces the same
        # maps every game (debugging); 0 picks a fresh random seed so each
        # game is unique.  It persists across respawns/level transitions
        # (only re-rolled here on a new game), so respawning a level
        # regenerates the identical layout.
        self.context["run_seed"] = cfg.level_gen.run_seed or random.randrange(
            1, 2**31 - 1
        )
        self.context["players"] = [
            PlayerState(
                player_num=i + 1,
                lives=cfg.num_lives,
                current_level=cfg.starting_level,
            )
            for i in range(num_players)
        ]
        self.context["active_player_index"] = 0
        self.transition(GameState.SET_ACTIVE_PLAYER)

    def _handle_set_active_player(self) -> None:
        self.transition(GameState.START_LEVEL)

    def _handle_start_level(self) -> None:
        from src.base_attackers.levels.level_factory import create_level

        players = self.context.get("players", [])
        idx = self.context.get("active_player_index", 0)
        cfg = self.context.get("config")
        level_number = players[idx].current_level if players else 1
        snapshot = players[idx].level_snapshot if players else None

        level = create_level(
            level_number=level_number,
            config=cfg,
            window_width=self.window.width,
            window_height=self.window.height,
            snapshot=snapshot,
        )
        self.context["current_level"] = level
        self.transition(GameState.RUN_LEVEL)
