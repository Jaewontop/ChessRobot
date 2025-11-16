from __future__ import annotations

import chess

from game import game_state
from engine.engine_manager import engine_make_best_move, evaluate_position
from game.game_utils import describe_game_end
from robot_arm.robot_control import perform_robot_move


def get_stockfish_response_move() -> chess.Move | None:
    """현재 보드에서 Stockfish가 제안하는 다음 이동을 반환."""
    try:
        eval_data = evaluate_position(game_state.current_board, depth=game_state.difficulty)
    except Exception as exc:
        print(f"[ERROR] Stockfish 평가 실패: {exc}")
        return None

    if not eval_data or not eval_data.get("best_move"):
        print("[Stockfish] 최선의 수를 얻지 못했습니다.")
        return None

    uci_move = eval_data["best_move"]
    try:
        move = chess.Move.from_uci(uci_move)
    except ValueError:
        print(f"[Stockfish] 잘못된 UCI 수: {uci_move}")
        return None

    if move not in game_state.current_board.legal_moves:
        print(f"[Stockfish] 불법 수 제안: {uci_move}")
        return None

    return move


def make_stockfish_move() -> bool:
    """Stockfish가 수를 두도록 함."""
    try:
        eval_data = evaluate_position(game_state.current_board, depth=game_state.difficulty)
        if eval_data and eval_data.get("best_move"):
            try:
                candidate_move = chess.Move.from_uci(eval_data["best_move"])
            except ValueError:
                candidate_move = None

            if candidate_move and candidate_move in game_state.current_board.legal_moves:
                perform_robot_move(candidate_move)

        moved = engine_make_best_move(game_state.current_board, depth=game_state.difficulty)
        if moved:
            move, san = moved
            print(f"[DEBUG] Stockfish 선택 수: {move.uci()} (SAN: {san})")
            if game_state.current_board.is_game_over():
                print(
                    f"[DEBUG] 엔진 수 이후 게임 종료: "
                    f"{describe_game_end(game_state.current_board)}"
                )
            return True

        print("[DEBUG] Stockfish가 유효한 수를 반환하지 않았습니다")
        return False
    except Exception as exc:
        print(f"[!] Stockfish 오류: {exc}")
        return False

