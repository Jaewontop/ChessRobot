from __future__ import annotations

from pathlib import Path
from typing import Optional

import chess

BASE_DIR = Path(__file__).resolve().parent
BOARD_VALUES_PATH = BASE_DIR / "init_board_values.npy"
CHESS_PIECES_PATH = BASE_DIR / "chess_pieces.pkl"

current_board: chess.Board = chess.Board()
player_color: str = "white"
difficulty: int = 5
game_over: bool = False
move_count: int = 0
init_board_values: Optional[object] = None

cv_capture: Optional[object] = None
cv_capture_wrapper: Optional[object] = None
cv_turn_color: str = "white"
chess_pieces_state: Optional[list[list[str]]] = None


def reset_game_state() -> None:
    """게임 전역 상태를 초기값으로 재설정."""
    global current_board, player_color, difficulty, game_over, move_count
    global init_board_values, cv_capture, cv_capture_wrapper, cv_turn_color
    global chess_pieces_state

    current_board = chess.Board()
    player_color = "white"
    difficulty = 5
    game_over = False
    move_count = 0
    init_board_values = None

    cv_capture = None
    cv_capture_wrapper = None
    cv_turn_color = "white"
    chess_pieces_state = None

