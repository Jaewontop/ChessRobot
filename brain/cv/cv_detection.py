from __future__ import annotations

import pickle
from typing import Any, Optional

import chess

from game import game_state
from cv.cv_manager import (
    coord_to_chess_notation,
    process_turn_transition,
    save_initial_board_from_capture,
)


def default_chess_pieces() -> list[list[str]]:
    return [
        ["BR", "BN", "BB", "BQ", "BK", "BB", "BN", "BR"],
        ["BP", "BP", "BP", "BP", "BP", "BP", "BP", "BP"],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["WP", "WP", "WP", "WP", "WP", "WP", "WP", "WP"],
        ["WR", "WN", "WB", "WQ", "WK", "WB", "WN", "WR"],
    ]


def load_chess_pieces() -> list[list[str]]:
    path = game_state.CHESS_PIECES_PATH
    if path.exists():
        try:
            with open(path, "rb") as file:
                pieces = pickle.load(file)
            if isinstance(pieces, list) and len(pieces) == 8:
                return pieces
        except Exception as exc:
            print(f"[DEBUG] 체스 기물 배열 로드 실패: {exc}")
    return default_chess_pieces()


def detect_move_via_cv() -> Optional[chess.Move]:
    """CV로 기물 변화를 감지하여 체스 이동을 반환."""
    if game_state.cv_capture_wrapper is None:
        print("[CV] 캡처 장치가 초기화되지 않았습니다.")
        return None

    if game_state.chess_pieces_state is None:
        game_state.chess_pieces_state = load_chess_pieces()

    try:
        result = process_turn_transition(
            game_state.cv_capture_wrapper,
            str(game_state.BOARD_VALUES_PATH),
            str(game_state.CHESS_PIECES_PATH),
            game_state.chess_pieces_state,
            game_state.cv_turn_color,
        )
    except Exception as exc:
        print(f"[CV] 턴 전환 처리 실패: {exc}")
        return None

    game_state.cv_turn_color = result["turn_color"]
    game_state.init_board_values = result["init_board_values"]
    game_state.chess_pieces_state = result["chess_pieces"]

    src = result.get("src")
    dst = result.get("dst")
    move_str = result.get("move_str")
    if move_str:
        print(f"[CV] 감지된 이동: {move_str}")

    if src is None or dst is None:
        return None

    move = _resolve_move_from_coords(tuple(src), tuple(dst))
    if move is None:
        print(f"[CV] 합법적인 이동을 찾지 못했습니다: src={src}, dst={dst}")
    return move


def initialize_board_reference() -> Optional[Any]:
    """초기 캡처에서 체스판 기준값을 저장."""
    if game_state.cv_capture_wrapper is None:
        print("[!] 캡처 장치가 없어 체스판 기준값을 초기화할 수 없습니다")
        return None

    board_vals, _ = save_initial_board_from_capture(
        game_state.cv_capture_wrapper, str(game_state.BOARD_VALUES_PATH)
    )
    if board_vals is not None:
        game_state.init_board_values = board_vals
        print("[✓] 체스판 기준값 초기화 완료")
    else:
        print("[!] 체스판 기준값 초기화 실패 - CV 감지 정확도가 낮을 수 있습니다")
    return game_state.init_board_values


def _resolve_move_from_coords(
    src: tuple[int, int], dst: tuple[int, int]
) -> Optional[chess.Move]:
    """격자 좌표(src/dst)를 체스 Move로 변환."""
    candidates = [(src, dst)]
    if src != dst:
        candidates.append((dst, src))

    for from_coord, to_coord in candidates:
        from_name = coord_to_chess_notation(from_coord[0], from_coord[1])
        to_name = coord_to_chess_notation(to_coord[0], to_coord[1])
        try:
            from_sq = chess.parse_square(from_name)
            to_sq = chess.parse_square(to_name)
        except ValueError:
            continue

        promotions: list[Optional[chess.PieceType]] = [None]
        piece = game_state.current_board.piece_at(from_sq)
        if piece and piece.piece_type == chess.PAWN and to_name[1] in ("1", "8"):
            promotions = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]

        for promo in promotions:
            move = chess.Move(from_sq, to_sq, promotion=promo)
            if move in game_state.current_board.legal_moves:
                return move
    return None

