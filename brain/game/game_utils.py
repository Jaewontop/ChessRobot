from __future__ import annotations

import chess


def describe_game_end(board: chess.Board) -> str:
    """게임 종료 사유를 사람이 읽기 쉬운 문자열로 반환."""
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

