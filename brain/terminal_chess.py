#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
터미널 기반 체스 게임 엔트리 포인트.
다른 모듈에 분산된 기능을 초기화하고 메인 루프를 실행한다.
"""

from game_flow import cleanup_game, game_loop, initialize_game
from game_state import reset_game_state

STOCKFISH_PATH = "/usr/games/stockfish"
# STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"

MONITOR_SERVER_URL = "http://localhost:5002"
ENABLE_MONITORING = True


def main() -> None:
    reset_game_state()
    try:
        if not initialize_game(STOCKFISH_PATH):
            return
        game_loop()
    except KeyboardInterrupt:
        print("\n\n게임이 중단되었습니다.")
    except Exception as exc:
        print(f"\n[!] 예상치 못한 오류: {exc}")
    finally:
        cleanup_game()


if __name__ == "__main__":
    main()
