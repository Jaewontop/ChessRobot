# main.py
from flask import Flask, Response, render_template_string
import cv2
import threading
import numpy as np
import os
import time
import pickle
import math
from pathlib import Path

# 내부 모듈
from video_streams import gen_warped_frames, gen_original_frames, gen_edges_frames
from piece_auto_update import update_chess_pieces
# find_green_corners 시그니처가 버전에 따라 다를 수 있으므로 HSV 범위도 함께 import
from warp_cam_picam2_v2 import find_green_corners, warp_chessboard, Hmin, Hmax, Smin, Smax, Vmin, Vmax

# ==== 경로(절대) ====
BASE_DIR = Path(__file__).resolve().parent
NPPATH = str(BASE_DIR / "init_board_values.npy")
PKLPATH = str(BASE_DIR / "chess_pieces.pkl")

# =======================
# 전역 상태
# =======================
USE_PICAM2 = True  # CSI 카메라인 경우 True

if USE_PICAM2:
    from piece_recognition import PiCam2Capture
    cap = PiCam2Capture()
else:
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

latest_frame = None

# 기준/턴/보드 상태
init_board_values = None
reload_base_board = False
turn_color = 'white'
prev_turn_color = 'white'
player_color = None   # 'white' or 'black' (카메라 아랫변 쪽 플레이어)

# 체스 기물 배열 (행: 0~7, 열: 0~7)
chess_pieces = [
    ['BR', 'BN', 'BB', 'BQ', 'BK', 'BB', 'BN', 'BR'],
    ['BP', 'BP', 'BP', 'BP', 'BP', 'BP', 'BP', 'BP'],
    ['', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''],
    ['WP', 'WP', 'WP', 'WP', 'WP', 'WP', 'WP', 'WP'],
    ['WR', 'WN', 'WB', 'WQ', 'WK', 'WB', 'WN', 'WR'],
]

prev_board_values = None
prev_warp = None
move_history = []

def _order_corners_tl_tr_br_bl(pts):
    """
    4점(pts)을 (Top-Left, Top-Right, Bottom-Right, Bottom-Left) 순서로 정렬해서 반환.
    pts: iterable of 4 points [[x,y], ...] or np.array shape (4,2)
    """
    import numpy as np
    pts = np.array(pts, dtype=np.float32).reshape(4, 2)

    # 합/차를 이용한 고전적 정렬 방식
    s = pts.sum(axis=1)          # x + y
    d = np.diff(pts, axis=1)     # y - x (주의: np.diff along axis=1 returns shape (4,1))

    tl = pts[np.argmin(s)]       # 합이 가장 작음
    br = pts[np.argmax(s)]       # 합이 가장 큼
    tr = pts[np.argmin(d)]       # (y-x)가 가장 작음 -> x가 크고 y가 작을 가능성 → 우상단
    bl = pts[np.argmax(d)]       # (y-x)가 가장 큼  -> x가 작고 y가 클 가능성 → 좌하단

    ordered = np.array([tl, tr, br, bl], dtype=np.float32)
    return ordered

# =======================
# 유틸: 좌표 표기/색 판별
# =======================
def coord_to_chess_notation(i, j):
    """(0,0)=a8, (7,7)=h1 체스 표기"""
    file = chr(ord('a') + j)
    rank = str(8 - i)
    return file + rank

def piece_to_fen(piece):
    if not piece or len(piece) < 2:
        return ''
    color, kind = piece[0], piece[1]
    kind_map = {'K': 'K', 'Q': 'Q', 'R': 'R', 'B': 'B', 'N': 'N', 'P': 'P'}
    fen = kind_map.get(kind.upper(), '?')
    return fen.upper() if color == 'W' else fen.lower() if color == 'B' else '?'

def _is_color_piece(code, color):  # code: 'WP','BP',..., color: 'white'/'black'
    return bool(code) and ((color == 'white' and code[0] == 'W') or (color == 'black' and code[0] == 'B'))

# =======================
# 노이즈 억제 도우미 (LAB + 다중 프레임 평균)
# =======================
def _mean_lab_board_from_warp(warp):
    """와핑된 400x400 보드에서 8x8 칸 평균을 LAB 공간(mean)으로 반환 (float32, shape=(8,8,3))"""
    h, w = warp.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    lab = cv2.cvtColor(warp, cv2.COLOR_BGR2LAB)
    out = np.zeros((8, 8, 3), np.float32)
    for i in range(8):
        for j in range(8):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            cell = lab[y1:y2, x1:x2]
            out[i, j] = cell.reshape(-1, 3).mean(axis=0)
    return out

def _safe_find_corners(frame):
    """
    find_green_corners 시그니처 차이를 흡수하고,
    반환된 4점을 TL, TR, BR, BL 순서로 강제 정렬해서 돌려준다.
    """
    import numpy as np

    corners = None
    try:
        lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
        upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)
        # 일부 버전은 (frame, lower, upper, min_area=...) 시그니처
        corners = find_green_corners(frame, lower, upper, min_area=60)
    except TypeError:
        # 다른 버전은 (frame)만 받는 시그니처
        corners = find_green_corners(frame)

    if corners is not None and len(corners) == 4:
        try:
            corners = _order_corners_tl_tr_br_bl(corners)
        except Exception:
            # 혹시라도 형상 문제 등으로 정렬 실패 시 원본 유지
            pass

    return corners

def _capture_avg_lab_board(cap, n_frames=8, sleep_sec=0.02):
    """짧은 시간 n_frames 프레임을 평균해서 LAB 보드값을 안정적으로 산출"""
    acc = np.zeros((8, 8, 3), np.float32)
    cnt = 0
    last_warp = None

    for _ in range(n_frames):
        ret, frame = cap.read()
        if not ret:
            break

        corners = _safe_find_corners(frame)

        if corners is not None and len(corners) == 4:
            warp = warp_chessboard(frame, corners, size=400)
        else:
            warp = cv2.resize(frame, (400, 400))

        last_warp = warp
        acc += _mean_lab_board_from_warp(warp)
        cnt += 1
        time.sleep(sleep_sec)

    if cnt == 0:
        return None, None
    return acc / cnt, last_warp

# =======================
# 부팅 시 보드/기준 로드
# =======================
def _startup_load_state():
    global chess_pieces, init_board_values
    # init_board_values
    if os.path.exists(NPPATH):
        try:
            init_board_values = np.load(NPPATH)
            print(f'[BOOT] init_board_values.npy 로드 완료: {NPPATH}')
        except Exception as e:
            print(f'[BOOT] init_board_values.npy 로드 실패: {e}')
            init_board_values = None
    else:
        print(f'[BOOT] init_board_values.npy 없음: {NPPATH}')

    # chess_pieces.pkl
    if os.path.exists(PKLPATH):
        try:
            with open(PKLPATH, 'rb') as f:
                cp = pickle.load(f)
            if isinstance(cp, list) and len(cp) == 8 and all(isinstance(r, list) and len(r) == 8 for r in cp):
                chess_pieces = cp
                print(f'[BOOT] chess_pieces.pkl 로드 완료: {PKLPATH}')
            else:
                print('[BOOT] chess_pieces.pkl 형식 이상 -> 기본값 사용')
        except Exception as e:
            print(f'[BOOT] chess_pieces.pkl 로드 실패: {e}')
    else:
        try:
            with open(PKLPATH, 'wb') as f:
                pickle.dump(chess_pieces, f)
            print(f'[BOOT] chess_pieces.pkl 생성(초기 배열): {PKLPATH}')
        except Exception as e:
            print(f'[BOOT] chess_pieces.pkl 생성 실패: {e}')

# =======================
# 프레임 읽기 스레드
# =======================
def frame_reader():
    global latest_frame
    while True:
        ret, frame = cap.read()
        if ret:
            latest_frame = frame
        time.sleep(0.01)

# =======================
# Flask 앱
# =======================
app = Flask(__name__)
hsv_values_global = []

def gen_original_frames_with_hsv():
    global hsv_values_global
    for frame_bytes, hsv_values in gen_original_frames(cap):
        hsv_values_global = hsv_values
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# ---------- 스트림 라우트 ----------
@app.route('/warp')
def warp_feed():
    return Response(gen_warped_frames(cap), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/original')
def original_feed():
    return Response(gen_original_frames_with_hsv(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/edges')
def edges_feed():
    return Response(gen_edges_frames(cap), mimetype='multipart/x-mixed-replace; boundary=frame')

# 차이 시각화: threshold 완화(40 → 15) + 절대경로 사용
@app.route('/piece')
def piece_feed():
    from piece_recognition import gen_edges_frames as gen_diff_frames
    return Response(gen_diff_frames(cap, base_board_path=NPPATH, threshold=15,top_k=2),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# ---------- 상태 라우트 ----------
@app.route('/turn_status')
def turn_status():
    return {'current': turn_color, 'previous': prev_turn_color}

# ---------- 보드/기준 시각화 ----------
@app.route('/base_board_img')
def base_board_img():
    global latest_frame, init_board_values, chess_pieces
    h, w = 400, 400
    cell_h = h // 8
    cell_w = w // 8

    if not (isinstance(chess_pieces, list) and len(chess_pieces) == 8 and all(isinstance(row, list) and len(row) == 8 for row in chess_pieces)):
        print('chess_pieces가 8x8 배열이 아님! 기본값으로 대체')
        chess_pieces = [[''] * 8 for _ in range(8)]

    base_img = np.ones((h, w, 3), dtype=np.uint8) * 220
    for i in range(8):
        for j in range(8):
            chess_i = i  # 시각화 좌표계를 와핑/업데이트와 동일하게 유지
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w

            # 보드 칠하기
            if (i + j) % 2 == 0:
                cv2.rectangle(base_img, (x1, y1), (x2, y2), (180, 180, 180), -1)
            else:
                cv2.rectangle(base_img, (x1, y1), (x2, y2), (240, 240, 240), -1)

            # 기물 텍스트
            piece = chess_pieces[chess_i][j]
            if piece:
                color = (255, 255, 255) if piece[0] == 'W' else (0, 0, 0) if piece[0] == 'B' else (0, 0, 255)
                cv2.putText(base_img, piece, (x1 + 8, y1 + cell_h // 2 + 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

    # diff 수치/상위 박스
    if latest_frame is not None and init_board_values is not None:
        frame = latest_frame.copy()
        corners = _safe_find_corners(frame)

        if corners is not None and len(corners) == 4:
            warp = warp_chessboard(frame, corners, size=400)
        else:
            warp = cv2.resize(frame, (400, 400))

        diff_vals = np.zeros((8, 8), dtype=np.float32)
        diff_list = []
        for i in range(8):
            for j in range(8):
                y1, y2 = i * cell_h, (i + 1) * cell_h
                x1, x2 = j * cell_w, (j + 1) * cell_w
                cell = warp[y1:y2, x1:x2]
                mean_bgr = np.mean(cell.reshape(-1, 3), axis=0)
                diff = np.linalg.norm(mean_bgr - init_board_values[i, j])
                diff_vals[i, j] = diff
                diff_list.append((diff, i, j))

        # 숫자(굵게)
        for i in range(8):
            for j in range(8):
                y1 = i * cell_h
                x1 = j * cell_w
                text = f"{int(diff_vals[i, j])}"
                cv2.putText(base_img, text, (x1 + 4, y1 + cell_h // 2 + 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 200), 2, cv2.LINE_AA)

        # 상위 2칸 박스(두께 3)
        diff_list.sort(reverse=True)
        shown = 0
        used = set()
        for diff, i, j in diff_list:
            if (i, j) in used:
                continue
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            cv2.rectangle(base_img, (x1, y1), (x2, y2), (0, 0, 255), 3)
            used.add((i, j))
            shown += 1
            if shown == 2:
                break

    _, buffer = cv2.imencode('.jpg', base_img)
    return Response(buffer.tobytes(), mimetype='image/jpeg')

# ---------- 기준값 저장 ----------
@app.route('/set_init_board', methods=['POST'])
def set_init_board():
    """현재 프레임을 와핑 후 8x8 평균 BGR을 기준으로 저장"""
    global init_board_values, latest_frame

    if latest_frame is None:
        return '프레임 없음', 400

    frame = latest_frame.copy()
    corners = _safe_find_corners(frame)

    warp = warp_chessboard(frame, corners, size=400) if corners is not None else cv2.resize(frame, (400, 400))

    h, w = warp.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    board_vals = np.zeros((8, 8, 3), dtype=np.float32)
    for i in range(8):
        for j in range(8):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            cell = warp[y1:y2, x1:x2]
            board_vals[i, j] = np.mean(cell.reshape(-1, 3), axis=0)

    np.save(NPPATH, board_vals)
    init_board_values = board_vals
    print(f"완전 초기상태 저장: {NPPATH}")
    return '초기상태 저장 완료', 200

# ---------- 턴 전환(이동 추정 + 새 기준 저장) ----------
@app.route('/next_turn', methods=['POST'])
def next_turn():
    """이동 추정(노이즈 억제 + LAB 비교 + 적응 임계 + 방향 보정) + 턴 전환 + 새 기준 저장"""
    global init_board_values, latest_frame, reload_base_board, turn_color, prev_turn_color
    global prev_board_values, prev_warp, chess_pieces, move_history

    # 턴 토글
    prev_turn_color = turn_color
    turn_color = 'black' if turn_color == 'white' else 'white'
    print(f"이전 턴: {prev_turn_color}, 현재 턴: {turn_color}")

    # 현재 보드 상태 저장(스냅샷)
    try:
        with open(PKLPATH, 'wb') as f:
            pickle.dump(chess_pieces, f)
    except Exception as e:
        print(f'[WARN] chess_pieces.pkl 저장 실패(사전): {e}')

    if latest_frame is None:
        return '프레임 없음', 400

    # 이전 기준(BGR 평균)
    prev_board_values = np.load(NPPATH) if os.path.exists(NPPATH) else None

    # ---------- 여러 프레임 평균 + LAB 공간으로 현재 보드 추정 ----------
    curr_lab, warp = _capture_avg_lab_board(cap, n_frames=8, sleep_sec=0.02)
    if curr_lab is None:
        return '현재 보드 캡처 실패', 500
    prev_warp = warp.copy()

    # prev_board_values(BGR평균) -> LAB로 변환
    prev_lab = np.zeros((8, 8, 3), np.float32)
    if prev_board_values is not None:
        for i in range(8):
            for j in range(8):
                bgr = np.array(prev_board_values[i, j], dtype=np.uint8)[None, None, :]
                lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
                prev_lab[i, j] = lab[0, 0]
    else:
        prev_lab = curr_lab.copy()

    # 밝기 L 영향 줄이기: a,b만 비교
    diff_mat = np.linalg.norm(curr_lab[:, :, 1:3] - prev_lab[:, :, 1:3], axis=2)

    # 적응 임계값: 평균 + 0.75*표준편차, 최소 3.0
    mu = float(diff_mat.mean())
    sigma = float(diff_mat.std())
    adaptive_thr = max(3.0, mu + 0.75 * sigma)

    # 내림차순 정렬
    flat = diff_mat.flatten()
    order = np.argsort(-flat)

    # 상위 후보 넉넉히 뽑기
    K = 6
    candidates = [ (idx // 8, idx % 8, float(flat[idx])) for idx in order[:K] ]

    # 이전 보드의 말 상태
    try:
        with open(PKLPATH, 'rb') as f:
            before_board = pickle.load(f)
    except Exception:
        before_board = [row[:] for row in chess_pieces]

    mover_color = prev_turn_color  # 이번에 실제로 움직인 편
    best = None  # (score, (src_i,src_j), (dst_i,dst_j))

    def is_valid(i, j): return 0 <= i < 8 and 0 <= j < 8

    def pair_score(src_i, src_j, dst_i, dst_j, ds, dd):
        psrc = before_board[src_i][src_j] if is_valid(src_i, src_j) else ''
        pdst = before_board[dst_i][dst_j] if is_valid(dst_i, dst_j) else ''
        score = 0.0
        score += 1.0 * ds + 0.8 * dd                # 변화량 가중
        if _is_color_piece(psrc, mover_color): score += 2.0
        if (not pdst) or (psrc and pdst and psrc[0] != pdst[0]): score += 1.0  # 빈칸 or 상대말
        if src_i == dst_i and src_j == dst_j: score -= 100.0                    # 같은 칸 방지
        return score

    # 후보쌍 평가
    for a in range(len(candidates)):
        i1, j1, d1 = candidates[a]
        for b in range(a + 1, len(candidates)):
            i2, j2, d2 = candidates[b]

            # 둘 다 임계 미만이면 스킵 (너무 미세한 변화)
            if d1 < adaptive_thr and d2 < adaptive_thr:
                continue

            s1 = pair_score(i1, j1, i2, j2, d1, d2)
            s2 = pair_score(i2, j2, i1, j1, d2, d1)
            if best is None or s1 > best[0]:
                best = (s1, (i1, j1), (i2, j2))
            if s2 > best[0]:
                best = (s2, (i2, j2), (i1, j1))

    # 최종 선택 (폴백 포함)
    if best is None:
        (i1, j1) = (order[0] // 8, order[0] % 8)
        (i2, j2) = (order[1] // 8, order[1] % 8)
        src, dst = (i1, j1), (i2, j2)
        print(f"[WARN] adaptive pick 실패 -> fallback src/dst={src}->{dst} (thr={adaptive_thr:.2f})")
    else:
        _, src, dst = best
        print(f"[DEBUG] adaptive pick src={src} dst={dst} thr={adaptive_thr:.2f}")

    # --- board_vals(BGR) 생성: 다음 턴 기준 저장용 ---
    h, w = warp.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    board_vals = np.zeros((8, 8, 3), np.float32)
    for i in range(8):
        for j in range(8):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            cell = warp[y1:y2, x1:x2]
            board_vals[i, j] = cell.reshape(-1, 3).mean(axis=0)

    # ---- 이동 반영 ----
    try:
        with open(PKLPATH, 'rb') as f:
            chess_pieces = pickle.load(f)
    except Exception:
        pass

    before = [row[:] for row in chess_pieces]
    chess_pieces = update_chess_pieces(chess_pieces, src, dst)

    # 기보 기록
    piece_src = before[src[0]][src[1]]
    piece_dst = before[dst[0]][dst[1]]
    if piece_src and not piece_dst:
        move_str = f"{piece_to_fen(piece_src)} {coord_to_chess_notation(src[0], src[1])}-{coord_to_chess_notation(dst[0], dst[1])}"
    elif piece_dst and not piece_src:
        move_str = f"{piece_to_fen(piece_dst)} {coord_to_chess_notation(dst[0], dst[1])}-{coord_to_chess_notation(src[0], src[1])}"
    else:
        move_str = f"? {coord_to_chess_notation(src[0], src[1])}<->{coord_to_chess_notation(dst[0], dst[1])}"
    print(f"[DEBUG] move: {move_str}")
    move_history.append(move_str)

    # 저장
    try:
        with open(PKLPATH, 'wb') as f:
            pickle.dump(chess_pieces, f)
    except Exception as e:
        print(f'[WARN] chess_pieces.pkl 저장 실패(사후): {e}')

    # 기존 기준 삭제 후 새 기준 저장
    if os.path.exists(NPPATH):
        try:
            os.remove(NPPATH)
            print(f"삭제 성공: {NPPATH}")
        except Exception as e:
            print(f"삭제 중 예외 발생: {e}")
    else:
        print(f"삭제할 파일이 없음: {NPPATH}")

    np.save(NPPATH, board_vals)
    try:
        init_board_values = np.load(NPPATH)
    except Exception as e:
        init_board_values = board_vals
        print(f'[WARN] 새 기준 재로드 실패: {e}')
    print(f"새 기준값 저장: {NPPATH}")
    reload_base_board = True

    return '턴 기록 및 전환 완료', 200

# ---------- 메인 UI ----------
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
          const pieceDiv = document.getElementById('piece-div');
          if (pieceDiv) {
            pieceDiv.innerHTML = '<img src="/piece?ts=' + Date.now() + '" width="320" height="320" style="border:1px solid #aaa;">';
          }
          const baseDiv = document.getElementById('base-div');
          if (baseDiv) {
            baseDiv.innerHTML = '<img src="/base_board_img?ts=' + Date.now() + '" width="320" height="320" style="border:1px solid #aaa;">';
          }
          fetch('/turn_status').then(r=>r.json()).then(data => {
            document.getElementById('turn-info').innerHTML =
              '<b>현재 턴:</b> ' + data.current + '<br><b>이전 턴:</b> ' + (data.previous ? data.previous : '없음');
          });
        });
    }
    function nextTurn() {
      fetch('/next_turn', {method: 'POST'})
        .then(r => r.text())
        .then(msg => {
          alert(msg);
          const pieceDiv = document.getElementById('piece-div');
          if (pieceDiv) {
            pieceDiv.innerHTML = '<img src="/piece?ts=' + Date.now() + '" width="320" height="320" style="border:1px solid #aaa;">';
          }
          const baseDiv = document.getElementById('base-div');
          if (baseDiv) {
            baseDiv.innerHTML = '<img src="/base_board_img?ts=' + Date.now() + '" width="320" height="320" style="border:1px solid #aaa;">';
          }
          fetch('/turn_status').then(r=>r.json()).then(data => {
            document.getElementById('turn-info').innerHTML =
              '<b>현재 턴:</b> ' + data.current + '<br><b>이전 턴:</b> ' + (data.previous ? data.previous : '없음');
          });
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

# =======================
# 엔트리 포인트
# =======================
if __name__ == '__main__':
    _startup_load_state()
    threading.Thread(target=frame_reader, daemon=True).start()
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
