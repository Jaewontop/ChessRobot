# video_streams.py
import cv2
import numpy as np
import os, time

# v2 모듈에서 코너/와핑 및 HSV 임계값 재사용
from warp_cam_picam2_v2 import (
    find_green_corners, warp_chessboard,
    Hmin, Hmax, Smin, Smax, Vmin, Vmax
)

# ==== 설정값 ====
GRID = 8
WARP_SIZE = 400
JPEG_QUALITY = 80

THRESHOLD = 12.0     # diff 문턱
TOP_K = 2            # 이동 후보 칸 수 (보통 2칸: 출발/도착)
DIFF_EMA = 0.5       # diff 부드럽게(지터 완화)
# ===============

def _jpeg_bytes(img):
    ok, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok: ok, buf = cv2.imencode('.jpg', img)
    return buf.tobytes()

def _draw_grid(vis):
    h, w = vis.shape[:2]
    cs_h, cs_w = h // GRID, w // GRID

    # 세로선
    for j in range(1, GRID):
        x = j * cs_w
        cv2.line(vis, (x, 0), (x, h), (100, 100, 100), 1, cv2.LINE_AA)
    # 가로선
    for i in range(1, GRID):
        y = i * cs_h
        cv2.line(vis, (0, y), (w, y), (100, 100, 100), 1, cv2.LINE_AA)

    # 좌표 라벨
    for j in range(GRID):
        cv2.putText(vis, chr(ord('a') + j), (j * cs_w + 4, 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120,120,120), 1, cv2.LINE_AA)
    for i in range(GRID):
        cv2.putText(vis, str(GRID - i), (4, i * cs_h + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120,120,120), 1, cv2.LINE_AA)

def _cell_mean_bgr(img, i, j, cs_h, cs_w):
    y1, y2 = i * cs_h, (i + 1) * cs_h
    x1, x2 = j * cs_w, (j + 1) * cs_w
    cell = img[y1:y2, x1:x2]
    return cell.reshape(-1, 3).mean(axis=0)

def _cell_center(i, j, cs_h, cs_w):
    y1, y2 = i * cs_h, (i + 1) * cs_h
    x1, x2 = j * cs_w, (j + 1) * cs_w
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return (cx, cy)

def gen_original_frames(cap):
    """
    (frame_bytes, hsv_values) 튜플을 반환하여 main.py와 호환.
    ⚠️ 디버그 점/선/도형 표시 없음 (완전 원본 표시)
    """
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01); continue
        yield _jpeg_bytes(frame), []

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
        upper = np.array([Hmax, Hmax, Vmax], dtype=np.uint8)
        upper[0] = Hmax  # 안전
        mask = cv2.inRange(hsv, lower, upper)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))

        # 디버그 도형/점 전부 제거: disp는 원본 그대로
        disp = frame.copy()

        # hsv_values만 유지(필요하면 UI에서 참고)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hsv_values = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 50: continue
            M = cv2.moments(cnt)
            if M['m00'] == 0: continue
            cx = int(M['m10']/M['m00']); cy = int(M['m01']/M['m00'])
            hsv_values.append([int(x) for x in hsv[cy, cx]])

        yield _jpeg_bytes(disp), hsv_values

def gen_warped_frames(cap, base_board_path='init_board_values.npy'):
    """
    /warp 스트림:
    - 코너 검출 → 와핑
    - 64칸 분할 평균 BGR vs 기준(init_board_values.npy) diff 숫자 오버레이
    - 상위 2칸(출발/도착 추정) 박스 표시
    - ⚠️ 화살표/번호 라벨(#1,#2) 제거
    - 코너 실패 시 이전 warp 폴백(없으면 원본)
    """
    lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
    upper = np.array([Hmax, Hmax, Vmax], dtype=np.uint8)
    upper[0] = Hmax

    prev_warp = None
    prev_diffs = None

    base_vals = None
    last_mtime = None

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01); continue

        # 기준값 자동 리로드(파일 변경 감지)
        if os.path.exists(base_board_path):
            mtime = os.path.getmtime(base_board_path)
            if last_mtime is None or mtime != last_mtime or base_vals is None:
                try:
                    base_vals = np.load(base_board_path)
                    last_mtime = mtime
                except Exception as e:
                    print(f"[video_streams] 기준값 로드 실패: {e}")
                    base_vals = None
        else:
            base_vals = None
            last_mtime = None

        # 코너 → 와핑 (시그니처 차이 안전)
        try:
            corners = find_green_corners(frame.copy(), lower, upper, min_area=60)
        except TypeError:
            corners = find_green_corners(frame.copy())

        if corners is not None and len(corners) == 4:
            warp = warp_chessboard(frame, corners, size=WARP_SIZE)
            prev_warp = warp.copy()
            status = "Warp OK"
        else:
            if prev_warp is not None:
                warp = prev_warp.copy()
                status = "No corners - showing previous warp"
            else:
                warp = frame.copy()
                status = "No corners - showing original"

        vis = warp.copy()
        _draw_grid(vis)

        h, w = vis.shape[:2]
        cs_h, cs_w = h // GRID, w // GRID

        # diff 계산 & 오버레이
        if base_vals is not None and base_vals.shape == (GRID, GRID, 3):
            diffs = np.zeros((GRID, GRID), np.float32)
            for i in range(GRID):
                for j in range(GRID):
                    mean_bgr = _cell_mean_bgr(warp, i, j, cs_h, cs_w).astype(np.float32)
                    diffs[i, j] = float(np.linalg.norm(mean_bgr - base_vals[i, j]))

            # 부드럽게
            if prev_diffs is None:
                smooth = diffs
            else:
                smooth = DIFF_EMA * diffs + (1.0 - DIFF_EMA) * prev_diffs
            prev_diffs = smooth

            # 숫자 쓰기
            for i in range(GRID):
                for j in range(GRID):
                    y1 = i * cs_h; x1 = j * cs_w
                    cv2.putText(vis, str(int(round(smooth[i, j]))), (x1 + 2, y1 + cs_h // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1, cv2.LINE_AA)

            # 상위 K칸 하이라이트 (사각형만, 화살표/라벨 없음)
            flat = smooth.flatten()
            order = np.argsort(-flat)  # 내림차순
            picks = []
            for idx in order:
                if len(picks) >= TOP_K: break
                if flat[idx] < THRESHOLD: break
                picks.append(idx)

            for k, idx in enumerate(picks):
                i = idx // GRID; j = idx % GRID
                x1, y1 = j * cs_w, i * cs_h
                x2, y2 = (j + 1) * cs_w, (i + 1) * cs_h
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0,0,255), 2)

        else:
            cv2.putText(vis, "NO BASE: click 'Set Initial Board' in web UI",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2, cv2.LINE_AA)

        # 상태 텍스트
        cv2.putText(vis, status, (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2, cv2.LINE_AA)

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + _jpeg_bytes(vis) + b'\r\n')

def gen_edges_frames(cap):
    """
    디버그 스트림: piece_recognition.py의 제너레이터를 그대로 연결.
    """
    from piece_recognition import gen_edges_frames as _gen_edges_frames
    yield from _gen_edges_frames(cap)
