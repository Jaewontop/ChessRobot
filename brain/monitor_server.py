#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
체스 게임 모니터링 서버
터미널 체스 게임의 상태를 외부에서 웹으로 확인 가능
"""

from flask import Flask, render_template_string, jsonify, request
import threading
import time
import json
from datetime import datetime

app = Flask(__name__)

# 게임 상태 (전역 변수로 공유)
game_state = {
    'board_fen': 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    'black_timer': 600,
    'white_timer': 600,
    'current_turn': 'white',
    'game_status': '게임 준비 중',
    'last_move': '',
    'move_count': 0,
    'last_update': datetime.now().isoformat(),
    'is_game_active': False
}

# HTML 템플릿
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>♔ 체스 게임 모니터링</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Arial', sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .content { padding: 30px; }
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .status-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            border-left: 5px solid #667eea;
        }
        .status-card h3 { color: #2c3e50; margin-bottom: 15px; }
        .status-value { font-size: 1.5em; font-weight: bold; color: #667eea; }
        .timer-display {
            font-family: 'Courier New', monospace;
            font-size: 2em;
            text-align: center;
            padding: 15px;
            background: #2c3e50;
            color: white;
            border-radius: 10px;
            margin: 10px 0;
        }
        .board-container {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
        }
        .chess-board {
            display: grid;
            grid-template-columns: repeat(8, 1fr);
            gap: 2px;
            max-width: 400px;
            margin: 0 auto;
        }
        .board-square {
            width: 50px;
            height: 50px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            border: 1px solid #ddd;
        }
        .board-square.white { background-color: #f0d9b5; }
        .board-square.black { background-color: #b58863; }
        .update-time {
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
            margin-top: 20px;
        }
        .refresh-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
            margin: 20px auto;
            display: block;
        }
        .refresh-btn:hover { transform: translateY(-2px); }
        @media (max-width: 768px) {
            .chess-board { max-width: 300px; }
            .board-square { width: 37px; height: 37px; font-size: 18px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>♔ 체스 게임 모니터링</h1>
            <p>터미널 체스 게임 실시간 상태</p>
        </div>
        
        <div class="content">
            <div class="status-grid">
                <div class="status-card">
                    <h3>게임 상태</h3>
                    <div class="status-value" id="gameStatus">{{ game_state.game_status }}</div>
                </div>
                
                <div class="status-card">
                    <h3>현재 차례</h3>
                    <div class="status-value" id="currentTurn">{{ game_state.current_turn }}</div>
                </div>
                
                <div class="status-card">
                    <h3>이동 수</h3>
                    <div class="status-value" id="moveCount">{{ game_state.move_count }}</div>
                </div>
                
                <div class="status-card">
                    <h3>마지막 이동</h3>
                    <div class="status-value" id="lastMove">{{ game_state.last_move or '없음' }}</div>
                </div>
            </div>
            
            <div class="status-card">
                <h3>타이머</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <h4 style="text-align: center; margin-bottom: 10px;">검은색</h4>
                        <div class="timer-display" id="blackTimer">{{ format_time(game_state.black_timer) }}</div>
                    </div>
                    <div>
                        <h4 style="text-align: center; margin-bottom: 10px;">흰색</h4>
                        <div class="timer-display" id="whiteTimer">{{ format_time(game_state.white_timer) }}</div>
                    </div>
                </div>
            </div>
            
            <div class="board-container">
                <h3 style="text-align: center; margin-bottom: 20px;">현재 보드 상태</h3>
                <div class="chess-board" id="chessBoard">
                    <!-- 체스보드가 여기에 생성됩니다 -->
                </div>
            </div>
            
            <button class="refresh-btn" onclick="refreshData()">새로고침</button>
            
            <div class="update-time">
                마지막 업데이트: <span id="lastUpdate">{{ game_state.last_update }}</span>
            </div>
        </div>
    </div>
    
    <script>
        // 체스 기물 유니코드
        const pieces = {
            'white': { 'P': '♙', 'R': '♖', 'N': '♘', 'B': '♗', 'Q': '♕', 'K': '♔' },
            'black': { 'P': '♟', 'R': '♜', 'N': '♞', 'B': '♝', 'Q': '♛', 'K': '♚' }
        };
        
        // FEN을 체스보드로 변환
        function updateBoard(fen) {
            const board = document.getElementById('chessBoard');
            board.innerHTML = '';
            
            const parts = fen.split(' ');
            const boardState = parts[0];
            
            let squareIndex = 0;
            for (let char of boardState) {
                if (char === '/') continue;
                
                if (char >= '1' && char <= '8') {
                    squareIndex += parseInt(char);
                } else {
                    const color = char === char.toUpperCase() ? 'white' : 'black';
                    const piece = char.toUpperCase();
                    
                    const square = document.createElement('div');
                    square.className = `board-square ${(Math.floor(squareIndex / 8) + squareIndex % 8) % 2 === 0 ? 'white' : 'black'}`;
                    square.textContent = pieces[color][piece];
                    board.appendChild(square);
                    
                    squareIndex++;
                }
            }
        }
        
        // 데이터 새로고침
        function refreshData() {
            fetch('/api/game_state')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('gameStatus').textContent = data.game_status;
                    document.getElementById('currentTurn').textContent = data.current_turn;
                    document.getElementById('moveCount').textContent = data.move_count;
                    document.getElementById('lastMove').textContent = data.last_move || '없음';
                    document.getElementById('blackTimer').textContent = formatTime(data.black_timer);
                    document.getElementById('whiteTimer').textContent = formatTime(data.white_timer);
                    document.getElementById('lastUpdate').textContent = data.last_update;
                    
                    updateBoard(data.board_fen);
                })
                .catch(error => console.error('데이터 새로고침 오류:', error));
        }
        
        // 시간 포맷팅
        function formatTime(seconds) {
            const minutes = Math.floor(seconds / 60);
            const secs = seconds % 60;
            return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        
        // 초기 보드 표시
        updateBoard('{{ game_state.board_fen }}');
        
        // 자동 새로고침 (5초마다)
        setInterval(refreshData, 5000);
    </script>
</body>
</html>
'''

def format_time(seconds):
    """초를 MM:SS 형식으로 변환"""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"

@app.route('/')
def index():
    """메인 페이지"""
    return render_template_string(HTML_TEMPLATE, 
                                game_state=game_state, 
                                format_time=format_time)

@app.route('/api/game_state')
def api_game_state():
    """게임 상태 API"""
    return jsonify(game_state)

@app.route('/api/update_board', methods=['POST'])
def api_update_board():
    """보드 상태 업데이트 API"""
    global game_state
    try:
        data = request.get_json()
        if data:
            game_state.update(data)
            game_state['last_update'] = datetime.now().isoformat()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def update_game_state(board_fen=None, black_timer=None, white_timer=None, 
                     current_turn=None, game_status=None, last_move=None, 
                     move_count=None, is_game_active=None):
    """게임 상태 업데이트 함수 (외부에서 호출)"""
    global game_state
    
    if board_fen is not None:
        game_state['board_fen'] = board_fen
    if black_timer is not None:
        game_state['black_timer'] = black_timer
    if white_timer is not None:
        game_state['white_timer'] = white_timer
    if current_turn is not None:
        game_state['current_turn'] = current_turn
    if game_status is not None:
        game_state['game_status'] = game_status
    if last_move is not None:
        game_state['last_move'] = last_move
    if move_count is not None:
        game_state['move_count'] = move_count
    if is_game_active is not None:
        game_state['is_game_active'] = is_game_active
    
    game_state['last_update'] = datetime.now().isoformat()

def start_monitor_server(host='0.0.0.0', port=5002):
    """모니터링 서버 시작"""
    print(f"♔ 체스 게임 모니터링 서버 시작")
    print(f"♔ 서버 주소: http://{host}:{port}")
    print(f"♔ 모바일에서 접속: http://[라즈베리파이_IP]:{port}")
    
    app.run(host=host, port=port, debug=False, threaded=True)

if __name__ == '__main__':
    start_monitor_server()
