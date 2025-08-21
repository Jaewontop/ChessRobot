# piece_recognition.py
# - 통합 버전: (1) 단독 실행 run()  (2) Flask용 스트리밍 gen_edges_frames()
# - 단독 실행: 실행 중 'b'로 현재 warp를 기준값(메모리) 설정, 'c'로 초기화, 'q'/ESC 종료.
# - Flask 연동: gen_edges_frames(cap, base_board_path, threshold) 사용.
#   ※ base_board_path('init_board_values.npy')는 main.py가 저장한 BGR 평균값(8x8x3, float32)과 비교.

import cv2
import numpy as np
import os

from warp_cam_picam2_v2 import (
    find_green_corners,
    warp_chessboard,
    FRAME_SIZE, FPS, HFLIP, VFLIP,
    USE_AUTO_EXPOSURE, EXPOSURE_TIME, ANALOG_GAIN,
    Hmin, Hmax, Smin, Smax, Vmin, Vmax
)

# ===================== CONFIG =====================
GRID = 8
WARP_SIZE = 400
CELL_MARGIN_RATIO = 0.08

# 단독 실행용 파라미터 (LAB 기반 EMA 스무딩)
THRESHOLD = 12.0      # 차이값 문턱
EMA_ALPHA = 0.6       # 셀 평균 EMA
DIFF_ALPHA = 0.5      # diff EMA
TOP_K = 4             # 박스 최대 개수

SHOW_WINDOW_NAME = "PieceRecognition (Warp+Diff)"
# ==================================================


# -------------------- 공통 유틸 --------------------
def _split_sizes(h: int, w: int, grid: int):
    """셀 크기, 마진 계산"""
    cs_h, cs_w = h // grid, w // grid
    my = int(cs_h * CELL_MARGIN_RATIO)
    mx = int(cs_w * CELL_MARGIN_RATIO)
    return cs_h, cs_w, my, mx


def _cell_region(i, j, cs_h, cs_w, my, mx, H, W):
    """셀 내부 마진까지 고려한 안전한 ROI"""
    y1 = i * cs_h + my
    y2 = (i + 1) * cs_h - my
    x1 = j * cs_w + mx
    x2 = (j + 1) * cs_w - mx
    # 경계 보정
    y1 = max(0, min(y1, H - 1)); y2 = max(y1 + 1, min(y2, H))
    x1 = max(0, min(x1, W - 1)); x2 = max(x1 + 1, min(x2, W))
    return y1, y2, x1, x2


def compute_board_means_LAB(image_bgr, grid=GRID, margin_ratio=CELL_MARGIN_RATIO):
    """단독 실행(run)에서 메모리 기준값을 만들 때 사용 (LAB 평균)"""
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    H, W = lab.shape[:2]
    cs_h, cs_w, my, mx = _split_sizes(H, W, grid)
    means = np.zeros((grid, grid, 3), np.float32)
    for i in range(grid):
        for j in range(grid):
            y1, y2, x1, x2 = _cell_region(i, j, cs_h, cs_w, my, mx, H, W)
            cell = lab[y1:y2, x1:x2]
            means[i, j] = cell.reshape(-1, 3).mean(axis=0).astype(np.float32)
    return means  # (grid,grid,3), float32


# -------------------- 단독 실행용 --------------------
class PiCam2Capture:
    """Picamera2 캡처 래퍼 (단독 실행에만 사용)"""
    def __init__(self):
        from picamera2 import Picamera2
        self.picam2 = Picamera2()
        cfg = self.picam2.create_preview_configuration(
            main={"size": FRAME_SIZE, "format": "RGB888"},
            controls={"FrameRate": FPS}
        )
        self.picam2.configure(cfg)
        self.picam2.start()
        if not USE_AUTO_EXPOSURE:
            self.picam2.set_controls({"AeEnable": False, "AwbEnable": False})
            self.picam2.set_controls({"ExposureTime": EXPOSURE_TIME, "AnalogueGain": ANALOG_GAIN})

    def read(self):
        rgb = self.picam2.capture_array()
        frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if HFLIP:
            frame = cv2.flip(frame, 1)
        if VFLIP:
            frame = cv2.flip(frame, 0)
        return True, frame

    def release(self):
        try:
            self.picam2.stop()
        except Exception:
            pass


def run():
    """단독 실행: 화면 창에 warp+diff 표시, 'b'로 기준 설정/갱신"""
    cap = PiCam2Capture()

    lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
    upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)

    base_board_values = None     # (LAB) 메모리 기준값
    prev_warp = None
    ema_means = None
    prev_diff = None

    cv2.namedWindow(SHOW_WINDOW_NAME, cv2.WINDOW_NORMAL)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            corners = find_green_corners(frame.copy(), lower, upper, min_area=60)

            # 와핑 (코너 없으면 이전 warp 유지)
            if corners is not None:
                warp = warp_chessboard(frame, corners, size=WARP_SIZE)
                prev_warp = warp
            else:
                warp = prev_warp if prev_warp is not None else frame

            vis = warp.copy()

            # 기준값이 없으면 안내만 표시
            if base_board_values is None:
                cv2.putText(vis, "NO BASE: press 'b' to set base from current warp",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
                cv2.imshow(SHOW_WINDOW_NAME, vis)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('b'):
                    base_board_values = compute_board_means_LAB(warp, grid=GRID, margin_ratio=CELL_MARGIN_RATIO)
                    ema_means = None
                    prev_diff = None
                    print("[Base] 기준값 설정 완료 (LAB):", base_board_values.shape, base_board_values.dtype)
                elif key in (27, ord('q')):
                    break
                continue

            # --- LAB 셀 평균 및 EMA ---
            lab = cv2.cvtColor(warp, cv2.COLOR_BGR2LAB)
            H, W = lab.shape[:2]
            cs_h, cs_w, my, mx = _split_sizes(H, W, GRID)

            means = np.zeros((GRID, GRID, 3), np.float32)
            for i in range(GRID):
                for j in range(GRID):
                    y1, y2, x1, x2 = _cell_region(i, j, cs_h, cs_w, my, mx, H, W)
                    cell = lab[y1:y2, x1:x2]
                    means[i, j] = cell.reshape(-1, 3).mean(axis=0).astype(np.float32)

            if ema_means is None:
                ema_means = means.copy()
            else:
                ema_means = EMA_ALPHA * means + (1.0 - EMA_ALPHA) * ema_means

            diffs_now = np.linalg.norm(ema_means - base_board_values, axis=2).astype(np.float32)
            if prev_diff is None:
                smooth_diff = diffs_now
            else:
                smooth_diff = DIFF_ALPHA * diffs_now + (1.0 - DIFF_ALPHA) * prev_diff
            prev_diff = smooth_diff

            # --- 시각화 ---
            for i in range(GRID):
                for j in range(GRID):
                    y1 = i * cs_h; x1 = j * cs_w
                    val = int(round(smooth_diff[i, j]))
                    cv2.putText(vis, str(val), (x1 + 2, y1 + cs_h // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

            flat_vals = smooth_diff.flatten()
            idx_sorted = np.argsort(-flat_vals)
            drawn = 0
            for idx in idx_sorted:
                if drawn >= TOP_K:
                    break
                if flat_vals[idx] < THRESHOLD:
                    break
                i = idx // GRID
                j = idx % GRID
                x1, y1 = j * cs_w, i * cs_h
                x2, y2 = (j + 1) * cs_w, (i + 1) * cs_h
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
                drawn += 1

            cv2.putText(vis, "BASE: SET (press 'c' to clear / 'b' to reset)", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2, cv2.LINE_AA)
            cv2.imshow(SHOW_WINDOW_NAME, vis)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('b'):
                base_board_values = compute_board_means_LAB(warp, grid=GRID, margin_ratio=CELL_MARGIN_RATIO)
                ema_means = None
                prev_diff = None
                print("[Base] 기준값 재설정 완료 (LAB)")
            elif key == ord('c'):
                base_board_values = None
                ema_means = None
                prev_diff = None
                print("[Base] 기준값 초기화")
            elif key in (27, ord('q')):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()


# -------------------- Flask 스트리밍용 --------------------
def gen_edges_frames(cap, base_board_path='init_board_values.npy', threshold=12.0, top_k=4):
    """
    main.py에서 /piece 라우트로 사용하는 제너레이터.
    - cap: cv2.VideoCapture(0) 같은 OpenCV 캡처
    - base_board_path: main.py가 저장한 기준값 파일 (BGR 평균값 8x8x3 float32)
    - threshold: diff 문턱 (정수 표시 기준도 같게 사용)
    - top_k: diff 상위 박스 표시 개수
    """
    # 기준값(BGR) 로드
    base_board_values = None
    if os.path.exists(base_board_path):
        try:
            base_board_values = np.load(base_board_path)
            # 기대형태: (8,8,3) float32
        except Exception as e:
            print(f"[piece_recognition] 기준값 로드 실패: {e}")
            base_board_values = None
    else:
        print(f"[piece_recognition] 기준값 파일 없음: {base_board_path}")

    prev_warp = None
    lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
    upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # 코너 검출 & 와핑
        corners = find_green_corners(frame.copy(), lower, upper, min_area=60)
        if corners is not None:
            warp = warp_chessboard(frame, corners, size=WARP_SIZE)
            prev_warp = warp
        else:
            warp = prev_warp if prev_warp is not None else frame

        vis = warp.copy()

        # 기준이 있으면 BGR 평균과 비교 (main.py와 동일 스킴)
        if base_board_values is not None and base_board_values.shape == (GRID, GRID, 3):
            H, W = warp.shape[:2]
            cs_h, cs_w = H // GRID, W // GRID
            diffs = np.zeros((GRID, GRID), np.float32)

            for i in range(GRID):
                for j in range(GRID):
                    y1, y2 = i * cs_h, (i + 1) * cs_h
                    x1, x2 = j * cs_w, (j + 1) * cs_w
                    cell = warp[y1:y2, x1:x2]
                    mean_bgr = np.mean(cell.reshape(-1, 3), axis=0)
                    diff = np.linalg.norm(mean_bgr - base_board_values[i, j])
                    diffs[i, j] = diff
                    cv2.putText(vis, str(int(diff)), (x1 + 2, y1 + cs_h // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

            flat = diffs.flatten()
            idx_sorted = np.argsort(-flat)
            for k in range(min(top_k, len(idx_sorted))):
                idx = idx_sorted[k]
                if flat[idx] < threshold:
                    break
                i = idx // GRID
                j = idx % GRID
                x1, y1 = j * cs_w, i * cs_h
                x2, y2 = (j + 1) * cs_w, (i + 1) * cs_h
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
        else:
            cv2.putText(vis, "NO BASE FILE: set in web UI (Set Initial Board)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)

        # JPEG로 인코딩하여 MJPEG 스트리밍
        _, buffer = cv2.imencode('.jpg', vis)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


# -------------------- 엔트리 --------------------
if __name__ == "__main__":
    run()
