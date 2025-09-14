#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stockfish 엔진 매니저
- 엔진 초기화/종료 관리
- 포지션 평가(승률/점수) 제공
- 최선 수 계산 및 적용 유틸
"""

import os
import math
import chess
import chess.engine
STOCKFISH_PATH = '/usr/games/stockfish'
#STOCKFISH_PATH = '/opt/homebrew/bin/stockfish'


class _EngineManager:
    def __init__(self):
        self._engine = None

    def ensure_engine(self) -> bool:
        if self._engine is not None:
            return True
        if not os.path.exists(STOCKFISH_PATH):
            print(f"[!] Stockfish를 찾을 수 없습니다: {STOCKFISH_PATH}")
            return False
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
            # 기본 설정 (난이도는 호출부에서 depth로 제어)
            return True
        except Exception as e:
            print(f"[!] Stockfish 초기화 실패: {e}")
            self._engine = None
            return False

    def quit(self):
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:
                pass
            self._engine = None

    @staticmethod
    def _cp_to_win_prob_white(cp: int) -> float:
        # 간단한 로지스틱: 1 / (1 + 10^(-cp/400))
        try:
            return 1.0 / (1.0 + math.pow(10.0, -cp / 400.0))
        except Exception:
            return 0.5

    def evaluate(self, board: chess.Board, depth: int = 10):
        """포지션 평가: cp/mate/백승률/추천수"""
        if not self.ensure_engine():
            return None
        try:
            info = self._engine.analyse(board, chess.engine.Limit(depth=depth))
            score = info.get('score')
            bestmove = info.get('pv', [None])[0]

            cp = None
            mate = None
            win_prob_white = None

            if score is not None:
                # 백 관점 점수
                pov = score.white()
                if pov.is_mate():
                    mate = pov.mate()
                    win_prob_white = 1.0 if mate and mate > 0 else 0.0
                else:
                    cp = pov.score(mate_score=100000)
                    win_prob_white = self._cp_to_win_prob_white(cp)

            san = None
            move_type = None
            if bestmove is not None and isinstance(bestmove, chess.Move):
                try:
                    san = board.san(bestmove)
                except Exception:
                    san = bestmove.uci() if bestmove else None
                
                # 움직임의 종류 분석
                move_type = self._analyze_move_type(board, bestmove)

            return {
                'cp': cp,
                'mate': mate,
                'win_prob_white': win_prob_white,
                'best_move': bestmove.uci() if isinstance(bestmove, chess.Move) else None,
                'best_move_san': san,
                'move_type': move_type,
            }
        except Exception as e:
            print(f"[!] 평가 실패: {e}")
            return None

    def _analyze_move_type(self, board: chess.Board, move: chess.Move) -> dict:
        """움직임의 종류를 분석하여 상세 정보 반환"""
        move_info = {
            'is_capture': False,
            'is_castling': False,
            'is_en_passant': False,
            'is_promotion': False,
            'is_check': False,
            'piece_type': None,
            'captured_piece': None,
            'promotion_piece': None
        }
        
        try:
            # 기물 잡기 여부
            if board.is_capture(move):
                move_info['is_capture'] = True
                # 잡힌 기물 확인
                captured_square = move.to_square
                if board.is_en_passant(move):
                    # 앙파상인 경우 잡힌 폰의 위치
                    captured_square = move.from_square + (8 if board.turn else -8)
                move_info['captured_piece'] = board.piece_at(captured_square)
            
            # 앙파상 여부
            if board.is_en_passant(move):
                move_info['is_en_passant'] = True
            
            # 캐슬링 여부
            if board.is_castling(move):
                move_info['is_castling'] = True
            
            # 프로모션 여부
            if move.promotion:
                move_info['is_promotion'] = True
                move_info['promotion_piece'] = move.promotion
            
            # 움직이는 기물 타입
            piece = board.piece_at(move.from_square)
            if piece:
                move_info['piece_type'] = piece.piece_type
            
            # 체크 여부 (움직임을 실행해서 확인)
            board_copy = board.copy()
            board_copy.push(move)
            move_info['is_check'] = board_copy.is_check()
            
        except Exception as e:
            print(f"[!] 움직임 분석 실패: {e}")
        
        return move_info

    def play_best(self, board: chess.Board, depth: int = 10):
        """최선 수 실행. 성공 시 (move, san) 반환"""
        if not self.ensure_engine():
            return None
        try:
            result = self._engine.play(board, chess.engine.Limit(depth=depth))
            if result and result.move:
                move = result.move
                try:
                    san = board.san(move)
                except Exception:
                    san = move.uci()
                board.push(move)
                return move, san
            return None
        except Exception as e:
            print(f"[!] 엔진 수 계산 실패: {e}")
            return None


_manager = _EngineManager()


def init_engine() -> bool:
    return _manager.ensure_engine()


def shutdown_engine():
    _manager.quit()


def evaluate_position(board: chess.Board, depth: int = 10):
    return _manager.evaluate(board, depth)


def engine_make_best_move(board: chess.Board, depth: int = 10):
    return _manager.play_best(board, depth)


