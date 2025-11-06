# piece_recognition.py — stable_v2 기반 이동 감지
import cv2
import numpy as np
import os

from warp_cam_picam2_stable_v2 import (
    find_chessboard_by_first_last_squares as find_corners,
    warp_chessboard,
    is_valid_quad,
    CornerStabilizer,
    MIN_QUAD_AREA, AR_MIN, AR_MAX
)

# ==== Corner 안정화 ====
_corner_stabilizer = CornerStabilizer(hist_len=7, ema_alpha=0.35, max_jump=60.0, need_good=3)
_last_good_corners = None
_hold_counter = 0
_HOLD_LAST_N_FRAMES = 20

def _safe_find_corners(frame):
    global _last_good_corners, _hold_counter
    raw = find_corners(frame, white_threshold=170)
    if raw is not None:
        ok, _ = is_valid_quad(raw, MIN_QUAD_AREA, AR_MIN, AR_MAX)
        if not ok:
            raw = None
    stable = _corner_stabilizer.update(raw)
    use = None
    if stable is not None:
        use = stable
        _last_good_corners = use
        _hold_counter = 0
    elif _last_good_corners is not None and _hold_counter < _HOLD_LAST_N_FRAMES:
        use = _last_good_corners
        _hold_counter += 1
    return use

# ==== 이동 감지 도우미 ====
def _compute_lab_means(warp, grid=8):
    h, w = warp.shape[:2]
    cell_h, cell_w = h // grid, w // grid
    lab = cv2.cvtColor(warp, cv2.COLOR_BGR2LAB)
    out = np.zeros((grid, grid, 3), np.float32)
    for i in range(grid):
        for j in range(grid):
            y1,y2 = i*cell_h,(i+1)*cell_h
            x1,x2 = j*cell_w,(j+1)*cell_w
            out[i,j] = lab[y1:y2,x1:x2].reshape(-1,3).mean(axis=0)
    return out

def _detrend_deltas(deltas):
    mean_shift = deltas.reshape(-1, 3).mean(axis=0, dtype=np.float32)
    return deltas - mean_shift

def _pair_moves(deltas_flat, norms_flat, threshold=9.0):
    order = np.argsort(-norms_flat)
    candidates = [idx for idx in order if norms_flat[idx] > threshold]
    if len(candidates) < 2:
        return []
    return [(candidates[0], candidates[1])]

# ==== 스트리머 ====
def gen_edges_frames(cap, base_board_path, threshold=9.0, top_k=2):
    prev_warp = None
    last_corners = None

    def _avg_corner_distance(a, b):
        if a is None or b is None:
            return 1e9
        a = np.asarray(a, dtype=np.float32).reshape(4, 2)
        b = np.asarray(b, dtype=np.float32).reshape(4, 2)
        return float(np.linalg.norm(a - b, axis=1).mean())
    if not os.path.exists(base_board_path):
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            _, jpeg = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        return

    base_bgr = np.load(base_board_path)
    base_lab = cv2.cvtColor(base_bgr.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)

    ema_means = None

    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        corners_candidate = _safe_find_corners(frame)

        # 새 코너는 유효 사각형 + 이전 코너와의 이동량 제한(침입 물체로 인한 급변 방지)
        chosen_corners = last_corners
        if corners_candidate is not None:
            ok, _ = is_valid_quad(corners_candidate, MIN_QUAD_AREA, AR_MIN, AR_MAX)
            if ok:
                # 40px 평균 이동 이하만 허용 (너무 크게 튀면 무시)
                if last_corners is None or _avg_corner_distance(last_corners, corners_candidate) <= 40.0:
                    chosen_corners = corners_candidate
        # 코너가 없다면 이전 코너 유지

        if chosen_corners is not None:
            warp = warp_chessboard(frame, chosen_corners, size=400)
            prev_warp = warp
            last_corners = chosen_corners
        else:
            warp = prev_warp if prev_warp is not None else cv2.resize(frame, (400, 400))

        means = _compute_lab_means(warp, grid=8)
        if ema_means is None:
            ema_means = means.copy()
        else:
            ema_means = 0.6*means + 0.4*ema_means

        deltas = _detrend_deltas(ema_means - base_lab)
        norms = np.linalg.norm(deltas, axis=2).astype(np.float32)

        vis = warp.copy()
        H,W = vis.shape[:2]; cs_h, cs_w = H//8, W//8
        pairs = _pair_moves(deltas.reshape(-1,3), norms.reshape(-1), threshold=threshold)
        for a,b in pairs[:top_k]:
            for idx in (a,b):
                i,j = idx//8, idx%8
                x1,y1 = j*cs_w, i*cs_h
                x2,y2 = (j+1)*cs_w,(i+1)*cs_h
                cv2.rectangle(vis, (x1,y1),(x2,y2), (0,0,255), 2)

        _, jpeg = cv2.imencode('.jpg', vis)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
