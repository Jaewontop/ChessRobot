from __future__ import annotations

import chess

import game_state
from move_analyzer import analyze_coordinates
from timer_control import check_timer_button_press


def get_move_from_user():
    """키보드로 이동을 입력받음 (예: e2e4). 'quit'로 종료."""
    print("⌨️ 수를 입력하세요 (예: e2e4). 'quit'로 종료, Ctrl+C도 종료")
    while True:
        try:
            button_signal = check_timer_button_press()
            if button_signal:
                current_turn = "white" if game_state.current_board.turn == chess.WHITE else "black"
                print(f"⚠️ 타이머 입력 감지: {button_signal}. 현재는 {current_turn} 차례입니다.")

            user_input = input("이동 입력 (e2e4): ").strip().lower()
            if user_input in ["q", "quit", "exit"]:
                return "quit"

            if len(user_input) == 4:
                coord1 = user_input[:2]
                coord2 = user_input[2:]

                if _is_valid_coordinate(coord1) and _is_valid_coordinate(coord2):
                    move_tuple = analyze_coordinates(game_state.current_board, coord1, coord2)
                    if move_tuple:
                        from_square, to_square = move_tuple
                        from_sq = chess.parse_square(from_square)
                        to_sq = chess.parse_square(to_square)
                        move = chess.Move(from_sq, to_sq)
                        if move in game_state.current_board.legal_moves:
                            return move
                        print("❌ 잘못된 이동입니다!")
                    else:
                        print("❌ 유효하지 않은 움직임입니다!")
                else:
                    print("❌ 올바른 형식으로 입력하세요 (예: e2e4)")
            else:
                print("❌ 올바른 형식으로 입력하세요 (예: e2e4)")
        except ValueError:
            print("❌ 잘못된 좌표입니다!")
        except KeyboardInterrupt:
            return "quit"


def _is_valid_coordinate(coord: str) -> bool:
    files = "abcdefgh"
    ranks = "12345678"
    return coord[0] in files and coord[1] in ranks

