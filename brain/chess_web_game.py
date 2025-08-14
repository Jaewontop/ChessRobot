"""
웹 체스 게임 서버
Stockfish와 대전할 수 있는 체스 게임을 제공
"""

from flask import Flask, render_template, request, jsonify, session
import chess
import chess.engine
import os
import tempfile
import subprocess
import json
from datetime import datetime
import threading
import time
import serial
import asyncio
import websockets
import json

app = Flask(__name__)
app.secret_key = 'chess_robot_secret_key'

# Stockfish 엔진 경로 (시스템에 설치된 경우)
STOCKFISH_PATH = '/opt/homebrew/bin/stockfish'

# WebSocket 클라이언트들을 저장할 set
websocket_clients = set()

# 아두이노 시리얼 연결
arduino_serial = None
arduino_port = "/dev/ttyACM0"  # 포트는 환경에 맞게 수정
arduino_baud = 9600

def connect_arduino():
    """아두이노 시리얼 연결"""
    global arduino_serial
    try:
        arduino_serial = serial.Serial(arduino_port, arduino_baud, timeout=1)
        print(f"[✓] 아두이노 연결 성공: {arduino_port}")
        return True
    except serial.SerialException as e:
        print(f"[!] 아두이노 연결 실패: {arduino_port} - {e}")
        return False

def read_arduino_data():
    """아두이노에서 타이머 데이터 읽기"""
    global arduino_serial
    if not arduino_serial:
        return None
    
    try:
        if arduino_serial.in_waiting > 0:
            data = arduino_serial.readline().decode().strip()
            if data.startswith('P1:') and ',P2:' in data:
                return data
    except Exception as e:
        print(f"[!] 아두이노 데이터 읽기 오류: {e}")
    
    return None

def broadcast_timer_data():
    """연결된 모든 WebSocket 클라이언트에 타이머 데이터 전송"""
    while True:
        try:
            timer_data = read_arduino_data()
            if timer_data:
                print(f"[→] 타이머 데이터 전송: {timer_data}")
                # 모든 WebSocket 클라이언트에 데이터 전송
                for client in websocket_clients.copy():
                    try:
                        asyncio.run(client.send(timer_data))
                    except Exception as e:
                        print(f"[!] 클라이언트 전송 오류: {e}")
                        websocket_clients.discard(client)
            
            time.sleep(1)  # 1초마다 체크
        except Exception as e:
            print(f"[!] 타이머 데이터 브로드캐스트 오류: {e}")
            time.sleep(1)

# 아두이노 연결 및 타이머 데이터 읽기 스레드 시작
def start_arduino_thread():
    """아두이노 연결 및 데이터 읽기 스레드 시작"""
    if connect_arduino():
        timer_thread = threading.Thread(target=broadcast_timer_data, daemon=True)
        timer_thread.start()
        print("[✓] 아두이노 타이머 스레드 시작")
    else:
        print("[!] 아두이노 연결 실패로 타이머 기능 비활성화")

# WebSocket 핸들러
async def websocket_handler(websocket, path):
    """WebSocket 연결 처리"""
    websocket_clients.add(websocket)
    print(f"[✓] WebSocket 클라이언트 연결 (총 {len(websocket_clients)}개)")
    
    try:
        async for message in websocket:
            # 클라이언트로부터의 메시지 처리 (필요시)
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        websocket_clients.discard(websocket)
        print(f"[✓] WebSocket 클라이언트 연결 해제 (총 {len(websocket_clients)}개)")

def start_websocket_server():
    """WebSocket 서버 시작"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    start_server = websockets.serve(websocket_handler, "0.0.0.0", 8765)
    loop.run_until_complete(start_server)
    print("[✓] WebSocket 서버 시작 (포트 8765)")
    loop.run_forever()

# WebSocket 서버를 별도 스레드에서 시작
websocket_thread = threading.Thread(target=start_websocket_server, daemon=True)
websocket_thread.start()

# Stockfish 설치 확인
def find_stockfish():
    """시스템에서 Stockfish를 찾습니다"""
    global STOCKFISH_PATH
    
    # 일반적인 설치 경로들
    possible_paths = [
        '/usr/local/bin/stockfish',
        '/usr/bin/stockfish',
        '/opt/homebrew/bin/stockfish',  # macOS Homebrew
        'stockfish',  # PATH에 있는 경우
    ]
    
    for path in possible_paths:
        try:
            result = subprocess.run([path, '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                STOCKFISH_PATH = path
                print(f"[✓] Stockfish 발견: {path}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            continue
    
    print("[!] Stockfish를 찾을 수 없습니다. 체스 엔진 기능이 제한됩니다.")
    return False

# 게임 상태 저장소
games = {}

class ChessGame:
    """체스 게임 클래스"""
    
    def __init__(self, game_id, player_color='white', difficulty=10):
        self.game_id = game_id
        self.board = chess.Board()
        self.player_color = player_color
        self.difficulty = difficulty  # 1-20 (Stockfish depth)
        self.game_over = False
        self.result = None
        self.move_history = []
        self.created_at = datetime.now()
        
        # 플레이어가 흑인 경우 첫 수를 Stockfish가 둠
        if player_color == 'black':
            self.make_stockfish_move()
    
    def make_move(self, move_uci):
        """플레이어의 수를 둡니다"""
        try:
            move = chess.Move.from_uci(move_uci)
            if move in self.board.legal_moves:
                self.board.push(move)
                self.move_history.append({
                    'move': move_uci,
                    'player': 'human',
                    'fen': self.board.fen()
                })
                
                # 게임 상태 확인
                if self.board.is_game_over():
                    self.game_over = True
                    self.result = self.get_game_result()
                    return {'success': True, 'game_over': True, 'result': self.result}
                
                # Stockfish의 응답 수
                if not self.game_over:
                    self.make_stockfish_move()
                
                return {'success': True, 'game_over': self.game_over, 'result': self.result}
            else:
                return {'success': False, 'error': '잘못된 수입니다'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def make_stockfish_move(self):
        """Stockfish가 수를 둡니다"""
        if not STOCKFISH_PATH or self.game_over:
            return
        
        try:
            # 임시 파일에 현재 보드 상태 저장
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pgn', delete=False) as f:
                f.write(self.board.pgn())
                temp_file = f.name
            
            # Stockfish 실행
            cmd = [
                STOCKFISH_PATH,
                'position', 'fen', self.board.fen(),
                'go', 'depth', str(self.difficulty)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # 임시 파일 삭제
            os.unlink(temp_file)
            
            if result.returncode == 0:
                # Stockfish의 응답에서 최선의 수 추출
                for line in result.stdout.split('\n'):
                    if line.startswith('bestmove'):
                        move_uci = line.split()[1]
                        if move_uci != '(none)':
                            move = chess.Move.from_uci(move_uci)
                            self.board.push(move)
                            self.move_history.append({
                                'move': move_uci,
                                'player': 'stockfish',
                                'fen': self.board.fen()
                            })
                            
                            # 게임 상태 확인
                            if self.board.is_game_over():
                                self.game_over = True
                                self.result = self.get_game_result()
                            break
            
        except Exception as e:
            print(f"Stockfish 오류: {e}")
    
    def get_game_result(self):
        """게임 결과를 반환합니다"""
        if self.board.is_checkmate():
            if self.board.turn == chess.WHITE:
                return "0-1" if self.player_color == 'white' else "1-0"
            else:
                return "1-0" if self.player_color == 'white' else "0-1"
        elif self.board.is_stalemate():
            return "1/2-1/2"
        elif self.board.is_insufficient_material():
            return "1/2-1/2"
        elif self.board.is_fifty_moves():
            return "1/2-1/2"
        elif self.board.is_repetition():
            return "1/2-1/2"
        else:
            return "*"
    
    def get_board_state(self):
        """현재 보드 상태를 반환합니다"""
        return {
            'fen': self.board.fen(),
            'game_over': self.game_over,
            'result': self.result,
            'move_history': self.move_history,
            'player_color': self.player_color,
            'current_turn': 'white' if self.board.turn == chess.WHITE else 'black'
        }

@app.route('/')
def index():
    """메인 페이지"""
    return render_template('chess_game.html')

@app.route('/new_game', methods=['POST'])
def new_game():
    """새 게임 시작"""
    data = request.get_json()
    player_color = data.get('player_color', 'white')
    difficulty = int(data.get('difficulty', 10))
    
    # 새 게임 ID 생성
    game_id = f"game_{len(games) + 1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 새 게임 생성
    games[game_id] = ChessGame(game_id, player_color, difficulty)
    
    # 세션에 게임 ID 저장
    session['game_id'] = game_id
    
    return jsonify({
        'success': True,
        'game_id': game_id,
        'board_state': games[game_id].get_board_state()
    })

@app.route('/make_move', methods=['POST'])
def make_move():
    """수 두기"""
    data = request.get_json()
    move_uci = data.get('move')
    game_id = session.get('game_id')
    
    if not game_id or game_id not in games:
        return jsonify({'success': False, 'error': '게임을 찾을 수 없습니다'})
    
    game = games[game_id]
    result = game.make_move(move_uci)
    
    return jsonify({
        'success': result['success'],
        'board_state': game.get_board_state(),
        'error': result.get('error')
    })

@app.route('/get_board_state')
def get_board_state():
    """현재 보드 상태 반환"""
    game_id = session.get('game_id')
    
    if not game_id or game_id not in games:
        return jsonify({'success': False, 'error': '게임을 찾을 수 없습니다'})
    
    game = games[game_id]
    return jsonify({
        'success': True,
        'board_state': game.get_board_state()
    })

@app.route('/reset_game')
def reset_game():
    """게임 리셋"""
    game_id = session.get('game_id')
    if game_id in games:
        del games[game_id]
    
    session.pop('game_id', None)
    return jsonify({'success': True})

if __name__ == '__main__':
    # Stockfish 찾기
    find_stockfish()
    
    # 아두이노 연결 및 타이머 데이터 읽기 스레드 시작
    start_arduino_thread()

    print("♔ 웹 체스 게임 서버 시작")
    print("♔ Stockfish 엔진:", "사용 가능" if STOCKFISH_PATH else "사용 불가")
    print("♔ 서버 주소: http://localhost:5001")
    
    app.run(debug=True, host='0.0.0.0', port=5001) 