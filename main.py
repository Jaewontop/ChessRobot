#!/usr/bin/env python3
"""
Chess Robot Web Game with python-chess
웹 브라우저에서 Stockfish와 대전할 수 있는 체스 게임
python-chess 라이브러리를 사용하여 정확한 체스 규칙 구현
"""

import sys
import os
import subprocess
import tempfile
import json
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session

# python-chess 라이브러리 import
import chess
import chess.engine

# 체스 분석기 import
from brain.chess_analyzer import ChessAnalyzer

# Flask 앱 초기화
app = Flask(__name__, 
            template_folder='brain/templates')
app.secret_key = 'chess_robot_secret_key'

# Stockfish 엔진 경로
STOCKFISH_PATH = '/opt/homebrew/bin/stockfish'

# 게임 상태 저장소
games = {}

class ChessGame:
    """체스 게임 클래스 - python-chess 사용"""
    
    def __init__(self, game_id, player_color='white', difficulty=10):
        self.game_id = game_id
        # python-chess 보드 초기화
        self.board = chess.Board()
        self.player_color = player_color
        self.difficulty = difficulty
        self.game_over = False
        self.result = None
        self.move_history = []
        self.created_at = datetime.now()
        
        # 체스 분석기 초기화
        self.analyzer = ChessAnalyzer(self.board)
        
        # 플레이어가 흑인 경우 첫 수를 Stockfish가 둠
        if player_color == 'black':
            self.make_stockfish_move()
    
    def get_fen(self):
        """현재 보드를 FEN 형식으로 반환"""
        return self.board.fen()
    
    def make_move(self, from_square, to_square, promotion=None):
        """플레이어의 수를 둡니다"""
        try:
            # 입력값 검증
            if from_square is None or to_square is None:
                return {'success': False, 'error': '시작 위치와 도착 위치가 필요합니다'}
            
            # 인덱스를 UCI 형식으로 변환
            from_uci = self._index_to_uci(from_square)
            to_uci = self._index_to_uci(to_square)
            
            # 이동 생성
            if promotion:
                move = chess.Move.from_uci(f"{from_uci}{to_uci}{promotion}")
            else:
                move = chess.Move.from_uci(f"{from_uci}{to_uci}")
            
            # 이동이 합법적인지 확인
            if move not in self.board.legal_moves:
                return {'success': False, 'error': '잘못된 이동입니다'}
            
            # 수 기록 (이동 전에 san() 호출)
            san_move = self.board.san(move)
            
            # 기물 이동
            self.board.push(move)
            
            # 수 기록
            self.move_history.append({
                'move': move.uci(),
                'san': san_move,
                'player': 'human',
                'fen': self.get_fen()
            })
            
            # 게임 상태 확인
            if self.board.is_game_over():
                self.game_over = True
                if self.board.is_checkmate():
                    self.result = "1-0" if self.player_color == 'white' else "0-1"
                elif self.board.is_stalemate():
                    self.result = "1/2-1/2"
                elif self.board.is_insufficient_material():
                    self.result = "1/2-1/2"
                elif self.board.is_fifty_moves():
                    self.result = "1/2-1/2"
                elif self.board.is_repetition():
                    self.result = "1/2-1/2"
                else:
                    self.result = "1/2-1/2"
                
                return {'success': True, 'game_over': True, 'result': self.result}
            
            # Stockfish의 응답 수
            if not self.game_over:
                self.make_stockfish_move()
            
            return {'success': True, 'game_over': self.game_over, 'result': self.result}
            
        except ValueError as e:
            return {'success': False, 'error': f'잘못된 입력: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': f'예상치 못한 오류: {str(e)}'}
    
    def make_stockfish_move(self):
        """Stockfish가 수를 둡니다"""
        if not os.path.exists(STOCKFISH_PATH) or self.game_over:
            return
        
        try:
            # 1초 딜레이 추가
            time.sleep(1)
            
            # python-chess의 engine 모듈 사용
            with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
                # 난이도 설정
                engine.configure({"Skill Level": min(self.difficulty // 2, 20)})
                
                # 최선의 수 계산
                result = engine.play(self.board, chess.engine.Limit(depth=self.difficulty))
                
                # result와 result.move가 None이 아닌지 확인
                if result and result.move:
                    # 수 기록 (이동 전에 san() 호출)
                    san_move = self.board.san(result.move)
                    self.move_history.append({
                        'move': result.move.uci(),
                        'san': san_move,
                        'player': 'stockfish',
                        'fen': self.get_fen()
                    })
                    
                    # 기물 이동
                    self.board.push(result.move)
                    
                    # 게임 상태 확인
                    if self.board.is_game_over():
                        self.game_over = True
                        if self.board.is_checkmate():
                            self.result = "1-0" if self.player_color == 'white' else "0-1"
                        elif self.board.is_stalemate():
                            self.result = "1/2-1/2"
                        elif self.board.is_insufficient_material():
                            self.result = "1/2-1/2"
                        elif self.board.is_fifty_moves():
                            self.result = "1/2-1/2"
                        elif self.board.is_repetition():
                            self.result = "1/2-1/2"
                        else:
                            self.result = "1/2-1/2"
                else:
                    print("Stockfish가 유효한 수를 찾지 못했습니다.")
            
        except Exception as e:
            print(f"Stockfish 오류: {e}")
    
    def _index_to_uci(self, index):
        """인덱스를 UCI 형식으로 변환"""
        # index가 None이거나 유효하지 않은 값인지 확인
        if index is None or not isinstance(index, int) or index < 0 or index > 63:
            raise ValueError(f"잘못된 인덱스: {index}")
        
        row = index // 8
        col = index % 8
        file = chr(ord('a') + col)
        rank = 8 - row
        return f"{file}{rank}"
    
    def _uci_to_index(self, uci_square):
        """UCI 형식을 인덱스로 변환"""
        file = ord(uci_square[0]) - ord('a')
        rank = 8 - int(uci_square[1])
        return rank * 8 + file
    
    def get_board_state(self):
        """현재 보드 상태를 반환합니다"""
        return {
            'fen': self.get_fen(),
            'game_over': self.game_over,
            'result': self.result,
            'move_history': self.move_history,
            'player_color': self.player_color,
            'current_turn': 'white' if self.board.turn else 'black',
            'is_check': self.board.is_check(),
            'legal_moves': [move.uci() for move in self.board.legal_moves]
        }
    
    def get_piece_at(self, square):
        """특정 위치의 기물을 반환합니다"""
        try:
            piece = self.board.piece_at(square)
            if piece:
                return {
                    'type': piece.symbol().lower(),
                    'color': 'white' if piece.color else 'black',
                    'symbol': piece.symbol()
                }
            return None
        except:
            return None
    


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
    from_square = data.get('from_square')
    to_square = data.get('to_square')
    promotion = data.get('promotion')  # 승급 기물
    game_id = session.get('game_id')
    
    if not game_id or game_id not in games:
        return jsonify({'success': False, 'error': '게임을 찾을 수 없습니다'})
    
    game = games[game_id]
    result = game.make_move(from_square, to_square, promotion)
    
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

@app.route('/get_piece/<int:square>')
def get_piece(square):
    """특정 위치의 기물 정보 반환"""
    game_id = session.get('game_id')
    
    if not game_id or game_id not in games:
        return jsonify({'success': False, 'error': '게임을 찾을 수 없습니다'})
    
    game = games[game_id]
    piece = game.get_piece_at(square)
    
    return jsonify({
        'success': True,
        'piece': piece
    })

@app.route('/coordinates_to_san', methods=['POST'])
def coordinates_to_san():
    """좌표를 SAN으로 변환 (자동 방향 감지)"""
    game_id = session.get('game_id')
    
    if not game_id or game_id not in games:
        return jsonify({'success': False, 'error': '게임을 찾을 수 없습니다'})
    
    data = request.get_json()
    coord1 = data.get('coord1')
    coord2 = data.get('coord2')
    promotion = data.get('promotion')
    auto_execute = data.get('auto_execute', False)  # 자동 실행 여부
    
    if not coord1 or not coord2:
        return jsonify({'success': False, 'error': '두 좌표가 모두 필요합니다'})
    
    game = games[game_id]
    
    # 체스 분석기를 사용해서 자동으로 이동 방향 감지
    result = game.analyzer.analyze_position_change(coord1, coord2, promotion)
    
    # SAN 변환에 성공하고 자동 실행이 요청된 경우
    if result['success'] and auto_execute:
        # 실제로 수를 실행
        from_coords = result['analysis']['from_coords']
        to_coords = result['analysis']['to_coords']
        
        # UCI 형식으로 이동 생성
        uci_move = f"{from_coords}{to_coords}"
        if promotion:
            uci_move += promotion
        
        try:
            move = chess.Move.from_uci(uci_move)
            
            # 이동이 합법적인지 다시 한번 확인
            if move in game.board.legal_moves:
                # SAN 표기법 생성 (이동 전에 호출)
                san_move = game.board.san(move)
                
                # 기물 이동
                game.board.push(move)
                
                # 수 기록
                game.move_history.append({
                    'move': move.uci(),
                    'san': san_move,
                    'player': 'human',
                    'fen': game.get_fen()
                })
                
                # 게임 상태 확인
                if game.board.is_game_over():
                    game.game_over = True
                    if game.board.is_checkmate():
                        game.result = "1-0" if game.player_color == 'white' else "0-1"
                    elif game.board.is_stalemate():
                        game.result = "1/2-1/2"
                    elif game.board.is_insufficient_material():
                        game.result = "1/2-1/2"
                    elif game.board.is_fifty_moves():
                        game.result = "1/2-1/2"
                    elif game.board.is_repetition():
                        game.result = "1/2-1/2"
                    else:
                        game.result = "1/2-1/2"
                
                # 체스 분석기 보드 상태 업데이트
                game.analyzer.update_board(game.board)
                
                # 자동 실행 성공 정보 추가
                result['auto_executed'] = True
                result['executed_move'] = {
                    'san': san_move,
                    'uci': uci_move,
                    'from': from_coords,
                    'to': to_coords
                }
                
                # Stockfish가 다음 수를 둘 차례인지 확인
                if not game.game_over and game.board.turn != (game.player_color == 'white'):
                    # Stockfish 차례
                    game.make_stockfish_move()
                
            else:
                result['auto_executed'] = False
                result['error'] = '이동이 합법적이지 않습니다'
                
        except Exception as e:
            result['auto_executed'] = False
            result['error'] = f'이동 실행 오류: {str(e)}'
    
    return jsonify(result)

@app.route('/reset_game')
def reset_game():
    """게임 리셋"""
    game_id = session.get('game_id')
    if game_id in games:
        del games[game_id]
    
    session.pop('game_id', None)
    return jsonify({'success': True})

def main():
    """메인 함수"""
    # Stockfish 확인
    if os.path.exists(STOCKFISH_PATH):
        print(f"[✓] Stockfish 발견: {STOCKFISH_PATH}")
    else:
        print(f"[!] Stockfish를 찾을 수 없습니다: {STOCKFISH_PATH}")
        print("[!] 체스 엔진 기능이 제한됩니다.")
    
    # python-chess 라이브러리 확인
    try:
        import chess
        print(f"[✓] python-chess 라이브러리 로드됨: {chess.__version__}")
    except ImportError as e:
        print(f"[!] python-chess 라이브러리를 찾을 수 없습니다: {e}")
        print("[!] pip install python-chess를 실행해주세요.")
        return
    
    print("♔ 웹 체스 게임 서버 시작 (python-chess 사용)")
    print("♔ 서버 주소: http://localhost:5001")
    
    app.run(debug=True, host='0.0.0.0', port=5001)

if __name__ == '__main__':
    main()
