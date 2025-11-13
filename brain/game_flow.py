from __future__ import annotations

import os
import time
from typing import Optional

import chess

import game_state
from board_display import display_board
from cv_detection import detect_move_via_cv, initialize_board_reference, load_chess_pieces
from cv_web import PiCam2Capture, ThreadSafeCapture, start_cv_web_server
from engine_control import get_stockfish_response_move, make_stockfish_move
from engine_manager import init_engine, shutdown_engine
from game_utils import describe_game_end
from robot_arm_controller import (
    connect_robot_arm,
    disconnect_robot_arm,
    get_robot_status,
    init_robot_arm,
    test_robot_connection,
)
from robot_control import perform_robot_move, wait_until_robot_idle
from timer_control import check_time_over, press_timer_button
from timer_manager import (
    check_timer_button,
    get_chess_timer_status,
    get_timer_manager,
    init_chess_timer,
)


def initialize_game(stockfish_path: str) -> bool:
    """엔진/로봇/타이머/CV 초기화 및 웹 모니터링 시작."""
    print("♔ 터미널 체스 게임 시작 ♔")
    print("=" * 50)

    if not os.path.exists(stockfish_path):
        print(f"[!] Stockfish를 찾을 수 없습니다: {stockfish_path}")
        print("[!] 체스 엔진 기능이 제한됩니다.")
        return False

    init_engine()

    print("[→] 로봇팔 초기화 중...")
    init_robot_arm(enabled=True, port="/dev/ttyUSB0", baudrate=9600)

    if test_robot_connection():
        print("[✓] 로봇팔 연결 테스트 성공")
        if connect_robot_arm():
            print("[✓] 로봇팔 연결 완료")
        else:
            print("[!] 로봇팔 연결 실패 - 명령 전송 없이 진행")
    else:
        print("[!] 로봇팔 연결 테스트 실패 - 명령 전송 없이 진행")

    print("[→] 아두이노 타이머 연결 시도 중...")
    if not init_chess_timer():
        print("[!] 아두이노 타이머 연결 실패 - 타이머 없이 진행")
    else:
        print("[✓] 아두이노 타이머 연결 및 모니터링 시작 완료")
        status = get_chess_timer_status()
        print(f"[→] 타이머 상태: {status}")

    game_state.chess_pieces_state = load_chess_pieces()
    game_state.cv_turn_color = "white"

    try:
        game_state.cv_capture = PiCam2Capture()
        game_state.cv_capture_wrapper = ThreadSafeCapture(game_state.cv_capture)
        print("[✓] Picamera 캡처 초기화 완료")
    except Exception as exc:
        game_state.cv_capture = None
        game_state.cv_capture_wrapper = None
        print(f"[!] Picamera 초기화 실패: {exc}")

    if game_state.cv_capture_wrapper is not None:
        print("[→] 체스판 기준값 초기화(CV) 중...")
        initialize_board_reference()
    else:
        print("[!] 캡처 장치가 없어 체스판 기준값을 초기화할 수 없습니다")

    try:
        start_cv_web_server(
            np_path=str(game_state.BOARD_VALUES_PATH),
            pkl_path=str(game_state.CHESS_PIECES_PATH),
            use_thread=True,
            cap=game_state.cv_capture_wrapper,
        )
        print("[✓] CV 웹 모니터링 서버 시작 (http://0.0.0.0:5001)")
    except Exception as exc:
        print(f"[!] CV 웹 서버 시작 실패: {exc}")

    game_state.player_color = "white"
    print("[→] 플레이어 색상: white (고정)")

    print(f"게임 설정: {game_state.player_color} 플레이어")
    print("[→] 초기 보드 상태 확인 중...")
    print(f"[→] 게임 종료 여부: {game_state.current_board.is_game_over()}")
    print(f"[→] 현재 차례: {'흰색' if game_state.current_board.turn == chess.WHITE else '검은색'}")

    return True


def game_loop() -> None:
    """메인 게임 루프."""
    game_state.difficulty = 5
    print(f"[→] 난이도: {game_state.difficulty} (고정)")
    print(f"게임 설정: {game_state.player_color} 플레이어, 난이도 {game_state.difficulty}")

    while not game_state.game_over:
        display_board()
        print(
            f"[DEBUG] 루프 시작 - 차례: "
            f"{'백' if game_state.current_board.turn == chess.WHITE else '흑'}, "
            f"FEN: {game_state.current_board.fen()}"
        )

        if check_time_over():
            game_state.game_over = True
            break

        button_signal = _poll_timer_button()
        if not button_signal:
            time.sleep(0.1)
            continue

        if button_signal == "white_turn_end":
            print("🔘 플레이어 버튼 감지 - 수를 분석합니다.")
            handle_player_turn()
        else:
            print("⏳ 로봇 측 버튼 감지 - 대기합니다.")
            time.sleep(0.5)

        if game_state.game_over:
            break

        if game_state.current_board.is_game_over():
            print("[DEBUG] 게임 종료 조건 만족!")
            print(f"[DEBUG] 체크메이트: {game_state.current_board.is_checkmate()}")
            print(f"[DEBUG] 스테일메이트: {game_state.current_board.is_stalemate()}")
            print(f"[DEBUG] 체크: {game_state.current_board.is_check()}")
            game_state.game_over = True
            break

    display_board()
    print("게임 종료!")


def handle_player_turn() -> None:
    """사용자 차례 처리."""
    try:
        move = detect_move_via_cv()
    except Exception as exc:
        print(f"[ERROR] 사용자 입력 처리 실패: {exc}")
        return

    if not isinstance(move, chess.Move):
        print("❌ 유효하지 않은 움직임입니다!")
        return

    apply_detected_move(move)
    if game_state.game_over:
        return

    engine_move = get_stockfish_response_move()
    if engine_move is None:
        print("[Stockfish] 엔진 이동을 생성하지 못했습니다.")
        return

    if not perform_robot_move(engine_move):
        print("[Stockfish] 로봇 이동 실패.")
        return

    apply_detected_move(engine_move)
    press_timer_button("P1")


def handle_engine_turn() -> None:
    """엔진 차례 처리."""
    try:
        print("🤖 Stockfish가 생각 중...")
        robot_status = get_robot_status()
        if robot_status["is_connected"]:
            wait_until_robot_idle()

        if make_stockfish_move():
            game_state.move_count += 1
            print("✅ Stockfish 이동 완료")
            if check_time_over():
                game_state.game_over = True
            elif game_state.current_board.is_game_over():
                print(
                    f"[DEBUG] 엔진 수 이후 게임 종료: "
                    f"{describe_game_end(game_state.current_board)}"
                )
                game_state.game_over = True
        else:
            print("❌ Stockfish 이동 실패 - 다음 턴으로 계속 진행")
            time.sleep(0.5)
    except Exception as exc:
        print(f"[ERROR] 엔진 차례 처리 실패: {exc}")
        time.sleep(1)


def apply_detected_move(move: chess.Move) -> None:
    """인식된 이동을 보드에 반영하고 종료 여부를 확인."""
    if move is None:
        return

    try:
        try:
            san_move = game_state.current_board.san(move)
        except Exception:
            san_move = move.uci()

        game_state.current_board.push(move)
        game_state.move_count += 1

        print(f"✅ CV 감지된 이동 적용: {move.uci()} (SAN: {san_move})")

        wait_until_robot_idle()

        if check_time_over():
            game_state.game_over = True
            return

        if game_state.current_board.is_game_over():
            print(f"[DEBUG] 이동 후 게임 종료: {describe_game_end(game_state.current_board)}")
            game_state.game_over = True
    except Exception as exc:
        print(f"[ERROR] 이동 적용 실패: {exc}")


def cleanup_game() -> None:
    """게임 종료 후 자원 정리."""
    timer_manager = get_timer_manager()
    if getattr(timer_manager, "is_monitoring", False):
        timer_manager.stop_monitoring()
    if getattr(timer_manager, "is_connected", False):
        timer_manager.disconnect()
    print("아두이노 타이머 연결을 종료했습니다.")

    disconnect_robot_arm()
    print("로봇팔 연결을 종료했습니다.")

    shutdown_engine()

    if game_state.cv_capture_wrapper is not None:
        try:
            game_state.cv_capture_wrapper.release()
        except Exception:
            pass


def _poll_timer_button() -> Optional[str]:
    """타이머 버튼 입력을 감지하고 의미있는 이벤트로 변환."""
    try:
        raw_signal = check_timer_button()
    except Exception as exc:
        print(f"[ERROR] 타이머 입력 확인 실패: {exc}")
        time.sleep(1)
        return None

    if not raw_signal:
        return None

    if raw_signal in ("P1", "P2"):
        return "black_turn_end" if raw_signal == "P1" else "white_turn_end"

    return raw_signal

