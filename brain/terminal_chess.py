#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
터미널 기반 체스 게임
아두이노 타이머와 연동하여 터미널에서 체스 게임 진행
모니터링 서버와 연동하여 외부에서 게임 상태 확인 가능
로봇팔 제어를 위한 움직임 분석 및 명령 전송 기능 포함
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
    get_chess_timer_status,
    check_timer_button
)
from engine_manager import (
    init_engine,
    shutdown_engine,
    evaluate_position,
    engine_make_best_move,
)
from robot_arm_controller import (
    init_robot_arm,
    connect_robot_arm,
    disconnect_robot_arm,
    execute_robot_move,
    configure_robot_arm,
    get_robot_status,
    test_robot_connection,
    is_robot_moving,
    get_move_description
)
from move_analyzer import (
    analyze_coordinates,
    analyze_move_with_context,
    suggest_move,
    get_all_possible_moves
)
from piece_detector import detect_move_and_update

# Stockfish 경로
#STOCKFISH_PATH = '/usr/games/stockfish'
STOCKFISH_PATH = '/opt/homebrew/bin/stockfish'

# 모니터링 서버 설정
MONITOR_SERVER_URL = 'http://localhost:5002'
ENABLE_MONITORING = True

# 게임 상태
current_board = chess.Board()
player_color = 'white'
difficulty = 15
game_over = False
move_count = 0

# 로봇팔 제어 설정 (robot_arm_controller에서 관리)

def display_board():
    """체스보드를 터미널에 표시"""
    #os.system('clear')
    print("♔ 터미널 체스 게임 ♔")
    print("=" * 50)
    
    # 타이머 표시
    print(f"{get_timer_display()}")
    
    # 로봇팔 상태 표시
    if is_robot_moving():
        print("🤖 로봇이 움직이는 중...")
    else:
        robot_status = get_robot_status()
        if robot_status['is_connected']:
            print("🤖 로봇팔 대기 중")
        else:
            print("🤖 로봇팔 연결 안됨")
    
    print("-" * 50)

    # 엔진 평가 표시 (승률/점수/권장수)
    try:
        eval_data = evaluate_position(current_board, depth=difficulty)
        if eval_data:
            wp = eval_data.get('win_prob_white')
            cp = eval_data.get('cp')
            mate = eval_data.get('mate')
            best_san = eval_data.get('best_move_san')
            best_move = eval_data.get('best_move')
            move_type = eval_data.get('move_type')
            
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
            
            # 움직임 타입 정보 표시 (정보만 표시, 명령 전송 없음)
            if move_type and best_move:
                move_type_names = {
                    'normal': '일반 이동',
                    'capture': '기물 잡기',
                    'en_passant': '앙파상',
                    'castling': '캐슬링',
                    'promotion': '프로모션'
                }
                move_type_name = move_type_names.get('unknown', '알 수 없음')
                
                # move_type에서 실제 타입 확인
                if move_type.get('is_castling'):
                    move_type_name = '캐슬링'
                elif move_type.get('is_en_passant'):
                    move_type_name = '앙파상'
                elif move_type.get('is_capture'):
                    move_type_name = '기물 잡기'
                elif move_type.get('is_promotion'):
                    move_type_name = '프로모션'
                else:
                    move_type_name = '일반 이동'
                
                print(f"움직임 타입: {move_type_name}")
            
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

def check_timer_button_press():
    """타이머 버튼 입력을 확인하여 턴 넘기기 신호 반환"""
    try:
        button_press = check_timer_button()
        if button_press:
            if button_press == 'P1':
                print("🔘 P1(검은색) 버튼 누름 - 턴 넘기기")
                return 'black_turn_end'
            elif button_press == 'P2':
                print("🔘 P2(흰색) 버튼 누름 - 턴 넘기기")
                return 'white_turn_end'
    except Exception as e:
        print(f"[DEBUG] 타이머 버튼 확인 오류: {e}")
    return None

def get_move_from_user():
    """CV로 기물 이동 자동 감지 (타이머 버튼으로 턴 넘기기 가능)"""
    print("📹 체스판에서 기물을 움직여주세요... (타이머 버튼으로 턴 넘기기, Ctrl+C로 게임 종료)")
    
    while True:
        try:
            # 타이머 버튼 입력 확인 (턴 넘기기)
            button_signal = check_timer_button_press()
            if button_signal:
                current_turn = 'white' if current_board.turn == chess.WHITE else 'black'
                
                # 현재 턴 플레이어가 버튼을 누르면 턴 넘기기
                if (button_signal == 'white_turn_end' and current_turn == 'white') or \
                   (button_signal == 'black_turn_end' and current_turn == 'black'):
                    print(f"🔘 {current_turn} 플레이어가 타이머를 눌러 턴을 넘겼습니다!")
                    return 'skip_turn'
                else:
                    print(f"⚠️  잘못된 타이밍입니다. 현재는 {current_turn} 차례입니다.")
            
            # CV로 기물 변화 감지
            move_input = detect_move_and_update(None, '../CV/init_board_values.npy')
            
            if not move_input:
                # print("❌ CV에서 기물 변화를 감지하지 못했습니다. 다시 시도하세요.")
                time.sleep(0.1)  # 짧은 대기
                continue
                
            print(f"📹 CV 감지 결과: {move_input}")
            
            if len(move_input) == 4:
                # 두 좌표 추출
                coord1 = move_input[:2]
                coord2 = move_input[2:]
                
                # 움직임 분석 (순서 자동 판단)
                #TODO: CV에서 coord1,coord2 받아와서 집어넣기 a1,a2
                move_tuple = analyze_coordinates(current_board, coord1, coord2)
                
                if move_tuple:
                    from_square, to_square = move_tuple
                    
                    # 분석 결과 표시
                    suggestion = suggest_move(current_board, coord1, coord2)
                    print(f"🤖 {suggestion}")
                    
                    # 이동 유효성 검사
                    from_sq = chess.parse_square(from_square)
                    to_sq = chess.parse_square(to_square)
                    move = chess.Move(from_sq, to_sq)
                    
                    if move in current_board.legal_moves:
                        return move
                    else:
                        print("❌ 잘못된 이동입니다!")
                else:
                    print("❌ 유효하지 않은 움직임입니다!")
                    print("💡 가능한 움직임들:")
                    possible_moves = get_all_possible_moves(current_board)
                    for i, move_info in enumerate(possible_moves[:5], 1):  # 상위 5개만 표시
                        print(f"   {i}. {move_info['piece']}: {move_info['from']} → {move_info['to']} ({move_info['type']})")
                    if len(possible_moves) > 5:
                        print(f"   ... 총 {len(possible_moves)}개 움직임 가능")
            else:
                print("❌ 올바른 형식으로 입력하세요 (예: e2e4 또는 e4e2)")
                
        except ValueError:
            print("❌ 잘못된 좌표입니다!")
        except KeyboardInterrupt:
            return 'quit'

def make_stockfish_move():
    """Stockfish가 수를 두도록 함 (engine_manager 사용)"""
    try:
        # Stockfish 차례일 때만 로봇팔 명령 분석 및 전송
        # 움직임 전에 현재 보드 상태에서 최선의 수 분석
        eval_data = evaluate_position(current_board, depth=difficulty)
        if eval_data and eval_data.get('best_move'):
            best_move = eval_data['best_move']
            move_type = eval_data.get('move_type')
            
            # 로봇팔 명령 분석 및 실행 (연결 상태와 관계없이)
            if move_type:
                move_desc = get_move_description(move_type, best_move)
                print(f"🤖 {move_desc} 실행 중...")
                
                # 로봇팔 명령 실행 (연결되지 않아도 명령 분석 및 표시)
                success = execute_robot_move(move_type, best_move)
                if success:
                    robot_status = get_robot_status()
                    if robot_status['is_connected']:
                        print("✅ 로봇팔 명령 전송 성공")
                    else:
                        print("✅ 명령 분석 완료 (로봇팔 미연결)")
                else:
                    print("❌ 로봇팔 명령 실행 실패")
        
        # 실제 움직임 실행
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
    
    # 로봇팔 초기화
    print(f"[→] 로봇팔 초기화 중...")
    init_robot_arm(enabled=True, port='/dev/ttyUSB0', baudrate=9600)
    
    # 로봇팔 연결 시도
    if test_robot_connection():
        print("[✓] 로봇팔 연결 테스트 성공")
        if connect_robot_arm():
            print("[✓] 로봇팔 연결 완료")
        else:
            print("[!] 로봇팔 연결 실패 - 명령 전송 없이 진행")
    else:
        print("[!] 로봇팔 연결 테스트 실패 - 명령 전송 없이 진행")
    
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
        
        # 타이머 버튼 입력 확인 (수를 둔 후 턴 넘기기 신호)
        button_signal = check_timer_button_press()
        if button_signal:
            current_turn = 'white' if current_board.turn == chess.WHITE else 'black'
            previous_turn = 'black' if current_board.turn == chess.WHITE else 'white'
            
            # 이전 턴 플레이어가 버튼을 눌렀는지 확인 (수를 둔 후 턴 종료 신호)
            if (button_signal == 'white_turn_end' and previous_turn == 'white') or \
               (button_signal == 'black_turn_end' and previous_turn == 'black'):
                print(f"🔘 {previous_turn} 플레이어가 수를 두고 타이머를 눌렀습니다!")
                print(f"🔄 이제 {current_turn} 플레이어 차례입니다.")
                time.sleep(1)
            elif (button_signal == 'white_turn_end' and current_turn == 'white') or \
                 (button_signal == 'black_turn_end' and current_turn == 'black'):
                print(f"⚠️  {current_turn} 플레이어는 먼저 수를 두어야 합니다!")
                time.sleep(1)
            else:
                print(f"⚠️  잘못된 타이밍입니다. 현재는 {current_turn} 차례입니다.")
                time.sleep(1)
        
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
            elif move == 'skip_turn':
                print("⚠️  체스에서는 턴을 넘길 수 없습니다. 반드시 수를 두어야 합니다.")
                print("🔄 다시 기물을 움직여주세요.")
                continue
            
            try:
                san_user = current_board.san(move)
            except Exception:
                san_user = move.uci()
            print(f"[DEBUG] 사용자 수 입력: {move.uci()} (SAN: {san_user})")
            
            # 사용자 움직임 실행 (로봇팔 명령 전송 없음)
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
        # Stockfish 차례
        else:
            print("🤖 Stockfish가 생각 중...")
            
            # 로봇팔이 연결되어 있고 움직이는 중이면 대기
            robot_status = get_robot_status()
            if robot_status['is_connected'] and is_robot_moving():
                print("🤖 로봇팔이 움직이는 중입니다. 잠시 대기...")
                while is_robot_moving():
                    time.sleep(0.5)
                print("🤖 로봇팔 움직임 완료!")
            
            if make_stockfish_move():
                move_count += 1
                print(f"✅ Stockfish 이동 완료")

                # 시간 초과 검사 (엔진 수 후)
                if check_time_over():
                    game_over = True
                    break
                
            else:
                print("❌ Stockfish 이동 실패 - 다음 턴으로 계속 진행")
                time.sleep(0.5)
                continue
        
        time.sleep(0.1)  # 타이머 버튼 확인을 위해 대기 시간 단축
    
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
        
        # 로봇팔 연결 해제
        disconnect_robot_arm()
        print("로봇팔 연결을 종료했습니다.")
        
        # 엔진 종료
        shutdown_engine()
