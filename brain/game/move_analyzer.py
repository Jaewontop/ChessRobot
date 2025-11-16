#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
체스 움직임 분석 모듈
두 좌표를 보고 출발지(from)와 도착지(to)를 자동으로 판단
"""

import chess
from typing import Tuple, Optional, Dict

class MoveAnalyzer:
    """체스 움직임 분석 클래스"""
    
    def __init__(self):
        # 기물의 기본 위치 (초기 배치)
        self.initial_positions = {
            'white': {
                'pawns': ['a2', 'b2', 'c2', 'd2', 'e2', 'f2', 'g2', 'h2'],
                'rooks': ['a1', 'h1'],
                'knights': ['b1', 'g1'],
                'bishops': ['c1', 'f1'],
                'queen': ['d1'],
                'king': ['e1']
            },
            'black': {
                'pawns': ['a7', 'b7', 'c7', 'd7', 'e7', 'f7', 'g7', 'h7'],
                'rooks': ['a8', 'h8'],
                'knights': ['b8', 'g8'],
                'bishops': ['c8', 'f8'],
                'queen': ['d8'],
                'king': ['e8']
            }
        }
    
    def analyze_coordinates(self, board: chess.Board, coord1: str, coord2: str) -> Optional[Tuple[str, str]]:
        """
        두 좌표를 보고 출발지(from)와 도착지(to)를 판단
        
        Args:
            board: 현재 체스 보드 상태
            coord1: 첫 번째 좌표 (예: 'e2')
            coord2: 두 번째 좌표 (예: 'e4')
        
        Returns:
            (from_square, to_square) 튜플 또는 None (유효하지 않은 경우)
        """
        if not self._is_valid_square(coord1) or not self._is_valid_square(coord2):
            return None
        
        # 두 좌표가 같은 경우
        if coord1 == coord2:
            return None
        
        # 각 좌표에 기물이 있는지 확인
        square1 = chess.parse_square(coord1)
        square2 = chess.parse_square(coord2)
        
        piece1 = board.piece_at(square1)
        piece2 = board.piece_at(square2)
        
        # 가능한 움직임 조합들
        possibilities = [
            (coord1, coord2),  # coord1 -> coord2
            (coord2, coord1)   # coord2 -> coord1
        ]
        
        # 각 가능성을 검사
        for from_square, to_square in possibilities:
            if self._is_valid_move(board, from_square, to_square):
                return (from_square, to_square)
        
        return None
    
    def _is_valid_square(self, coord: str) -> bool:
        """좌표가 유효한 체스 좌표인지 확인"""
        if len(coord) != 2:
            return False
        
        file = coord[0].lower()  # a-h
        rank = coord[1]          # 1-8
        
        return file in 'abcdefgh' and rank in '12345678'
    
    def _is_valid_move(self, board: chess.Board, from_square: str, to_square: str) -> bool:
        """주어진 움직임이 유효한지 확인"""
        try:
            from_sq = chess.parse_square(from_square)
            to_sq = chess.parse_square(to_square)
            
            # 출발지에 기물이 있는지 확인
            piece = board.piece_at(from_sq)
            if not piece:
                return False
            
            # 현재 차례의 기물인지 확인
            if piece.color != board.turn:
                return False
            
            # 움직임이 합법적인지 확인
            move = chess.Move(from_sq, to_sq)
            return move in board.legal_moves
            
        except (ValueError, AttributeError):
            return False
    
    def analyze_move_with_context(self, board: chess.Board, coord1: str, coord2: str) -> Dict:
        """
        움직임을 분석하고 상세 정보 반환
        
        Returns:
            {
                'from_square': str,
                'to_square': str,
                'piece_type': str,
                'move_type': str,
                'is_valid': bool,
                'reason': str
            }
        """
        result = {
            'from_square': None,
            'to_square': None,
            'piece_type': None,
            'move_type': None,
            'is_valid': False,
            'reason': ''
        }
        
        # 좌표 유효성 검사
        if not self._is_valid_square(coord1) or not self._is_valid_square(coord2):
            result['reason'] = '유효하지 않은 좌표 형식'
            return result
        
        if coord1 == coord2:
            result['reason'] = '출발지와 도착지가 같습니다'
            return result
        
        # 움직임 분석
        move_tuple = self.analyze_coordinates(board, coord1, coord2)
        if not move_tuple:
            result['reason'] = '유효하지 않은 움직임입니다'
            return result
        
        from_square, to_square = move_tuple
        result['from_square'] = from_square
        result['to_square'] = to_square
        result['is_valid'] = True
        
        # 기물 정보
        from_sq = chess.parse_square(from_square)
        piece = board.piece_at(from_sq)
        if piece:
            result['piece_type'] = self._get_piece_name(piece.piece_type, piece.color)
        
        # 움직임 타입 분석
        move = chess.Move(from_sq, chess.parse_square(to_square))
        result['move_type'] = self._get_move_type(board, move)
        result['reason'] = '유효한 움직임입니다'
        
        return result
    
    def _get_piece_name(self, piece_type: int, color: bool) -> str:
        """기물 타입을 한글로 반환"""
        piece_names = {
            chess.PAWN: '폰',
            chess.KNIGHT: '나이트',
            chess.BISHOP: '비숍',
            chess.ROOK: '룩',
            chess.QUEEN: '퀸',
            chess.KING: '킹'
        }
        
        color_name = '흰색' if color else '검은색'
        piece_name = piece_names.get(piece_type, '알 수 없음')
        
        return f"{color_name} {piece_name}"
    
    def _get_move_type(self, board: chess.Board, move: chess.Move) -> str:
        """움직임의 타입을 반환"""
        if board.is_castling(move):
            return '캐슬링'
        elif board.is_en_passant(move):
            return '앙파상'
        elif board.is_capture(move):
            return '기물 잡기'
        elif move.promotion:
            return '프로모션'
        else:
            return '일반 이동'
    
    def suggest_move(self, board: chess.Board, coord1: str, coord2: str) -> str:
        """사용자에게 움직임을 제안하는 메시지 생성"""
        analysis = self.analyze_move_with_context(board, coord1, coord2)
        
        if not analysis['is_valid']:
            return f"❌ {analysis['reason']}"
        
        from_sq = analysis['from_square']
        to_sq = analysis['to_square']
        piece = analysis['piece_type']
        move_type = analysis['move_type']
        
        return f"✅ {piece}을(를) {from_sq}에서 {to_sq}로 {move_type}"
    
    def get_all_possible_moves(self, board: chess.Board) -> list:
        """현재 보드에서 가능한 모든 움직임 반환"""
        legal_moves = []
        
        for move in board.legal_moves:
            from_square = chess.square_name(move.from_square)
            to_square = chess.square_name(move.to_square)
            
            # 기물 정보
            piece = board.piece_at(move.from_square)
            piece_name = self._get_piece_name(piece.piece_type, piece.color) if piece else '알 수 없음'
            
            # 움직임 타입
            move_type = self._get_move_type(board, move)
            
            legal_moves.append({
                'from': from_square,
                'to': to_square,
                'piece': piece_name,
                'type': move_type,
                'uci': move.uci(),
                'san': board.san(move) if board.is_legal(move) else 'N/A'
            })
        
        return legal_moves


# 전역 인스턴스
_move_analyzer = MoveAnalyzer()

def analyze_coordinates(board: chess.Board, coord1: str, coord2: str) -> Optional[Tuple[str, str]]:
    """두 좌표를 보고 출발지와 도착지 판단"""
    return _move_analyzer.analyze_coordinates(board, coord1, coord2)

def analyze_move_with_context(board: chess.Board, coord1: str, coord2: str) -> Dict:
    """움직임을 분석하고 상세 정보 반환"""
    return _move_analyzer.analyze_move_with_context(board, coord1, coord2)

def suggest_move(board: chess.Board, coord1: str, coord2: str) -> str:
    """사용자에게 움직임 제안 메시지 생성"""
    return _move_analyzer.suggest_move(board, coord1, coord2)

def get_all_possible_moves(board: chess.Board) -> list:
    """현재 보드에서 가능한 모든 움직임 반환"""
    return _move_analyzer.get_all_possible_moves(board)
