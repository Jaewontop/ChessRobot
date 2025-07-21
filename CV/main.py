from flask import Flask, Response, render_template_string
import cv2
import threading
import numpy as np
import os
import time
from video_streams import gen_warped_frames, gen_original_frames, gen_edges_frames
import pickle
from piece_auto_update import update_chess_pieces

cap = cv2.VideoCapture(0)
latest_frame = None
init_board_values = None
reload_base_board = False
turn_color = 'white'
prev_turn_color = 'white'

# 체스 기물 배열 (행: 0~7, 열: 0~7)
# 0: 검정 진영, 7: 흰색 진영
chess_pieces = [
    ['WR', 'WN', 'WB', 'WQ', 'WK', 'WB', 'WN', 'WR'],
    ['WP', 'WP', 'WP', 'WP', 'WP', 'WP', 'WP', 'WP'],
    ['', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''],
    ['BP', 'BP', 'BP', 'BP', 'BP', 'BP', 'BP', 'BP'],
    ['BR', 'BN', 'BB', 'BQ', 'BK', 'BB', 'BN', 'BR'],
]
prev_board_values = None
prev_warp = None

# 완전 초기상태 저장용
init_board_values = None

# 프레임 읽기 스레드
def frame_reader():
    global latest_frame
    while True:
        ret, frame = cap.read()
        if ret:
            latest_frame = frame
        time.sleep(0.01)

# 서버 시작 전에 스레드 실행
threading.Thread(target=frame_reader, daemon=True).start()

app = Flask(__name__)

hsv_values_global = []

def gen_original_frames_with_hsv():
    global hsv_values_global
    for frame_bytes, hsv_values in gen_original_frames(cap):
        hsv_values_global = hsv_values
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/warp')
def warp_feed():
    return Response(gen_warped_frames(cap), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/original')
def original_feed():
    return Response(gen_original_frames_with_hsv(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/edges')
def edges_feed():
    return Response(gen_edges_frames(cap), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/reset_board', methods=['POST'])
def reset_board():
    global init_board_values, latest_frame, reload_base_board, turn_color, prev_turn_color, prev_board_values, prev_warp
    import os
    file_path = 'init_board_values.npy'
    abs_path = os.path.abspath(file_path)
    # 턴 토글
    prev_turn_color = turn_color
    turn_color = 'black' if turn_color == 'white' else 'white'
    print(f"이전 턴: {prev_turn_color}, 현재 턴: {turn_color}")
    if latest_frame is not None:
        # 이전 기준값/warp 저장
        if os.path.exists(file_path):
            prev_board_values = np.load(file_path)
        else:
            prev_board_values = None
        frame = latest_frame.copy()
        from warping_utils import find_green_corners, warp_chessboard
        corners = find_green_corners(frame)
        if corners is not None:
            warp = warp_chessboard(frame, corners, size=400)
        else:
            warp = frame.copy()
        prev_warp = warp.copy()
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"삭제 시도: {abs_path}")
                if not os.path.exists(file_path):
                    print("삭제 성공")
                else:
                    print("삭제 실패: 파일이 여전히 존재함")
            except Exception as e:
                print(f"삭제 중 예외 발생: {e}")
        else:
            print(f"삭제할 파일이 없음: {abs_path}")
        h, w = warp.shape[:2]
        cell_size_h = h // 8
        cell_size_w = w // 8
        board_vals = np.zeros((8,8,3), dtype=np.float32)
        for i in range(8):
            for j in range(8):
                y1, y2 = i*cell_size_h, (i+1)*cell_size_h
                x1, x2 = j*cell_size_w, (j+1)*cell_size_w
                cell = warp[y1:y2, x1:x2]
                mean_bgr = np.mean(cell.reshape(-1, 3), axis=0)
                board_vals[i, j] = mean_bgr
        np.save(file_path, board_vals)
        # 저장 후 즉시 불러와서 최신값 반영
        init_board_values = np.load(file_path)
        print(f"새 기준값 저장: {abs_path}")
        reload_base_board = True
        return '초기화 완료', 200
    return '프레임 없음', 400

@app.route('/turn_status')
def turn_status():
    global turn_color, prev_turn_color
    return {'current': turn_color, 'previous': prev_turn_color}

@app.route('/piece')
def piece_feed():
    from piece_recognition import gen_edges_frames
    return Response(gen_edges_frames(cap, base_board_path='init_board_values.npy', threshold=40), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/base_board_img')
def base_board_img():
    import cv2
    global latest_frame, init_board_values, chess_pieces
    h, w = 400, 400
    cell_size_h = h // 8
    cell_size_w = w // 8
    # chess_pieces를 전역 배열에서 직접 사용
    if not (isinstance(chess_pieces, list) and len(chess_pieces) == 8 and all(isinstance(row, list) and len(row) == 8 for row in chess_pieces)):
        print('chess_pieces가 8x8 배열이 아님! 기본값으로 대체')
        chess_pieces = [['']*8 for _ in range(8)]
    base_img = np.ones((h, w, 3), dtype=np.uint8) * 220  # 밝은 바탕
    # 체스 기물 배열 배경 (0행이 아래, 7행이 위, 색상도 반전)
    for i in range(8):
        for j in range(8):
            chess_i = 7 - i
            y1, y2 = i*cell_size_h, (i+1)*cell_size_h
            x1, x2 = j*cell_size_w, (j+1)*cell_size_w
            if (i+j)%2 == 0:
                cv2.rectangle(base_img, (x1, y1), (x2, y2), (180,180,180), -1)  # 검정
            else:
                cv2.rectangle(base_img, (x1, y1), (x2, y2), (240,240,240), -1)  # 흰색
            piece = chess_pieces[chess_i][j]
            if piece:
                if piece[0] == 'W':
                    font_color = (255,255,255)  # 흰색
                elif piece[0] == 'B':
                    font_color = (0,0,0)  # 검정
                else:
                    font_color = (0,0,255)  # 기타(빨강)
                cv2.putText(base_img, piece, (x1+8, y1+cell_size_h//2+10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, font_color, 2, cv2.LINE_AA)
    # 현재 프레임 diff 표시
    if latest_frame is not None and init_board_values is not None:
        from warping_utils import find_green_corners, warp_chessboard
        frame = latest_frame.copy()
        corners = find_green_corners(frame)
        if corners is not None and len(corners) == 4:
            warp = warp_chessboard(frame, corners, size=400)
        else:
            warp = frame.copy()
        diff_vals = np.zeros((8,8), dtype=np.float32)
        diff_list = []
        for i in range(8):
            for j in range(8):
                y1, y2 = i*cell_size_h, (i+1)*cell_size_h
                x1, x2 = j*cell_size_w, (j+1)*cell_size_w
                cell = warp[y1:y2, x1:x2]
                mean_bgr = np.mean(cell.reshape(-1, 3), axis=0)
                diff = np.linalg.norm(mean_bgr - init_board_values[i, j])
                diff_vals[i, j] = diff
                diff_list.append((diff, i, j))
        # 텍스트 표시
        for i in range(8):
            for j in range(8):
                y1, y2 = i*cell_size_h, (i+1)*cell_size_h
                x1, x2 = j*cell_size_w, (j+1)*cell_size_w
                text = f"{int(diff_vals[i, j])}"
                text_x = x1 + 2
                text_y = y1 + cell_size_h//2
                cv2.putText(base_img, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1, cv2.LINE_AA)
        # diff가 가장 큰 두 칸에 무조건 빨간 박스
        if len(diff_list) >= 2:
            diff_list.sort(reverse=True)
            seen = set()
            shown = 0
            for diff, i, j in diff_list:
                if (i, j) not in seen:
                    y1, y2 = i*cell_size_h, (i+1)*cell_size_h
                    x1, x2 = j*cell_size_w, (j+1)*cell_size_w
                    cv2.rectangle(base_img, (x1, y1), (x2, y2), (0,0,255), 2)
                    seen.add((i, j))
                    shown += 1
                    if shown == 2:
                        break
    _, buffer = cv2.imencode('.jpg', base_img)
    frame_bytes = buffer.tobytes()
    return Response(frame_bytes, mimetype='image/jpeg')

# 완전 초기상태 저장용
init_board_values = None

@app.route('/set_init_board', methods=['POST'])
def set_init_board():
    global init_board_values, latest_frame, init_board_values
    import os
    file_path = 'init_board_values.npy'
    if latest_frame is not None:
        frame = latest_frame.copy()
        from warping_utils import find_green_corners, warp_chessboard
        corners = find_green_corners(frame)
        if corners is not None:
            warp = warp_chessboard(frame, corners, size=400)
        else:
            warp = frame.copy()
        h, w = warp.shape[:2]
        cell_size_h = h // 8
        cell_size_w = w // 8
        board_vals = np.zeros((8,8,3), dtype=np.float32)
        for i in range(8):
            for j in range(8):
                y1, y2 = i*cell_size_h, (i+1)*cell_size_h
                x1, x2 = j*cell_size_w, (j+1)*cell_size_w
                cell = warp[y1:y2, x1:x2]
                mean_bgr = np.mean(cell.reshape(-1, 3), axis=0)
                board_vals[i, j] = mean_bgr
        np.save(file_path, board_vals)
        init_board_values = board_vals
        # 기준값도 동기화
        np.save('init_board_values.npy', board_vals)
        init_board_values = board_vals
        print(f"완전 초기상태 저장: {file_path} 및 init_board_values.npy")
        return '초기상태 저장 완료', 200
    return '프레임 없음', 400

def coord_to_chess_notation(i, j):
    # 0,0이 a1(아래), 7,7이 h8(위)
    file = chr(ord('a') + j)
    rank = str(i + 1)
    return file + rank

def piece_to_fen(piece):
    if not piece or len(piece) < 2:
        return ''
    color, kind = piece[0], piece[1]
    # FEN: KQBNRP (백 대문자), kqbnrp (흑 소문자)
    kind_map = {'K':'K', 'Q':'Q', 'R':'R', 'B':'B', 'N':'N', 'P':'P'}
    fen = kind_map.get(kind.upper(), '?')
    if color == 'W':
        return fen.upper()
    elif color == 'B':
        return fen.lower()
    else:
        return '?'

move_history = []

@app.route('/next_turn', methods=['POST'])
def next_turn():
    global init_board_values, latest_frame, reload_base_board, turn_color, prev_turn_color, prev_board_values, prev_warp, chess_pieces, move_history
    import os
    import pickle
    file_path = 'init_board_values.npy'
    abs_path = os.path.abspath(file_path)
    # 턴 토글
    prev_turn_color = turn_color
    turn_color = 'black' if turn_color == 'white' else 'white'
    print(f"이전 턴: {prev_turn_color}, 현재 턴: {turn_color}")
    # chess_pieces를 파일로 저장
    with open('chess_pieces.pkl', 'wb') as f:
        pickle.dump(chess_pieces, f)
    if latest_frame is not None:
        # 이전 기준값/warp 저장
        if os.path.exists(file_path):
            prev_board_values = np.load(file_path)
        else:
            prev_board_values = None
        frame = latest_frame.copy()
        from warping_utils import find_green_corners, warp_chessboard
        corners = find_green_corners(frame)
        if corners is not None:
            warp = warp_chessboard(frame, corners, size=400)
        else:
            warp = frame.copy()
        prev_warp = warp.copy()
        # diff 가장 큰 두개 좌표 계산
        h, w = warp.shape[:2]
        cell_size_h = h // 8
        cell_size_w = w // 8
        board_vals = np.zeros((8,8,3), dtype=np.float32)
        diff_list = []
        for i in range(8):
            for j in range(8):
                y1, y2 = i*cell_size_h, (i+1)*cell_size_h
                x1, x2 = j*cell_size_w, (j+1)*cell_size_w
                cell = warp[y1:y2, x1:x2]
                mean_bgr = np.mean(cell.reshape(-1, 3), axis=0)
                board_vals[i, j] = mean_bgr
                if prev_board_values is not None:
                    diff = np.linalg.norm(mean_bgr - prev_board_values[i, j])
                    diff_list.append((diff, i, j))
        diff_list.sort(reverse=True)
        if len(diff_list) >= 2:
            (diff1, i1, j1), (diff2, i2, j2) = diff_list[0], diff_list[1]
            print(f"[DEBUG] diff 가장 큰 두개: ({i1},{j1})={diff1:.1f}, ({i2},{j2})={diff2:.1f}")
            # chess_pieces 불러오기
            try:
                with open('chess_pieces.pkl', 'rb') as f:
                    chess_pieces = pickle.load(f)
            except Exception as e:
                print(f'chess_pieces 불러오기 실패: {e}')
                chess_pieces = [['']*8 for _ in range(8)]
            # 이동 반영
            before = [row[:] for row in chess_pieces]
            chess_pieces = update_chess_pieces(chess_pieces, (i1, j1), (i2, j2))
            # FEN 표기법에 맞는 이동 내역 기록
            piece1 = before[i1][j1]
            piece2 = before[i2][j2]
            move_str = None
            if piece1 and not piece2:
                move_str = f"{piece_to_fen(piece1)} {coord_to_chess_notation(i1, j1)}-{coord_to_chess_notation(i2, j2)}"
            elif piece2 and not piece1:
                move_str = f"{piece_to_fen(piece2)} {coord_to_chess_notation(i2, j2)}-{coord_to_chess_notation(i1, j1)}"
            else:
                move_str = f"? {coord_to_chess_notation(i1, j1)}<->{coord_to_chess_notation(i2, j2)}"  # 불확실
            print(f"[DEBUG] move: {move_str}")
            move_history.append(move_str)
            # 저장
            with open('chess_pieces.pkl', 'wb') as f:
                pickle.dump(chess_pieces, f)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"삭제 시도: {abs_path}")
                if not os.path.exists(file_path):
                    print("삭제 성공")
                else:
                    print("삭제 실패: 파일이 여전히 존재함")
            except Exception as e:
                print(f"삭제 중 예외 발생: {e}")
        else:
            print(f"삭제할 파일이 없음: {abs_path}")
        np.save(file_path, board_vals)
        # 저장 후 즉시 불러와서 최신값 반영
        init_board_values = np.load(file_path)
        print(f"새 기준값 저장: {abs_path}")
        reload_base_board = True
        return '턴 기록 및 전환 완료', 200
    return '프레임 없음', 400

# index()에 두 버튼 추가
@app.route('/')
def index():
    global turn_color, prev_turn_color, move_history
    move_str = ' -> '.join(move_history)
    return render_template_string('''
    <h1>체스판 실시간 분석</h1>
    <div style="margin-bottom:10px; font-size:18px;">
      <b>현재 턴:</b> {{turn_color}}<br>
      <b>이전 턴:</b> {{prev_turn_color if prev_turn_color else '없음'}}
    </div>
    <button onclick="setInitialBoard()">완전 초기상태 저장</button>
    <button onclick="nextTurn()">턴 기록 및 전환</button>
    <script>
    function setInitialBoard() {
      fetch('/set_init_board', {method: 'POST'})
        .then(r => r.text())
        .then(msg => {
          alert(msg);
          // diff 스트림 완전 새로고침
          const pieceDiv = document.getElementById('piece-div');
          if (pieceDiv) {
            pieceDiv.innerHTML = '<img src="/piece?ts=' + Date.now() + '" width="320" height="320" style="border:1px solid #aaa;">';
          }
          // 기준값 이미지 새로고침
          const baseDiv = document.getElementById('base-div');
          if (baseDiv) {
            baseDiv.innerHTML = '<img src="/base_board_img?ts=' + Date.now() + '" width="320" height="320" style="border:1px solid #aaa;">';
          }
          // 턴 정보 새로고침
          fetch('/turn_status').then(r=>r.json()).then(data => {
            document.getElementById('turn-info').innerHTML = '<b>현재 턴:</b> ' + data.current + '<br><b>이전 턴:</b> ' + (data.previous ? data.previous : '없음');
          });
        });
    }
    function nextTurn() {
      fetch('/next_turn', {method: 'POST'})
        .then(r => r.text())
        .then(msg => {
          alert(msg);
          // diff 스트림 완전 새로고침
          const pieceDiv = document.getElementById('piece-div');
          if (pieceDiv) {
            pieceDiv.innerHTML = '<img src="/piece?ts=' + Date.now() + '" width="320" height="320" style="border:1px solid #aaa;">';
          }
          // 기준값 이미지 새로고침
          const baseDiv = document.getElementById('base-div');
          if (baseDiv) {
            baseDiv.innerHTML = '<img src="/base_board_img?ts=' + Date.now() + '" width="320" height="320" style="border:1px solid #aaa;">';
          }
          // 턴 정보 새로고침
          fetch('/turn_status').then(r=>r.json()).then(data => {
            document.getElementById('turn-info').innerHTML = '<b>현재 턴:</b> ' + data.current + '<br><b>이전 턴:</b> ' + (data.previous ? data.previous : '없음');
          });
          // 이동 내역 새로고침
          location.reload();
        });
    }
    </script>
    <div id="turn-info" style="margin-bottom:10px; font-size:18px;">
      <b>현재 턴:</b> {{turn_color}}<br>
      <b>이전 턴:</b> {{prev_turn_color if prev_turn_color else '없음'}}
    </div>
    <div style="display: flex; gap: 20px;">
      <div>
        <h3 style="margin:0; font-size:16px;">웹캠 원본</h3>
        <img src="/original" width="320" height="320" style="border:1px solid #aaa;">
      </div>
      <div>
        <h3 style="margin:0; font-size:16px;">와핑 결과</h3>
        <img src="/warp" width="320" height="320" style="border:1px solid #aaa;">
      </div>
      <div id="piece-div">
        <h3 style="margin:0; font-size:16px;">차이 시각화</h3>
        <img src="/piece" width="320" height="320" style="border:1px solid #aaa;">
      </div>
      <div id="base-div">
        <h3 style="margin:0; font-size:16px;">기물 배열/상태</h3>
        <img src="/base_board_img" width="320" height="320" style="border:1px solid #aaa;">
      </div>
    </div>
    <div style="margin-top:20px; font-size:16px; color:#222;">
      <b>기물 이동 내역:</b><br>
      {{ move_str }}
    </div>
    ''', turn_color=turn_color, prev_turn_color=prev_turn_color, move_str=move_str)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False) 