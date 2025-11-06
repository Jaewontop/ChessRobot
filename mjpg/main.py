# main.py
from flask import Flask, Response, render_template_string, request, jsonify
import cv2
import threading
import numpy as np
import os
import time
import pickle
import math
from pathlib import Path

# 내부 모듈
from video_streams import gen_original_frames, gen_edges_frames
from piece_auto_update import update_chess_pieces

# ▶▶ 변경: stable 버전 함수/클래스 사용
#   - 초록마커(find_green_corners) 대신 베이지칸 기반 + 안정화
from warp_cam_picam2_stable_v2 import (
    warp_chessboard,
)

# ▶▶ 추가: 쌍 매칭(pairing)로 이동칸 추정
from piece_recognition import _pair_moves

# ==== 경로(절대) ====
BASE_DIR = Path(__file__).resolve().parent
NPPATH = str(BASE_DIR / "init_board_values.npy")
PKLPATH = str(BASE_DIR / "chess_pieces.pkl")

# =======================
# 전역 상태
# =======================
USE_PICAM2 = True  # CSI 카메라(PiCam2)면 True, USB 웹캠이면 False

if USE_PICAM2:
    # Picamera2를 VideoCapture처럼 쓰기 위한 간단 래퍼
    class PiCam2Capture:
        def __init__(self, size=(1280, 720), fps=30, hflip=False, vflip=False):
            from picamera2 import Picamera2
            self.hflip = hflip
            self.vflip = vflip
            self.picam2 = Picamera2()
            cfg = self.picam2.create_preview_configuration(
                main={"size": size, "format": "RGB888"},
                controls={"FrameRate": fps}
            )
            self.picam2.configure(cfg)
            self.picam2.start()

        def read(self):
            import cv2
            rgb = self.picam2.capture_array()
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            if self.hflip:
                bgr = cv2.flip(bgr, 1)
            if self.vflip:
                bgr = cv2.flip(bgr, 0)
            return True, bgr

        def release(self):
            try:
                self.picam2.stop()
            except Exception:
                pass

    cap = PiCam2Capture()  # <-- CSI 카메라
else:
    import cv2
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)  # <-- USB 웹캠
    # 필요 시 해상도/FPS 세팅
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

latest_frame = None
# 수동 와핑 모드 상태
manual_mode = False
manual_corners = None  # np.float32 (4,2) in TL,TR,BR,BL order

# 자동 코너/안정화는 사용하지 않음 (수동 와핑 전용)

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
    import numpy as np
    pts = np.array(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    ordered = np.array([tl, tr, br, bl], dtype=np.float32)
    return ordered

def _set_manual_corners(points):
    """points: list/ndarray shape (4,2), in any order. We will order TL,TR,BR,BL."""
    global manual_corners, manual_mode
    import numpy as np
    arr = np.array(points, dtype=np.float32).reshape(4, 2)
    ordered = _order_corners_tl_tr_br_bl(arr)
    manual_corners = ordered
    manual_mode = True

def _clear_manual_corners():
    global manual_corners, manual_mode
    manual_corners = None
    manual_mode = False

def _get_corners_for_frame(frame):
    """수동 코너만 사용. 없으면 None."""
    return manual_corners

class WarpedCapture:
    """원본 cap을 감싸 수동 코너가 설정된 경우 항상 와핑된 프레임을 반환하는 래퍼.
    piece_recognition, video_streams 등의 기존 제너레이터에 투명하게 전달 가능.
    """
    def __init__(self, cap, size=400):
        self._cap = cap
        self._size = size

    def read(self):
        ret, frame = self._cap.read()
        if not ret:
            return ret, frame
        corners = _get_corners_for_frame(frame)
        if corners is not None and len(corners) == 4:
            warped = warp_chessboard(frame, corners, size=self._size)
            return True, warped
        # 코너가 없으면 안전하게 리사이즈
        try:
            return True, cv2.resize(frame, (self._size, self._size))
        except Exception:
            return True, frame

    def release(self):
        try:
            self._cap.release()
        except Exception:
            pass

# =======================
# 유틸: 좌표 표기/색 판별
# =======================
def coord_to_chess_notation(i, j):
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

def _is_color_piece(code, color):
    return bool(code) and ((color == 'white' and code[0] == 'W') or (color == 'black' and code[0] == 'B'))

# =======================
# 노이즈 억제 도우미 (LAB + 다중 프레임 평균)
# =======================
def _mean_lab_board_from_warp(warp):
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

# 자동 코너 탐지는 제거됨

def _capture_avg_lab_board(cap, n_frames=8, sleep_sec=0.02):
    acc = np.zeros((8, 8, 3), np.float32)
    cnt = 0
    last_warp = None

    for _ in range(n_frames):
        ret, frame = cap.read()
        if not ret:
            break

        corners = _get_corners_for_frame(frame)
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
# 견고성 향상: 에지/텍스처 맵 (원본 유지 - /base_board_img용)
# =======================
def _edge_density_map(warp_img):
    try:
        gray = cv2.cvtColor(warp_img, cv2.COLOR_BGR2GRAY)
    except Exception:
        gray = warp_img if len(warp_img.shape) == 2 else cv2.cvtColor(warp_img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    v = np.var(eq)
    lower = max(10, min(80, int(0.33 * np.sqrt(max(1.0, v)))))
    upper = int(lower * 2.5)
    edges = cv2.Canny(eq, lower, upper)
    h, w = edges.shape[:2]
    cell_h, cell_w = h // 8, w // 8
    out = np.zeros((8, 8), np.float32)
    for i in range(8):
        for j in range(8):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            cell = edges[y1:y2, x1:x2]
            total = cell.size
            out[i, j] = 0.0 if total == 0 else float(np.count_nonzero(cell)) / float(total)
    return out

def _l_variance_map(warp_img):
    lab = cv2.cvtColor(warp_img, cv2.COLOR_BGR2LAB)
    L = lab[:, :, 0]
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    L_eq = clahe.apply(L)
    h, w = L_eq.shape[:2]
    cell_h, cell_w = h // 8, w // 8
    out = np.zeros((8, 8), np.float32)
    for i in range(8):
        for j in range(8):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            cell = L_eq[y1:y2, x1:x2]
            out[i, j] = float(np.var(cell))
    return out

# =======================
# 부팅 시 보드/기준 로드
# =======================
def _startup_load_state():
    global chess_pieces, init_board_values
    if os.path.exists(NPPATH):
        try:
            init_board_values = np.load(NPPATH)
            print(f'[BOOT] init_board_values.npy 로드 완료: {NPPATH}')
        except Exception as e:
            print(f'[BOOT] init_board_values.npy 로드 실패: {e}')
            init_board_values = None
    else:
        print(f'[BOOT] init_board_values.npy 없음: {NPPATH}')

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
    # 항상 수동 와핑된 프레임을 기준으로 동작
    local_cap = WarpedCapture(cap)
    for frame_bytes, hsv_values in gen_original_frames(local_cap):
        hsv_values_global = hsv_values
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

def _encode_jpeg(img):
    ret, buf = cv2.imencode('.jpg', img)
    return buf.tobytes() if ret else b''

def _draw_corners_on_image(img, corners, color=(0, 255, 255)):
    out = img.copy()
    if corners is not None and len(corners) == 4:
        for (x, y) in corners:
            cv2.circle(out, (int(x), int(y)), 8, color, -1)
        pts = np.array(corners, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(out, [pts], isClosed=True, color=(0, 200, 255), thickness=2)
    return out

def gen_warped_frames_manual(cap, size=400):
    """수동 코너가 설정되었을 때 사용하는 와핑 스트림 제네레이터."""
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue
        corners = _get_corners_for_frame(frame)
        warp = warp_chessboard(frame, corners, size=size) if corners is not None else cv2.resize(frame, (size, size))
        frame_bytes = _encode_jpeg(warp)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# ---------- 스트림 라우트 ----------
@app.route('/warp')
def warp_feed():
    # 항상 수동 코너 기반 와핑 제네레이터 사용
    return Response(gen_warped_frames_manual(cap), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/original')
def original_feed():
    return Response(gen_original_frames_with_hsv(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/edges')
def edges_feed():
    # 항상 WarpedCapture 사용
    local_cap = WarpedCapture(cap)
    return Response(gen_edges_frames(local_cap), mimetype='multipart/x-mixed-replace; boundary=frame')

# 차이 시각화
def _draw_piece_diff(warp_img, top_k=2):
    # warp_img: 400x400 기준 가정
    h, w = warp_img.shape[:2]
    cell_h, cell_w = h // 8, w // 8
    canvas = warp_img.copy()
    if init_board_values is None:
        return canvas
    diffs = []
    for i in range(8):
        for j in range(8):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            cell = warp_img[y1:y2, x1:x2]
            mean_bgr = np.mean(cell.reshape(-1, 3), axis=0)
            diff = float(np.linalg.norm(mean_bgr - init_board_values[i, j]))
            diffs.append((diff, i, j))
    diffs.sort(reverse=True)
    k = max(0, min(top_k, len(diffs)))
    for n in range(k):
        _, i, j = diffs[n]
        y1, y2 = i * cell_h, (i + 1) * cell_h
        x1, x2 = j * cell_w, (j + 1) * cell_w
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 0, 255), 3)
    return canvas

def gen_piece_frames_local(cap, size=400, top_k=2):
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue
        # cap은 WarpedCapture이므로 frame 자체가 이미 와핑된 보드
        warp = frame
        try:
            if warp.shape[0] != size or warp.shape[1] != size:
                warp = cv2.resize(warp, (size, size))
        except Exception:
            pass
        vis = _draw_piece_diff(warp, top_k=top_k)
        frame_bytes = _encode_jpeg(vis)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/piece')
def piece_feed():
    # 로컬 제너레이터로 교체하여 400x400 기준으로만 렌더링 (검정 여백 방지)
    local_cap = WarpedCapture(cap)
    return Response(gen_piece_frames_local(local_cap, size=400, top_k=2),
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
            chess_i = i
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w

            if (i + j) % 2 == 0:
                cv2.rectangle(base_img, (x1, y1), (x2, y2), (180, 180, 180), -1)
            else:
                cv2.rectangle(base_img, (x1, y1), (x2, y2), (240, 240, 240), -1)

            piece = chess_pieces[chess_i][j]
            if piece:
                color = (255, 255, 255) if piece[0] == 'W' else (0, 0, 0) if piece[0] == 'B' else (0, 0, 255)
                cv2.putText(base_img, piece, (x1 + 8, y1 + cell_h // 2 + 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

    if latest_frame is not None and init_board_values is not None:
        frame = latest_frame.copy()
        corners = _get_corners_for_frame(frame)
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

        for i in range(8):
            for j in range(8):
                y1 = i * cell_h
                x1 = j * cell_w
                text = f"{int(diff_vals[i, j])}"
                cv2.putText(base_img, text, (x1 + 4, y1 + cell_h // 2 + 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 200), 2, cv2.LINE_AA)

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

# ---------- 디버그: 코너/와프 확인 ----------
@app.route('/debug_original')
def debug_original():
    global latest_frame
    if latest_frame is None:
        ret, frame = cap.read()
        if not ret:
            return '프레임 없음', 500
        latest_frame = frame
    frame = latest_frame.copy()
    corners = _get_corners_for_frame(frame)
    dbg = _draw_corners_on_image(frame, corners)
    return Response(_encode_jpeg(dbg), mimetype='image/jpeg')

@app.route('/debug_warp')
def debug_warp():
    global latest_frame
    if latest_frame is None:
        ret, frame = cap.read()
        if not ret:
            return '프레임 없음', 500
        latest_frame = frame
    frame = latest_frame.copy()
    corners = _get_corners_for_frame(frame)
    warp = warp_chessboard(frame, corners, size=400) if corners is not None else cv2.resize(frame, (400, 400))
    return Response(_encode_jpeg(warp), mimetype='image/jpeg')

# ---------- 스냅샷(원본) 제공 ----------
@app.route('/snapshot_original')
def snapshot_original():
    global latest_frame
    if latest_frame is None:
        ret, frame = cap.read()
        if not ret:
            return '프레임 없음', 500
        latest_frame = frame
    # 원본 해상도/비율 그대로 반환
    img = latest_frame.copy()
    _, buf = cv2.imencode('.jpg', img)
    return Response(buf.tobytes(), mimetype='image/jpeg')

# ---------- 기준값 저장 ----------
@app.route('/set_init_board', methods=['POST'])
def set_init_board():
    """현재 프레임을 와핑 후 8x8 평균 BGR을 기준으로 저장"""
    global init_board_values, latest_frame

    if latest_frame is None:
        return '프레임 없음', 400

    frame = latest_frame.copy()
    corners = _get_corners_for_frame(frame)
    frame = latest_frame.copy()
    corners = _get_corners_for_frame(frame)
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
    """
    ▶ 패치: LAB 델타 + 디트렌딩 + _pair_moves 로 (출발, 도착) 추정
    + 턴 전환 + 새 기준 저장 (나머지 로직은 기존 유지)
    """
    global init_board_values, latest_frame, reload_base_board, turn_color, prev_turn_color
    global prev_board_values, prev_warp, chess_pieces, move_history

    prev_turn_color = turn_color
    turn_color = 'black' if turn_color == 'white' else 'white'
    print(f"이전 턴: {prev_turn_color}, 현재 턴: {turn_color}")

    try:
        with open(PKLPATH, 'wb') as f:
            pickle.dump(chess_pieces, f)
    except Exception as e:
        print(f'[WARN] chess_pieces.pkl 저장 실패(사전): {e}')

    if latest_frame is None:
        return '프레임 없음', 400

    prev_board_values = np.load(NPPATH) if os.path.exists(NPPATH) else None

    # --- 현재 보드 LAB 평균 (다중 프레임 평균) ---
    curr_lab, warp = _capture_avg_lab_board(cap, n_frames=8, sleep_sec=0.02)
    if curr_lab is None:
        return '현재 보드 캡처 실패', 500
    prev_warp = warp.copy()

    # --- 이전 기준 BGR -> LAB ---
    if prev_board_values is not None:
        prev_lab = np.zeros((8, 8, 3), np.float32)
        for i in range(8):
            for j in range(8):
                bgr = np.array(prev_board_values[i, j], dtype=np.uint8)[None, None, :]
                lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
                prev_lab[i, j] = lab[0, 0]
    else:
        prev_lab = curr_lab.copy()

    # --- 델타 + 디트렌딩 ---
    deltas = curr_lab - prev_lab
    mean_shift = deltas.reshape(-1, 3).mean(axis=0, dtype=np.float32)
    deltas = deltas - mean_shift
    norms = np.linalg.norm(deltas, axis=2).astype(np.float32)

    # --- 쌍 매칭으로 src/dst 추정 ---
    pairs = _pair_moves(deltas.reshape(-1, 3), norms.reshape(-1), threshold=9.0)
    if pairs:
        a, b = pairs[0]
        src = (a // 8, a % 8)
        dst = (b // 8, b % 8)
        print(f"[DEBUG] pair pick src={src}, dst={dst}")
    else:
        # 폴백: 상위 두 칸
        flat = norms.flatten()
        order = np.argsort(-flat)
        src = (order[0] // 8, order[0] % 8)
        dst = (order[1] // 8, order[1] % 8)
        print(f"[WARN] pair 없음 → fallback src/dst={src}->{dst}")

    # --- 다음 턴 기준 저장용 BGR 평균 ---
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

# ---------- 수동 코너 설정 API ----------
@app.route('/set_corners', methods=['POST'])
def set_corners_api():
    """JSON: {"points": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]} 순서는 무관.
    수동 모드를 활성화하고 /warp 스트림이 수동 와핑을 사용하도록 전환한다.
    """
    try:
        data = request.get_json(force=True)
        pts = data.get('points')
        if not pts or len(pts) != 4:
            return jsonify({'ok': False, 'error': 'points must be length 4'}), 400
        # 좌표는 원본 해상도 기준으로 전달된다고 가정하고 그대로 사용
        _set_manual_corners(pts)
        return jsonify({'ok': True, 'manual_mode': True}), 200
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/clear_corners', methods=['POST'])
def clear_corners_api():
    _clear_manual_corners()
    return jsonify({'ok': True, 'manual_mode': False}), 200

@app.route('/get_corners', methods=['GET'])
def get_corners_api():
    if manual_corners is None:
        return jsonify({'manual_mode': manual_mode, 'points': None})
    pts = manual_corners.astype(float).tolist()
    return jsonify({'manual_mode': manual_mode, 'points': pts})

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
    <div style="margin:10px 0;">
      <a href="/manual" target="_blank">[수동 4점 설정 페이지 열기]</a>
      &nbsp;|&nbsp;
      <a href="/debug_original" target="_blank">[코너 디버그]</a>
      &nbsp;|&nbsp;
      <a href="/debug_warp" target="_blank">[와프 디버그]</a>
    </div>
    <div style="display: flex, gap: 20px;">
      <div>
        <h3 style="margin:0; font-size:16px;">웹캠 원본</h3>
        <img src="/original" style="border:1px solid #aaa; max-width: 48vw; height: auto;">
      </div>
      <div>
        <h3 style="margin:0; font-size:16px;">와핑 결과</h3>
        <img src="/warp" style="border:1px solid #aaa; max-width: 48vw; height: auto;">
      </div>
      <div id="piece-div">
        <h3 style="margin:0; font-size:16px;">차이 시각화</h3>
        <img src="/piece" style="border:1px solid #aaa; max-width: 48vw; height: auto;">
      </div>
      <div id="base-div">
        <h3 style="margin:0; font-size:16px;">기물 배열/상태</h3>
        <img src="/base_board_img" style="border:1px solid #aaa; max-width: 48vw; height: auto;">
      </div>
    </div>
    <div style="margin-top:20px; font-size:16px; color:#222;">
      <b>기물 이동 내역:</b><br>
      {{ move_str }}
    </div>
    ''', turn_color=turn_color, prev_turn_color=prev_turn_color, move_str=move_str)

# ---------- 수동 4점 설정 UI ----------
@app.route('/manual')
def manual_page():
    return render_template_string('''
    <html>
    <head>
      <meta charset="utf-8" />
      <title>수동 코너 설정</title>
      <style>
        body { font-family: sans-serif; }
        #wrap { display: flex; gap: 20px; }
        #left { flex: 0 0 auto; }
        #right { flex: 1 1 auto; }
        canvas { border: 1px solid #aaa; cursor: crosshair; }
        .btn { padding: 6px 10px; margin-right: 6px; }
        .pt { width: 70px; display: inline-block; }
      </style>
    </head>
    <body>
      <h2>수동 4점 설정 (원본 스냅샷에 클릭하여 TL,TR,BR,BL 순서로 선택 권장)</h2>
      <div id="wrap">
        <div id="left">
          <div style="margin-bottom:8px;">
            <button class="btn" onclick="loadSnapshot()">스냅샷 새로고침</button>
            <button class="btn" onclick="clearPoints()">포인트 초기화</button>
            <button class="btn" onclick="sendPoints()">저장(/set_corners)</button>
            <button class="btn" onclick="clearServer()">서버 해제(/clear_corners)</button>
          </div>
          <div>
            <img id="img" src="/snapshot_original?ts=" style="display:none;" onload="drawImage()" />
            <canvas id="canvas" width="400" height="400"></canvas>
          </div>
        </div>
        <div id="right">
          <div><b>선택된 포인트</b> (이미지 좌표):</div>
          <div id="pts"></div>
          <div id="status" style="margin-top:10px;color:#006400;"></div>
        </div>
      </div>

      <script>
      const img = document.getElementById('img');
      const canvas = document.getElementById('canvas');
      const ctx = canvas.getContext('2d');
      let points = [];

      function loadSnapshot() {
        document.getElementById('img').src = '/snapshot_original?ts=' + Date.now();
      }

      function drawImage() {
        // 원본 해상도에 맞춰 캔버스 크기를 설정
        const w = img.naturalWidth || img.width;
        const h = img.naturalHeight || img.height;
        canvas.width = w; canvas.height = h;
        ctx.clearRect(0,0,w,h);
        ctx.drawImage(img, 0, 0, w, h);
        drawOverlay();
      }

      function drawOverlay() {
        // 점과 선 그리기
        ctx.fillStyle = 'rgba(0,0,0,0.25)';
        for (let i=0;i<points.length;i++){
          const p = points[i];
          ctx.beginPath();
          ctx.arc(p.x, p.y, 6, 0, Math.PI*2);
          ctx.fillStyle = '#00ff00';
          ctx.fill();
          ctx.strokeStyle = '#003300';
          ctx.stroke();
          ctx.fillStyle = '#ffffff';
          ctx.font = '14px sans-serif';
          ctx.fillText((i+1).toString(), p.x+8, p.y-8);
        }
        if (points.length === 4) {
          ctx.beginPath();
          ctx.moveTo(points[0].x, points[0].y);
          ctx.lineTo(points[1].x, points[1].y);
          ctx.lineTo(points[2].x, points[2].y);
          ctx.lineTo(points[3].x, points[3].y);
          ctx.closePath();
          ctx.strokeStyle = '#ffff00';
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        updatePtsPanel();
      }

      function canvasPos(evt){
        const rect = canvas.getBoundingClientRect();
        const x = evt.clientX - rect.left;
        const y = evt.clientY - rect.top;
        return {x,y};
      }

      canvas.addEventListener('click', (evt) => {
        if (points.length >= 4) return;
        const p = canvasPos(evt);
        points.push(p);
        drawOverlay();
      });

      function clearPoints(){
        points = [];
        drawImage();
        setStatus('포인트 초기화 완료');
      }

      function updatePtsPanel(){
        const div = document.getElementById('pts');
        let html = '';
        for (let i=0;i<points.length;i++){
          const p = points[i];
          html += `<div>#${i+1} <span class="pt">x:${Math.round(p.x)}</span> <span class="pt">y:${Math.round(p.y)}</span></div>`;
        }
        div.innerHTML = html;
      }

      function setStatus(msg, ok=true){
        const s = document.getElementById('status');
        s.style.color = ok ? '#006400' : '#8B0000';
        s.textContent = msg;
      }

      async function sendPoints(){
        if (points.length !== 4){ setStatus('포인트 4개를 선택하세요', false); return; }
        // 원본 좌표계를 그대로 서버에 전달
        const pts = points.map(p => [Math.round(p.x), Math.round(p.y)]);
        try{
          const res = await fetch('/set_corners', {
            method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({points: pts})
          });
          const j = await res.json();
          if (j.ok){ setStatus('저장 성공. /warp에서 수동 와핑 사용 중'); }
          else { setStatus('저장 실패: '+(j.error||res.status), false); }
        }catch(e){ setStatus('요청 실패: '+e, false); }
      }

      async function clearServer(){
        try{
          const res = await fetch('/clear_corners', {method:'POST'});
          const j = await res.json();
          if (j.ok){ setStatus('서버 수동 모드 해제'); }
          else { setStatus('해제 실패', false); }
        }catch(e){ setStatus('요청 실패: '+e, false); }
      }

      // 초기 스냅샷 로드
      loadSnapshot();
      </script>
    </body>
    </html>
    ''')

# =======================
# 엔트리 포인트
# =======================
if __name__ == '__main__':
    _startup_load_state()
    threading.Thread(target=frame_reader, daemon=True).start()
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
