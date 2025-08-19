#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
터미널 기반 체스 게임
아두이노 타이머와 연동하여 터미널에서 체스 게임 진행
모니터링 서버와 연동하여 외부에서 게임 상태 확인 가능
"""

import os
import sys
import time
import chess
import chess.engine
import requests
from datetime import datetime
from timer_manager import (
    get_timer_manager, 
    get_timer_display, 
    get_black_timer, 
    get_white_timer,
    init_chess_timer,
    get_chess_timer_status
)
from engine_manager import (
    init_engine,
    shutdown_engine,
    evaluate_position,
    engine_make_best_move,
)

# Stockfish 경로
STOCKFISH_PATH = '/usr/games/stockfish'

# 모니터링 서버 설정
MONITOR_SERVER_URL = 'http://localhost:5002'
ENABLE_MONITORING = True

# 게임 상태
current_board = chess.Board()
player_color = 'white'
difficulty = 15
game_over = False
move_count = 0



def update_monitor_server(board_fen=None, black_timer=None, white_timer=None, 
                         current_turn=None, game_status=None, last_move=None, 
                         move_count=None, is_game_active=None):
    """모니터링 서버에 게임 상태 업데이트"""
    if not ENABLE_MONITORING:
        return
    
    try:
        data = {}
        if board_fen is not None:
            data['board_fen'] = board_fen
        if black_timer is not None:
            data['black_timer'] = black_timer
        if white_timer is not None:
            data['white_timer'] = white_timer
        if current_turn is not None:
            data['current_turn'] = current_turn
        if game_status is not None:
            data['game_status'] = game_status
        if last_move is not None:
            data['last_move'] = last_move
        if move_count is not None:
            data['move_count'] = move_count
        if is_game_active is not None:
            data['is_game_active'] = is_game_active
        
        # if data:
        #     response = requests.post(f"{MONITOR_SERVER_URL}/api/update_board", 
        #                           json=data, timeout=1)
        #     if response.status_code == 200:
        #         print(f"[✓] 모니터링 서버 업데이트 성공")
        #     else:
        #         print(f"[!] 모니터링 서버 업데이트 실패: {response.status_code}")
    except Exception as e:
        print(f"[!] 모니터링 서버 연결 오류: {e}")

def display_board():
    """체스보드를 터미널에 표시"""
    os.system('clear')
    print("♔ 터미널 체스 게임 ♔")
    print("=" * 50)
    
    # 타이머 표시
    print(f"{get_timer_display()}")
    print("-" * 50)

    # 엔진 평가 표시 (승률/점수/권장수)
    try:
        eval_data = evaluate_position(current_board, depth=difficulty)
        if eval_data:
            wp = eval_data.get('win_prob_white')
            cp = eval_data.get('cp')
            mate = eval_data.get('mate')
            best_san = eval_data.get('best_move_san')
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
            print("-" * 50)
    except Exception as _e:
        # 평가 실패 시 조용히 넘어감
        pass
    
    # 체스보드 표시
    board_str = str(current_board)
    lines = board_str.split('\n')
    
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
    
    # 게임 상태 표시
    if current_board.is_checkmate():
        print("♔ 체크메이트!")
        if current_board.turn == chess.WHITE:
            print("검은색 승리!")
        else:
            print("흰색 승리!")
    elif current_board.is_stalemate():
        print("⚖️ 스테일메이트 - 무승부!")
    elif current_board.is_check():
        print("⚡ 체크!")
    
    # 현재 차례 표시
    turn = "흰색" if current_board.turn == chess.WHITE else "검은색"
    print(f"현재 차례: {turn}")
    print("-" * 50)

def describe_game_end(board: chess.Board) -> str:
    """게임 종료 사유를 사람이 읽기 쉬운 문자열로 반환"""
    if board.is_checkmate():
        return "체크메이트"
    if board.is_stalemate():
        return "스테일메이트"
    if board.is_insufficient_material():
        return "기물 부족 무승부"
    if board.is_fifty_moves() or board.can_claim_fifty_moves():
        return "오십수 규칙 무승부"
    if board.is_repetition() or board.can_claim_threefold_repetition():
        return "삼중 반복 무승부"
    return "게임 종료"

def check_time_over() -> bool:
    """타이머가 0이 된 플레이어가 있으면 즉시 게임 종료 처리"""
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
    except Exception as e:
        print(f"[DEBUG] 시간 초과 검사 오류: {e}")
    return False

def get_move_from_user():
    """사용자로부터 이동 입력 받기"""
    while True:
        try:
            move_input = input("이동 입력 (예: e2e4, q to quit): ").strip().lower()
            
            if move_input == 'q':
                return 'quit'
            
            if len(move_input) == 4:
                #TODO: 나중에 여기 CV에서 받아온 두 좌표로 집어넣기
                from_square = chess.parse_square(move_input[:2])
                to_square = chess.parse_square(move_input[2:])
                
                # 이동 유효성 검사
                move = chess.Move(from_square, to_square)
                if move in current_board.legal_moves:
                    return move
                else:
                    print("❌ 잘못된 이동입니다!")
            else:
                print("❌ 올바른 형식으로 입력하세요 (예: e2e4)")
                
        except ValueError:
            print("❌ 잘못된 좌표입니다!")
        except KeyboardInterrupt:
            return 'quit'

def make_stockfish_move():
    """Stockfish가 수를 두도록 함 (engine_manager 사용)"""
    try:
        moved = engine_make_best_move(current_board, depth=difficulty)
        if moved:
            move, san = moved
            print(f"[DEBUG] Stockfish 선택 수: {move.uci()} (SAN: {san})")
            if current_board.is_game_over():
                print(f"[DEBUG] 엔진 수 이후 게임 종료: {describe_game_end(current_board)}")
            return True
        else:
            print("[DEBUG] Stockfish가 유효한 수를 반환하지 않았습니다")
            return False
    except Exception as e:
        print(f"[!] Stockfish 오류: {e}")
        return False



def main():
    """메인 게임 루프"""
    global current_board, player_color, game_over, move_count
    
    print("♔ 터미널 체스 게임 시작 ♔")
    print("=" * 50)
    
    # Stockfish 확인
    if not os.path.exists(STOCKFISH_PATH):
        print(f"[!] Stockfish를 찾을 수 없습니다: {STOCKFISH_PATH}")
        print("[!] 체스 엔진 기능이 제한됩니다.")
        return
    # 엔진 초기화
    init_engine()
    
    # 아두이노 타이머 연결
    print(f"[→] 아두이노 타이머 연결 시도 중...")
    if not init_chess_timer():
        print("[!] 아두이노 타이머 연결 실패 - 타이머 없이 진행")
    else:
        print(f"[✓] 아두이노 타이머 연결 및 모니터링 시작 완료")
        # 타이머 상태 확인
        status = get_chess_timer_status()
        print(f"[→] 타이머 상태: {status}")
    
    # 플레이어 색상 선택
    while True:
        color_input = input("색상 선택 (w: 흰색, b: 검은색): ").strip().lower()#TODO: 나중에 CV에서 받아온 색상으로 집어넣기
        if color_input in ['w', 'b']:
            player_color = 'white' if color_input == 'w' else 'black'
            break
        print("❌ w 또는 b를 입력하세요!")
    
    # 난이도 고정 (프롬프트 제거)
    difficulty = 15
    print("[→] 난이도: 15 (고정)")
    
    print(f"게임 설정: {player_color} 플레이어, 난이도 {difficulty}")
    
    # 게임 시작 전 보드 상태 확인
    print(f"[→] 초기 보드 상태 확인 중...")
    print(f"[→] 게임 종료 여부: {current_board.is_game_over()}")
    print(f"[→] 현재 차례: {'흰색' if current_board.turn == chess.WHITE else '검은색'}")
    
    # 모니터링 서버 초기화
    if ENABLE_MONITORING:
        print(f"[→] 모니터링 서버 초기화 중...")
        update_monitor_server(
            board_fen=current_board.fen(),
            black_timer=get_black_timer(),
            white_timer=get_white_timer(),
            current_turn="white",
            game_status="게임 시작",
            move_count=0,
            is_game_active=True
        )
        print(f"[✓] 모니터링 서버 초기화 완료")
        print(f"[→] 모바일에서 확인: http://[라즈베리파이_IP]:5002")
    
    # 플레이어가 검은색인 경우 Stockfish가 첫 수를 둠
    if player_color == 'black':
        print("🤖 Stockfish가 첫 수를 둡니다...")
        make_stockfish_move()
    
    # 게임 루프
    while not game_over:
        display_board()
        print(f"[DEBUG] 루프 시작 - 차례: {'백' if current_board.turn == chess.WHITE else '흑'}, FEN: {current_board.fen()}")

        # 시간 초과 우선 검사
        if check_time_over():
            game_over = True
            break
        
        # 게임 종료 확인 (디버깅 정보 추가)
        if current_board.is_game_over():
            print(f"[DEBUG] 게임 종료 조건 만족!")
            print(f"[DEBUG] 체크메이트: {current_board.is_checkmate()}")
            print(f"[DEBUG] 스테일메이트: {current_board.is_stalemate()}")
            print(f"[DEBUG] 체크: {current_board.is_check()}")
            game_over = True
            break
        
        # 사용자 차례
        if (current_board.turn == chess.WHITE and player_color == 'white') or \
           (current_board.turn == chess.BLACK and player_color == 'black'):
            
            move = get_move_from_user()
            if move == 'quit':
                print("게임을 종료합니다.")
                break
            
            try:
                san_user = current_board.san(move)
            except Exception:
                san_user = move.uci()
            print(f"[DEBUG] 사용자 수 입력: {move.uci()} (SAN: {san_user})")
            current_board.push(move)
            move_count += 1
            print(f"✅ 이동: {move}")
            # 시간 초과 검사 (사용자 수 후)
            if check_time_over():
                game_over = True
                break

            if current_board.is_game_over():
                print(f"[DEBUG] 사용자 수 이후 게임 종료: {describe_game_end(current_board)}")
                game_over = True
                break
            
            # 모니터링 서버에 이동 정보 업데이트
            # update_monitor_server(
            #     last_move=str(move),
            #     move_count=move_count,
            #     black_timer=get_black_timer(),
            #     white_timer=get_white_timer()
            # )
            
        # Stockfish 차례
        else:
            print("🤖 Stockfish가 생각 중...")
            if make_stockfish_move():
                move_count += 1
                print(f"✅ Stockfish 이동 완료")

                # 시간 초과 검사 (엔진 수 후)
                if check_time_over():
                    game_over = True
                    break
                
                # 모니터링 서버에 이동 정보 업데이트
                # update_monitor_server(
                #     last_move="Stockfish",
                #     move_count=move_count,
                #     black_timer=get_black_timer(),
                #     white_timer=get_white_timer()
                # )
            else:
                print("❌ Stockfish 이동 실패 - 다음 턴으로 계속 진행")
                time.sleep(0.5)
                continue
        
        time.sleep(1)
    
    # 최종 보드 표시
    display_board()
    print("게임 종료!")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n게임이 중단되었습니다.")
    except Exception as e:
        print(f"\n[!] 예상치 못한 오류: {e}")
    finally:
        # 타이머 매니저 정리
        timer_manager = get_timer_manager()
        if timer_manager.is_monitoring:
            timer_manager.stop_monitoring()
        if timer_manager.is_connected:
            timer_manager.disconnect()
        print("아두이노 타이머 연결을 종료했습니다.")
        # 엔진 종료
        shutdown_engine()
