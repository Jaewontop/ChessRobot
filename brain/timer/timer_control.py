from __future__ import annotations

from timer.timer_manager import (
    check_timer_button,
    get_black_timer,
    get_timer_manager,
    get_white_timer,
)


def check_time_over() -> bool:
    """타이머가 0이 된 플레이어가 있으면 즉시 게임 종료 처리."""
    try:
        black_left = get_black_timer()
        white_left = get_white_timer()
        if black_left is not None and black_left <= 0:
            print("[DEBUG] 시간 초과: 검은색 타이머 0초")
            print("⏰ 시간 초과! 흰색 승리")
            return True
        if white_left is not None and white_left <= 0:
            print("[DEBUG] 시간 초과: 흰색 타이머 0초")
            print("⏰ 시간 초과! 검은색 승리")
            return True
    except Exception as exc:
        print(f"[DEBUG] 시간 초과 검사 오류: {exc}")
    return False


def check_timer_button_press() -> str | None:
    """타이머 버튼 입력을 확인하여 턴 넘기기 신호 반환."""
    try:
        button_press = check_timer_button()
        if button_press == "P1":
            print("🔘 P1(검은색) 버튼 누름 - 턴 넘기기")
            return "black_turn_end"
        if button_press == "P2":
            print("🔘 P2(흰색) 버튼 누름 - 턴 넘기기")
            return "white_turn_end"
    except Exception as exc:
        print(f"[DEBUG] 타이머 버튼 확인 오류: {exc}")
    return None


def press_timer_button(button_id: str) -> None:
    """타이머 매니저에 직접 버튼 입력 신호를 전송."""
    try:
        get_timer_manager().send_command(button_id)
    except Exception as exc:
        print(f"[Timer] 타이머 명령 전송 실패: {exc}")


def send_timer_move_command() -> bool:
    """타이머로 이동하라는 명령 전송."""
    try:
        return get_timer_manager().send_timer_move_command()
    except Exception as exc:
        print(f"[Timer] 타이머 이동 명령 전송 실패: {exc}")
        return False


def wait_for_timer_completion(timeout: float = 10.0) -> bool:
    """타이머 완료 신호 대기."""
    try:
        return get_timer_manager().wait_for_completion(timeout=timeout)
    except Exception as exc:
        print(f"[Timer] 타이머 완료 신호 대기 실패: {exc}")
        return False

