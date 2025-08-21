import pickle

def update_chess_pieces(chess_pieces, pos1, pos2):
    """
    chess_pieces: 8x8 배열 (문자열)
    pos1, pos2: (i, j) 튜플 (diff가 큰 두 칸)
    한 쪽에만 기물이 있으면 그 기물이 다른 쪽으로 이동
    """
    piece1 = chess_pieces[pos1[0]][pos1[1]]
    piece2 = chess_pieces[pos2[0]][pos2[1]]
    if piece1 and not piece2:
        # pos1 → pos2 이동
        chess_pieces[pos2[0]][pos2[1]] = piece1
        chess_pieces[pos1[0]][pos1[1]] = ''
        print(f"[DEBUG] {piece1}가 {pos1} → {pos2} 이동")
    elif piece2 and not piece1:
        # pos2 → pos1 이동
        chess_pieces[pos1[0]][pos1[1]] = piece2
        chess_pieces[pos2[0]][pos2[1]] = ''
        print(f"[DEBUG] {piece2}가 {pos2} → {pos1} 이동")
    else:
        print(f"[DEBUG] 이동 불확실: {pos1}({piece1}), {pos2}({piece2})")
    return chess_pieces

# 예시 사용법
if __name__ == "__main__":
    # chess_pieces 불러오기
    with open('chess_pieces.pkl', 'rb') as f:
        chess_pieces = pickle.load(f)
    # 예시: diff가 큰 두 박스 좌표
    pos1 = (6, 4)  # 예: e2 (WP)
    pos2 = (4, 4)  # 예: e4
    chess_pieces = update_chess_pieces(chess_pieces, pos1, pos2)
    # 저장
    with open('chess_pieces.pkl', 'wb') as f:
        pickle.dump(chess_pieces, f)
    print('기물 이동 반영 완료') 
