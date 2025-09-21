# warp_cam_picam2_stable_v2.py
# Picamera2 + 초록 마커 4점 검출 + (옵션)기하검증 + (옵션)안정화 + 보수적 홀드(최근값 유지) + 자세한 로깅

import time, collections
import numpy as np
import cv2
from picamera2 import Picamera2

# ======================== CONFIG ========================
Hmin, Hmax = 35, 85
Smin, Smax = 50, 255
Vmin, Vmax = 50, 255

# 카메라 제어
FRAME_SIZE = (1280, 720)
FPS = 30
HFLIP = False
VFLIP = False
USE_AUTO_EXPOSURE = True   # 자동 노출 유지
EXPOSURE_TIME = 8000       # AeEnable=False 일 때만 유효(마이크로초)
ANALOG_GAIN = 1.8          # 적당한 게인

# 검출/기하 조건
MIN_CONTOUR_AREA = 50      # 작은 마커도 검출 가능하도록 조정
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

def is_valid_quad(pts, min_area=500, ar_min=0.6, ar_max=1.7):
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

def find_green_corners(frame, lower, upper, min_area=500):
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
        if all(np.hypot(c[0]-d[0], c[1]-d[1]) > 15 for d in dedup):  # 15픽셀로 조정
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

def find_chessboard_by_first_last_squares(frame, white_threshold=180, debug_frame=None):
    """체스보드의 첫 번째와 마지막 베이지색 칸을 찾아서 정사각형 와핑 영역을 결정하는 함수"""
    # 그레이스케일 변환
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # 가우시안 블러로 노이즈 제거
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    
    # 베이지색/흰색 마스크 생성 (임계값보다 밝은 픽셀)
    _, mask = cv2.threshold(blurred, white_threshold, 255, cv2.THRESH_BINARY)
    
    # 모폴로지 연산으로 노이즈 제거
    kernel = np.ones((3,3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    
    # 윤곽선 찾기
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # 면적으로 정렬하여 큰 윤곽선들부터 검사
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    
    # 디버깅용 프레임 생성
    if debug_frame is not None:
        debug_frame[:] = frame.copy()
        # 모든 윤곽선을 파란색으로 그리기
        cv2.drawContours(debug_frame, contours, -1, (255, 0, 0), 2)
    
    # 충분히 큰 베이지색 영역들만 필터링하고 중심점 계산
    white_squares_centers = []
    for i, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        if area > 1000:  # 충분히 큰 영역만
            # 중심점 계산
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                white_squares_centers.append([cx, cy])
                
                # 디버깅용: 큰 영역의 중심점을 빨간색 원으로 표시
                if debug_frame is not None:
                    cv2.circle(debug_frame, (cx, cy), 10, (0, 0, 255), -1)
                    cv2.putText(debug_frame, f"{i}", (cx-5, cy+5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    cv2.putText(debug_frame, f"{area:.0f}", (cx-15, cy-15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    
    if VERBOSE and int(time.time()*2)%2==0:
        print(f"[DBG] 발견된 윤곽선: {len(contours)}개, 유효한 베이지색 칸: {len(white_squares_centers)}개")
    
    if len(white_squares_centers) < 2:
        if VERBOSE and int(time.time()*3)%3==0:
            print(f"[DBG] 충분한 베이지색 칸을 찾지 못함: {len(white_squares_centers)}개")
        return None
    
    # 중심점들을 좌표 기준으로 정렬
    white_squares_centers = np.array(white_squares_centers)
    
    # 체스판의 첫 번째와 마지막 베이지색 칸을 찾기
    # 일반적으로 체스판은 좌상단이 흰색이거나 검정색이므로,
    # 가장 좌상단에 가까운 베이지색 칸과 가장 우하단에 가까운 베이지색 칸을 찾음
    
    # 좌상단에 가장 가까운 점 (x+y가 가장 작은 점)
    first_square = white_squares_centers[np.argmin(white_squares_centers[:, 0] + white_squares_centers[:, 1])]
    
    # 우하단에 가장 가까운 점 (x+y가 가장 큰 점)
    last_square = white_squares_centers[np.argmax(white_squares_centers[:, 0] + white_squares_centers[:, 1])]
    
    # 디버깅용: 첫 번째와 마지막 칸을 초록색으로 표시
    if debug_frame is not None:
        cv2.circle(debug_frame, tuple(first_square.astype(int)), 15, (0, 255, 0), 3)
        cv2.putText(debug_frame, "FIRST", (first_square[0]-20, first_square[1]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        cv2.circle(debug_frame, tuple(last_square.astype(int)), 15, (0, 255, 255), 3)
        cv2.putText(debug_frame, "LAST", (last_square[0]-20, last_square[1]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        # 두 점 사이의 선 그리기
        cv2.line(debug_frame, tuple(first_square.astype(int)), tuple(last_square.astype(int)), (255, 255, 0), 2)
    
    # 두 점 사이의 거리 계산
    distance = np.linalg.norm(last_square - first_square)
    
    if distance < 100:  # 너무 가까우면 유효하지 않음
        if VERBOSE and int(time.time()*3)%3==0:
            print(f"[DBG] 첫 번째와 마지막 칸이 너무 가까움: {distance}")
        return None
    
    # 체스판은 8x8이므로, 첫 번째와 마지막 칸 사이의 거리를 이용해서
    # 전체 체스판의 크기를 추정
    # 일반적으로 체스판은 정사각형이므로, 대각선 거리를 이용
    chessboard_size = int(distance * 1.414)  # 대각선 거리 * sqrt(2)로 근사
    
    # 첫 번째 칸을 기준으로 정사각형 와핑 영역 계산
    # 체스판의 전체 크기에서 8칸이므로, 칸 하나의 크기 추정
    square_size = chessboard_size // 8
    
    # 와핑 영역의 4개 코너 계산
    # 첫 번째 칸에서 시작해서 전체 체스판 크기만큼 확장
    start_x = int(first_square[0] - square_size * 0.5)  # 첫 번째 칸의 절반 크기만큼 왼쪽으로
    start_y = int(first_square[1] - square_size * 0.5)  # 첫 번째 칸의 절반 크기만큼 위쪽으로
    
    end_x = start_x + chessboard_size
    end_y = start_y + chessboard_size
    
    # 이미지 경계 내에서 클리핑
    start_x = max(0, start_x)
    start_y = max(0, start_y)
    end_x = min(frame.shape[1], end_x)
    end_y = min(frame.shape[0], end_y)
    
    # 4개 코너 생성 (sort_corners_by_position과 호환되는 순서)
    corners = np.array([
        [start_x, start_y],      # 좌상단
        [end_x, start_y],        # 우상단
        [end_x, end_y],          # 우하단
        [start_x, end_y]         # 좌하단
    ], dtype=np.float32)
    
    # sort_corners_by_position과 동일한 정렬 적용
    corners = sort_corners_by_position(corners)
    
    # 디버깅용: 와핑 영역을 보라색 사각형으로 표시
    if debug_frame is not None:
        cv2.rectangle(debug_frame, (start_x, start_y), (end_x, end_y), (255, 0, 255), 3)
        cv2.putText(debug_frame, f"Size: {chessboard_size}", (start_x, start_y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
        cv2.putText(debug_frame, f"Square: {square_size}", (start_x, start_y+20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
    
    # 면적 검증
    area = (end_x - start_x) * (end_y - start_y)
    if area < MIN_QUAD_AREA:
        if VERBOSE and int(time.time()*3)%3==0:
            print(f"[DBG] 추정된 체스판 영역 면적 부족: {area}")
        return None
    
    # 종횡비 검증 (정사각형이어야 함)
    width = end_x - start_x
    height = end_y - start_y
    aspect_ratio = width / height if height > 0 else 0
    
    if not (0.8 <= aspect_ratio <= 1.2):  # 정사각형에 가까워야 함
        if VERBOSE and int(time.time()*3)%3==0:
            print(f"[DBG] 추정된 체스판이 정사각형이 아님: {aspect_ratio}")
        return None
    
    if VERBOSE:
        print(f"[DBG] 첫 번째 칸: {first_square}, 마지막 칸: {last_square}")
        print(f"[DBG] 추정된 체스판 크기: {chessboard_size}, 칸 크기: {square_size}")
        print(f"[DBG] 와핑 영역: {corners.tolist()}")
        print(f"[DBG] 발견된 베이지색 칸 수: {len(white_squares_centers)}")
        print(f"[DBG] 거리: {distance:.1f}, 종횡비: {aspect_ratio:.2f}")
    
    return corners

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
        cv2.namedWindow("Debug View", cv2.WINDOW_NORMAL)  # 디버깅용 윈도우 추가
        if SHOW_EDGES:
            cv2.namedWindow("Edges", cv2.WINDOW_NORMAL)
        if SHOW_MASK:
            cv2.namedWindow("White Squares Mask", cv2.WINDOW_NORMAL)
    except Exception as e:
        print(f"[WARN] 윈도우 생성 실패: {e}")

    print("[INFO] 프로그램 시작. 'q' 또는 ESC로 종료")
    print(f"[INFO] 베이지색 칸 검출 임계값: 200")

    while True:
        try:
            rgb = picam2.capture_array()
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            if HFLIP: frame = cv2.flip(frame, 1)
            if VFLIP: frame = cv2.flip(frame, 0)

            disp = frame.copy()
            debug_frame = frame.copy()  # 디버깅용 프레임 생성
            
            # 초록 마커 대신 베이지색 칸으로 체스판 검출
            raw_corners = find_chessboard_by_first_last_squares(disp, white_threshold=200, debug_frame=debug_frame)

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

            # 베이지색 칸 마스크 표시 (디버깅용)
            if SHOW_MASK:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blurred = cv2.GaussianBlur(gray, (3, 3), 0)
                _, mask = cv2.threshold(blurred, 200, 255, cv2.THRESH_BINARY)
                kernel = np.ones((3,3), np.uint8)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                # 마스크를 컬러로 변환하여 표시
                mask_color = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                cv2.imshow("White Squares Mask", mask_color)

            cv2.imshow("Frame", disp)
            cv2.imshow("Warped", warp)
            cv2.imshow("Debug View", debug_frame)  # 디버깅 윈도우 표시

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
