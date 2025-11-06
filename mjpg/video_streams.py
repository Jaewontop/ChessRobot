# video_streams.py (디버그 강화판, 혼합 모드 사용)

import cv2
import numpy as np
import os, time

# v2 모듈에서 혼합 corner 검출/warp 재사용
from warp_cam_picam2_stable_v2 import (
    find_chessboard_by_first_last_squares as find_corners,
    warp_chessboard,
    Hmin, Hmax, Smin, Smax, Vmin, Vmax,
    is_valid_quad, CornerStabilizer, MIN_QUAD_AREA, AR_MIN, AR_MAX
)

GRID = 8
WARP_SIZE = 400
JPEG_QUALITY = 80

def _jpeg_bytes_from_rgb(img_rgb):
    bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode('.jpg', bgr, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok:
        ok, buf = cv2.imencode('.jpg', bgr)
    return buf.tobytes()

def _draw_grid(vis_rgb):
    h, w = vis_rgb.shape[:2]
    cs_h, cs_w = h // GRID, w // GRID
    for j in range(1, GRID):
        x = j * cs_w
        cv2.line(vis_rgb, (x, 0), (x, h), (100, 100, 100), 1, cv2.LINE_AA)
    for i in range(1, GRID):
        y = i * cs_h
        cv2.line(vis_rgb, (0, y), (w, y), (100, 100, 100), 1, cv2.LINE_AA)

def gen_original_frames(cap):
    """원본 스트림"""
    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            time.sleep(0.01)
            continue
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        yield _jpeg_bytes_from_rgb(frame_rgb), []

def gen_warped_frames(cap):
    """체스판 와핑 스트림"""
    prev_warp = None
    # 안정화된 코너 보정기 (스트림 생명주기 내 유지)
    _corner_stabilizer = CornerStabilizer(hist_len=7, ema_alpha=0.35, max_jump=60.0, need_good=3)
    _last_good_corners = None
    _hold_counter = 0
    _HOLD_LAST_N_FRAMES = 20

    def _safe_find_corners(frame_bgr):
        nonlocal _last_good_corners, _hold_counter
        raw = find_corners(frame_bgr, white_threshold=180)
        if raw is not None:
            ok, _ = is_valid_quad(raw, MIN_QUAD_AREA, AR_MIN, AR_MAX)
            if not ok:
                raw = None
        stable = _corner_stabilizer.update(raw)
        if stable is not None:
            _last_good_corners = stable
            _hold_counter = 0
            return stable
        if _last_good_corners is not None and _hold_counter < _HOLD_LAST_N_FRAMES:
            _hold_counter += 1
            return _last_good_corners
        return None
    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        # --- 코너 검출 (안정화) ---
        corners = _safe_find_corners(frame_bgr)

        # --- 디버그: 원본에 코너 점 찍기 ---
        debug_rgb = frame_rgb.copy()
        if corners is not None:
            for (x, y) in corners.astype(int):
                cv2.circle(debug_rgb, (x, y), 10, (255, 0, 0), -1)

        # --- 와핑 ---
        warped = None
        if corners is not None:
            warped = warp_chessboard(frame_bgr, corners, size=WARP_SIZE)

        if warped is not None:
            vis = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
            status = "Warp OK"
            prev_warp = vis.copy()
        else:
            if prev_warp is not None:
                vis = prev_warp.copy()
                status = "No corners - showing previous warp"
            else:
                vis = debug_rgb.copy()
                status = "No warp - showing original"

        _draw_grid(vis)
        h, w = vis.shape[:2]
        cv2.putText(vis, status, (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2, cv2.LINE_AA)

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + _jpeg_bytes_from_rgb(vis) + b'\r\n')

def gen_edges_frames(cap):
    """디버그 스트림 (piece_recognition에서 가져옴)"""
    from piece_recognition import gen_edges_frames as _gen_edges_frames
    yield from _gen_edges_frames(cap)
