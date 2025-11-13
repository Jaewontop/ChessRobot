from __future__ import annotations

import time

import game_state
from robot_arm_controller import (
    execute_robot_move,
    get_move_description,
    get_robot_status,
    is_robot_moving,
)


def perform_robot_move(move) -> bool:
    """로봇팔에 이동을 명령."""
    if move is None:
        return False

    move_type = {
        "is_capture": game_state.current_board.is_capture(move),
        "is_castling": game_state.current_board.is_castling(move),
        "is_en_passant": game_state.current_board.is_en_passant(move),
        "is_promotion": move.promotion is not None,
    }

    move_desc = get_move_description(move_type, move.uci())
    print(f"🤖 {move_desc} 실행 중...")
    success = execute_robot_move(move_type, move.uci())
    if success:
        robot_status = get_robot_status()
        if robot_status["is_connected"]:
            print("✅ 로봇팔 명령 전송 성공")
        else:
            print("✅ 명령 분석 완료 (로봇팔 미연결)")
    else:
        print("❌ 로봇팔 명령 실행 실패")
    return success


def wait_until_robot_idle() -> None:
    """로봇팔이 움직이는 동안 대기."""
    if is_robot_moving():
        print("🤖 로봇팔이 움직이는 중입니다. 잠시 대기...")
        while is_robot_moving():
            time.sleep(0.5)
        print("🤖 로봇팔 움직임 완료!")

