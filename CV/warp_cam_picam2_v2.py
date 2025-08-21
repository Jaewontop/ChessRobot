# warp_cam_picam2_stable_v2.py
# Picamera2 + 초록 마커 4점 검출 + (옵션)기하검증 + (옵션)안정화 + 보수적 홀드(최근값 유지) + 자세한 로깅

import time, collections
import numpy as np
import cv2
from picamera2 import Picamera2

# ======================== CONFIG ========================
Hmin, Hmax = 65, 84
Smin, Smax = 65, 255
Vmin, Vmax = 65, 255

# 카메라 제어
FRAME_SIZE = (1280, 720)
FPS = 30
HFLIP = False
VFLIP = False
USE_AUTO_EXPOSURE = True   # 자동 노출 유지
EXPOSURE_TIME = 8000       # AeEnable=False 일 때만 유효(마이크로초)
ANALOG_GAIN = 1.8          # 적당한 게인

# 검출/기하 조건
MIN_CONTOUR_AREA = 100     # 더 큰 영역만 허용 (노이즈 제거)
USE_GEOMETRY_CHECK = True  # 기하 검증 다시 켜기
MIN_QUAD_AREA = 5000       # 적당한 영역
AR_MIN, AR_MAX = 0.6, 2.0 # 체스보드 비율에 맞게 조정

# 안정화
USE_STABILIZER = True      # 안정화 켜기
EMA_ALPHA = 0.3            # 더 안정적인 값
MAX_JUMP = 50.0            # 더 엄격한 점프 제한
NEED_GOOD = 3              # 더 많은 좋은 프레임 필요
HOLD_LAST_N_FRAMES = 20    # 더 오래 홀드

# 로깅
VERBOSE = True             # 내부 결정 과정을 터미널에 자세히 출력
SHOW_EDGES = False
SHOW_MASK = True           # 마스크 표시 (디버깅용)
# =====================================================================


# ------------------------ 유틸/검증/안정화 ------------------------
def poly_area(pts: np.ndarray) -> float:
    x = pts[:, 0]; y = pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

def is_valid_quad(pts, min_area=8000, ar_min=0.6, ar_max=1.7):
    if pts is None: 
        return False, "None"
    pts = np.asarray(pts)
    if pts.shape != (4, 2):
        return False, f"shape={pts.shape}"
    area = poly_area(pts.astype(np.float32))
    if area < min_area:
        return False, f"area<{min_area} ({area:.1f})"
    w1 = np.linalg.norm(pts[1] - pts[0]); w2 = np.linalg.norm(pts[2] - pts[3])
    h1 = np.linalg.norm(pts[3] - pts[0]); h2 = np.linalg.norm(pts[2] - pts[1])
    w = (w1 + w2) / 2.0; h = (h1 + h2) / 2.0
    if w == 0 or h == 0:
        return False, "zero width/height"
    ar = w / h
    if not (ar_min <= ar <= ar_max):
        return False, f"ar={ar:.2f} out of [{ar_min},{ar_max}]"
    return True, f"ok area={area:.0f}, ar={ar:.2f}"

class CornerStabilizer:
    def __init__(self, hist_len=7, ema_alpha=0.35, max_jump=60.0, need_good=3):
        self.hist = collections.deque(maxlen=hist_len)
        self.ema = None
        self.alpha = ema_alpha
        self.max_jump = max_jump
        self.need_good = need_good
        self.good_run = 0

    def update(self, corners):
        if corners is None or np.asarray(corners).shape != (4, 2):
            self.good_run = 0
            return self.get()
        if self.ema is not None:
            d = np.linalg.norm(self.ema - corners, axis=1).mean()
            if d > self.max_jump:   # 갑자기 튀면 무시
                return self.get()
        self.hist.append(corners.astype(np.float32))
        self.good_run = min(self.need_good, self.good_run + 1)
        med = np.median(np.stack(self.hist, axis=0), axis=0)
        self.ema = med if self.ema is None else (self.alpha * med + (1 - self.alpha) * self.ema)
        return self.get()

    def get(self):
        if self.ema is None or self.good_run < self.need_good:
            return None
        return self.ema.astype(np.float32)


# ------------------------ 코너 검출/정렬/와핑 ------------------------
def sort_corners_by_position(pts):
    pts = sorted(pts, key=lambda p: (p[1], p[0]))  # y → x
    top = sorted(pts[:2], key=lambda p: p[0])
    bot = sorted(pts[2:], key=lambda p: p[0])
    return np.array([top[0], top[1], bot[1], bot[0]], dtype=np.float32)

def find_green_corners(frame, lower, upper, min_area=60):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower, upper)
    
    # 모폴로지 연산으로 노이즈 제거
    k = np.ones((3,3), np.uint8)  # 더 작은 커널
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

    # 마스크 정보 출력
    mask_fill = mask.mean()/255.0
    if VERBOSE and int(time.time()*3)%3==0:
        print(f"[DBG] mask_fill={mask_fill:.3f}, lower={lower}, upper={upper}")

    # 윤곽선 찾기
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:10]  # 더 많은 윤곽선 검사

    centers = []
    for i, c in enumerate(cnts):
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"]/M["m00"])
        cy = int(M["m01"]/M["m00"])
        centers.append([cx, cy])
        
        if VERBOSE and int(time.time()*3)%3==0:
            print(f"[DBG] contour {i}: area={area:.1f}, center=({cx},{cy})")

    # 근접 중복 제거 (거리 임계값을 더 작게)
    dedup = []
    for c in centers:
        if all(np.hypot(c[0]-d[0], c[1]-d[1]) > 8 for d in dedup):  # 8픽셀로 줄임
            dedup.append(c)
    centers = dedup

    if VERBOSE and int(time.time()*3)%3==0:
        print(f"[DBG] final centers={len(centers)}: {centers}")

    if len(centers) == 4:
        sorted_corners = sort_corners_by_position(centers)
        if VERBOSE:
            print(f"[DBG] corners sorted: {sorted_corners.tolist()}")
        return sorted_corners
    elif len(centers) > 4:
        # 4개보다 많으면 가장 큰 4개만 선택
        if VERBOSE:
            print(f"[DBG] too many centers ({len(centers)}), selecting largest 4")
        # 면적으로 정렬하여 가장 큰 4개 선택
        areas = []
        for c in centers:
            # 해당 중심점 근처의 마스크 픽셀 수 계산
            x, y = int(c[0]), int(c[1])
            area = np.sum(mask[max(0,y-10):min(mask.shape[0],y+10), 
                             max(0,x-10):min(mask.shape[1],x+10)]) / 255
            areas.append(area)
        
        # 면적으로 정렬하여 상위 4개 선택
        sorted_indices = np.argsort(areas)[::-1][:4]
        selected_centers = [centers[i] for i in sorted_indices]
        sorted_corners = sort_corners_by_position(selected_centers)
        if VERBOSE:
            print(f"[DBG] selected corners: {sorted_corners.tolist()}")
        return sorted_corners
    
    return None

def warp_chessboard(frame, corners, size=480):
    if corners is None:
        if VERBOSE: print("[warp] corners is None")
        return None
    
    try:
        c = np.asarray(corners, dtype=np.float32)
        if c.shape != (4, 2):
            if VERBOSE: print(f"[warp] invalid shape: {c.shape}")
            return None
        
        # 코너 순서 확인 및 정렬
        c = sort_corners_by_position(c)
        
        # 와핑 크기 설정
        dst = np.array([[0, 0], [size-1, 0], [size-1, size-1], [0, size-1]], dtype=np.float32)
        
        # 투시 변환 행렬 계산
        M = cv2.getPerspectiveTransform(c, dst)
        
        # 와핑 실행
        warped = cv2.warpPerspective(frame, M, (size, size))
        
        if VERBOSE and int(time.time()*2)%2==0:
            print(f"[warp] success: corners={c.tolist()}, size={size}")
        
        return warped
        
    except Exception as e:
        if VERBOSE: print(f"[warp] error: {e}")
        return None


# ------------------------ 메인 ------------------------
def main():
    # Picamera2 설정
    picam2 = Picamera2()
    cfg = picam2.create_preview_configuration(
        main={"size": FRAME_SIZE, "format": "RGB888"},
        controls={"FrameRate": FPS}
    )
    picam2.configure(cfg)
    picam2.start()
    time.sleep(0.7)  # 워밍업

    if not USE_AUTO_EXPOSURE:
        picam2.set_controls({"AeEnable": False, "AwbEnable": False})
        # 필요 시 수동 값 세팅
        picam2.set_controls({"ExposureTime": EXPOSURE_TIME, "AnalogueGain": ANALOG_GAIN})
        if VERBOSE: print(f"[Cam] AE/AWB OFF, ExposureTime={EXPOSURE_TIME}, Gain={ANALOG_GAIN}")
    else:
        if VERBOSE: print("[Cam] AE/AWB ON (디버그와 동일 조건)")

    lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
    upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)

    stabilizer = CornerStabilizer(hist_len=7, ema_alpha=EMA_ALPHA, max_jump=MAX_JUMP, need_good=NEED_GOOD) \
                 if USE_STABILIZER else None

    last_good_corners = None
    hold_counter = 0

    # OpenCV 윈도우 생성 (Qt 의존성 제거)
    try:
        cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)
        cv2.namedWindow("Warped", cv2.WINDOW_NORMAL)
        if SHOW_EDGES:
            cv2.namedWindow("Edges", cv2.WINDOW_NORMAL)
        if SHOW_MASK:
            cv2.namedWindow("Green Mask", cv2.WINDOW_NORMAL)
    except Exception as e:
        print(f"[WARN] 윈도우 생성 실패: {e}")

    print("[INFO] 프로그램 시작. 'q' 또는 ESC로 종료")
    print(f"[INFO] 초록 마커 검출 범위: H({Hmin}-{Hmax}), S({Smin}-{Smax}), V({Vmin}-{Vmax})")

    while True:
        try:
            rgb = picam2.capture_array()
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            if HFLIP: frame = cv2.flip(frame, 1)
            if VFLIP: frame = cv2.flip(frame, 0)

            disp = frame.copy()
            raw_corners = find_green_corners(disp, lower, upper, min_area=MIN_CONTOUR_AREA)

            # (옵션) 기하 검증
            if USE_GEOMETRY_CHECK:
                ok, reason = is_valid_quad(raw_corners, MIN_QUAD_AREA, AR_MIN, AR_MAX)
                if not ok:
                    if VERBOSE and raw_corners is not None:
                        print(f"[Geo] reject: {reason}")
                    raw_corners = None

            # (옵션) 안정화
            if stabilizer is not None:
                stable_corners = stabilizer.update(raw_corners)
            else:
                stable_corners = raw_corners

            # 홀드(최근값 유지)
            use_corners = None
            if stable_corners is not None:
                use_corners = stable_corners
                last_good_corners = stable_corners
                hold_counter = 0
                if VERBOSE and int(time.time()*3)%3==0:
                    print(f"[Status] corners detected: {stable_corners.tolist()}")
            elif last_good_corners is not None and hold_counter < HOLD_LAST_N_FRAMES:
                use_corners = last_good_corners
                hold_counter += 1
                if VERBOSE and hold_counter == 1:
                    print(f"[Hold] using last good corners for up to {HOLD_LAST_N_FRAMES} frames")
            else:
                use_corners = None

            # 디버그 그리기
            if raw_corners is not None:
                for i, p in enumerate(raw_corners.astype(int)):
                    cv2.circle(disp, tuple(p), 5, (0,0,255), -1)  # 원시=빨강
                    cv2.putText(disp, str(i), tuple(p), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
            if stable_corners is not None and USE_STABILIZER:
                for i, p in enumerate(stable_corners.astype(int)):
                    cv2.circle(disp, tuple(p), 5, (0,255,0), -1)  # 안정화=초록
                    cv2.putText(disp, f"S{i}", tuple(p), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

            # 와핑 실행
            warp = warp_chessboard(frame, use_corners, size=480)  # 더 큰 크기로 향상
            if warp is None:
                warp = np.zeros((320,320,3), dtype=np.uint8)
                cv2.putText(warp, "No corners detected", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

            if SHOW_EDGES:
                edges = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),(5,5),0), 50, 150)
                cv2.imshow("Edges", edges)

            # 마스크 표시 (디버깅용)
            if SHOW_MASK:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, lower, upper)
                # 마스크를 컬러로 변환하여 표시
                mask_color = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                cv2.imshow("Green Mask", mask_color)

            cv2.imshow("Frame", disp)
            cv2.imshow("Warped", warp)

            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord('q')):
                break

        except Exception as e:
            print(f"[ERROR] 메인 루프 오류: {e}")
            time.sleep(0.1)

    picam2.stop()
    cv2.destroyAllWindows()
    print("[INFO] 프로그램 종료")

if __name__ == "__main__":
    main()
