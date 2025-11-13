from __future__ import annotations

import chess

import game_state
from engine_manager import evaluate_position
from robot_arm_controller import get_robot_status, is_robot_moving
from timer_manager import get_timer_display


def display_board() -> None:
    """체스보드를 터미널에 표시."""
    print("♔ 터미널 체스 게임 ♔")
    print("=" * 50)

    print(f"{get_timer_display()}")

    if is_robot_moving():
        print("🤖 로봇이 움직이는 중...")
    else:
        robot_status = get_robot_status()
        if robot_status["is_connected"]:
            print("🤖 로봇팔 대기 중")
        else:
            print("🤖 로봇팔 연결 안됨")

    print("-" * 50)

    try:
        eval_data = evaluate_position(game_state.current_board, depth=game_state.difficulty)
        if eval_data:
            _print_engine_evaluation(eval_data)
    except Exception:
        # 평가 실패 시 조용히 넘어감
        pass

    _print_board(game_state.current_board)
    _print_game_status(game_state.current_board)


def _print_engine_evaluation(eval_data: dict) -> None:
    wp = eval_data.get("win_prob_white")
    cp = eval_data.get("cp")
    mate = eval_data.get("mate")
    best_san = eval_data.get("best_move_san")
    best_move = eval_data.get("best_move")
    move_type = eval_data.get("move_type")

    line = "평가: "
    if mate is not None:
        line += f"체크메이트 경로 (mate {mate:+d})"
    elif wp is not None:
        w = int(round(wp * 100))
        b = 100 - w
        if cp is not None:
            line += f"백 {w}% / 흑 {b}% (cp {cp:+d})"
        else:
            line += f"백 {w}% / 흑 {b}%"
    else:
        line += "계산 불가"
    if best_san:
        line += f" | 권장수: {best_san}"
    print(line)

    if move_type and best_move:
        move_type_name = _resolve_move_type_name(move_type)
        print(f"움직임 타입: {move_type_name}")

    print("-" * 50)


def _resolve_move_type_name(move_type: dict) -> str:
    if move_type.get("is_castling"):
        return "캐슬링"
    if move_type.get("is_en_passant"):
        return "앙파상"
    if move_type.get("is_capture"):
        return "기물 잡기"
    if move_type.get("is_promotion"):
        return "프로모션"
    return "일반 이동"


def _print_board(board: chess.Board) -> None:
    board_str = str(board)
    lines = board_str.split("\n")

    print("   a b c d e f g h")
    print("  ┌─┬─┬─┬─┬─┬─┬─┬─┐")

    for i, line in enumerate(lines):
        rank = 8 - i
        print(f"{rank} │{'│'.join(line.split())}│")
        if i < 7:
            print("  ├─┼─┼─┼─┼─┼─┼─┼─┤")

    print("  └─┴─┴─┴─┴─┴─┴─┴─┘")
    print("   a b c d e f g h")
    print("-" * 50)


def _print_game_status(board: chess.Board) -> None:
    if board.is_checkmate():
        print("♔ 체크메이트!")
        if board.turn == chess.WHITE:
            print("검은색 승리!")
        else:
            print("흰색 승리!")
    elif board.is_stalemate():
        print("⚖️ 스테일메이트 - 무승부!")
    elif board.is_check():
        print("⚡ 체크!")

    turn = "흰색" if board.turn == chess.WHITE else "검은색"
    print(f"현재 차례: {turn}")
    print("-" * 50)

