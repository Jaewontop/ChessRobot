#!/usr/bin/env python3
"""
Chess Position Analyzer
체스 보드의 위치 변화를 분석하고 SAN 표기법으로 변환하는 모듈
"""

import chess
from typing import Dict, List, Tuple, Optional


class ChessAnalyzer:
    """체스 보드 분석 및 SAN 변환 클래스"""
    
    def __init__(self, board: chess.Board):
        """
        초기화
        
        Args:
            board: python-chess 보드 객체
        """
        self.board = board
        self.previous_board = board.copy() if board else None
    
    def analyze_position_change(self, coord1: str, coord2: str, promotion: Optional[str] = None) -> Dict:
        """
        두 좌표를 분석해서 어떤 기물이 어디로 이동했는지 판단하고 SAN으로 변환
        
        Args:
            coord1 (str): 첫 번째 좌표 (예: 'e2')
            coord2 (str): 두 번째 좌표 (예: 'e4')
            promotion (str, optional): 승급 기물 (예: 'q', 'r', 'b', 'n')
        
        Returns:
            dict: 분석 결과
        """
        try:
            # 좌표 유효성 검사
            if not self._is_valid_coordinate(coord1) or not self._is_valid_coordinate(coord2):
                return {
                    'success': False,
                    'error': '잘못된 좌표 형식입니다. (예: e2, a1)'
                }
            
            # 두 좌표를 정수 인덱스로 변환
            square1 = chess.parse_square(coord1)
            square2 = chess.parse_square(coord2)
            
            # 각 좌표에 있는 기물 확인
            piece1 = self.board.piece_at(square1)
            piece2 = self.board.piece_at(square2)
            
            # 이동 방향과 기물 정보를 바탕으로 from/to 판단
            from_coords, to_coords, moved_piece = self._determine_move_direction(
                coord1, coord2, piece1, piece2
            )
            
            if not from_coords or not to_coords:
                return {
                    'success': False,
                    'error': '유효한 이동을 찾을 수 없습니다.'
                }
            
            # SAN 변환
            result = self._convert_to_san(from_coords, to_coords, promotion)
            
            if result['success']:
                # 추가 분석 정보
                result['analysis'] = {
                    'from_coords': from_coords,
                    'to_coords': to_coords,
                    'moved_piece': moved_piece,
                    'piece_color': 'white' if moved_piece.color else 'black',
                    'piece_type': moved_piece.symbol().lower(),
                    'move_number': len(self.board.move_stack) + 1,
                    'current_turn': 'white' if self.board.turn else 'black',
                    'detection_method': 'auto_detected'
                }
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': f'분석 오류: {str(e)}'
            }
    
    def _determine_move_direction(self, coord1: str, coord2: str, piece1: chess.Piece, piece2: chess.Piece) -> Tuple[Optional[str], Optional[str], Optional[chess.Piece]]:
        """
        두 좌표를 분석해서 이동 방향을 판단
        
        Returns:
            Tuple[from_coords, to_coords, moved_piece]
        """
        square1 = chess.parse_square(coord1)
        square2 = chess.parse_square(coord2)
        
        # 현재 차례 확인
        current_turn = self.board.turn
        
        # 가능한 이동 시나리오들
        scenarios = []
        
        # 시나리오 1: coord1에서 coord2로 이동
        if piece1 and piece1.color == current_turn:
            # coord1에 현재 차례의 기물이 있는 경우
            scenarios.append((coord1, coord2, piece1, 'from_coord1'))
        
        # 시나리오 2: coord2에서 coord1로 이동
        if piece2 and piece2.color == current_turn:
            # coord2에 현재 차례의 기물이 있는 경우
            scenarios.append((coord2, coord1, piece2, 'from_coord2'))
        
        # 시나리오 3: 빈 칸에서 기물이 생긴 경우 (폰 승급 등)
        if not piece1 and piece2 and piece2.color == current_turn:
            # coord1이 빈 칸이고 coord2에 현재 차례의 기물이 있는 경우
            # 이는 폰이 승급한 경우일 수 있음
            scenarios.append((coord1, coord2, piece2, 'promotion'))
        
        # 시나리오 4: 기물이 사라진 경우 (기물 잡기)
        if piece1 and piece1.color == current_turn and not piece2:
            # coord1에 현재 차례의 기물이 있고 coord2가 빈 칸인 경우
            scenarios.append((coord1, coord2, piece1, 'capture'))
        
        # 가장 가능성이 높은 시나리오 선택
        if not scenarios:
            return None, None, None
        
        # 우선순위: 1. 일반 이동, 2. 기물 잡기, 3. 승급
        priority_order = ['from_coord1', 'from_coord2', 'capture', 'promotion']
        
        for priority in priority_order:
            for scenario in scenarios:
                if scenario[3] == priority:
                    from_coords, to_coords, piece, _ = scenario
                    
                    # 이 이동이 합법적인지 확인
                    if self._is_legal_move(from_coords, to_coords, piece):
                        return from_coords, to_coords, piece
        
        # 합법적인 이동이 없으면 첫 번째 시나리오 반환
        return scenarios[0][0], scenarios[0][1], scenarios[0][2]
    
    def _is_legal_move(self, from_coords: str, to_coords: str, piece: chess.Piece) -> bool:
        """이동이 합법적인지 확인"""
        try:
            uci_move = f"{from_coords}{to_coords}"
            move = chess.Move.from_uci(uci_move)
            return move in self.board.legal_moves
        except:
            return False
    
    def _convert_to_san(self, from_coords: str, to_coords: str, promotion: Optional[str] = None) -> Dict:
        """
        좌표를 SAN 표기법으로 변환
        
        Args:
            from_coords (str): 시작 위치
            to_coords (str): 도착 위치
            promotion (str, optional): 승급 기물
        
        Returns:
            dict: 변환 결과
        """
        try:
            # 좌표를 UCI 형식으로 변환
            uci_move = f"{from_coords}{to_coords}"
            if promotion:
                uci_move += promotion
            
            # UCI를 Move 객체로 변환
            move = chess.Move.from_uci(uci_move)
            
            # 이동이 합법적인지 확인
            if move not in self.board.legal_moves:
                return {
                    'success': False,
                    'error': f'잘못된 이동: {from_coords}-{to_coords}'
                }
            
            # 이동 전 보드 상태 저장
            board_before = self.board.copy()
            
            # 기물 이동
            self.board.push(move)
            
            # SAN 표기법 생성
            san_move = board_before.san(move)
            
            # 이동한 기물 정보
            piece = board_before.piece_at(move.from_square)
            piece_symbol = piece.symbol() if piece else '?'
            
            # 기물 잡기 여부 확인
            is_capture = self.board.is_capture(move)
            
            # 체크/체크메이트 확인
            is_check = self.board.is_check()
            is_checkmate = self.board.is_checkmate()
            
            # 보드 상태 복원
            self.board = board_before
            
            return {
                'success': True,
                'san': san_move,
                'uci': uci_move,
                'piece': piece_symbol,
                'is_capture': is_capture,
                'is_check': is_check,
                'is_checkmate': is_checkmate,
                'from_coords': from_coords,
                'to_coords': to_coords
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'변환 오류: {str(e)}'
            }
    
    def _is_valid_coordinate(self, coord: str) -> bool:
        """좌표가 유효한지 확인"""
        if len(coord) != 2:
            return False
        
        file = coord[0].lower()
        rank = coord[1]
        
        return file in 'abcdefgh' and rank in '12345678'
    
    def update_board(self, new_board: chess.Board):
        """보드 상태 업데이트"""
        self.previous_board = self.board.copy()
        self.board = new_board
    
    def get_board_differences(self) -> List[Dict]:
        """
        이전 보드와 현재 보드의 차이점을 분석
        
        Returns:
            List[Dict]: 차이점 목록
        """
        if not self.previous_board:
            return []
        
        differences = []
        
        # 모든 칸을 검사
        for square in chess.SQUARES:
            prev_piece = self.previous_board.piece_at(square)
            curr_piece = self.board.piece_at(square)
            
            if prev_piece != curr_piece:
                coord = chess.square_name(square)
                differences.append({
                    'square': coord,
                    'previous': str(prev_piece) if prev_piece else 'empty',
                    'current': str(curr_piece) if curr_piece else 'empty',
                    'change_type': self._get_change_type(prev_piece, curr_piece)
                })
        
        return differences
    
    def _get_change_type(self, prev_piece: Optional[chess.Piece], curr_piece: Optional[chess.Piece]) -> str:
        """변화 유형 판단"""
        if not prev_piece and curr_piece:
            return 'piece_appeared'
        elif prev_piece and not curr_piece:
            return 'piece_disappeared'
        elif prev_piece and curr_piece and prev_piece != curr_piece:
            return 'piece_changed'
        else:
            return 'no_change'


# 사용 예시 함수
def analyze_chess_move(board: chess.Board, coord1: str, coord2: str, promotion: Optional[str] = None) -> Dict:
    """
    체스 이동을 분석하는 편의 함수
    
    Args:
        board: python-chess 보드 객체
        coord1: 첫 번째 좌표
        coord2: 두 번째 좌표
        promotion: 승급 기물
    
    Returns:
        dict: 분석 결과
    """
    analyzer = ChessAnalyzer(board)
    return analyzer.analyze_position_change(coord1, coord2, promotion)


if __name__ == "__main__":
    # 테스트 코드
    board = chess.Board()
    analyzer = ChessAnalyzer(board)
    
    # 초기 상태에서 e2-e4 이동 분석
    result = analyzer.analyze_position_change('e2', 'e4')
    print("e2-e4 분석 결과:")
    print(result)
    
    # 폰을 실제로 이동
    board.push_san('e4')
    analyzer.update_board(board)
    
    # e7-e5 이동 분석
    result = analyzer.analyze_position_change('e7', 'e5')
    print("\ne7-e5 분석 결과:")
    print(result) 