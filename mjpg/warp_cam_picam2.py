# warp_cam_picam2_stable.py
# Picamera2 로컬 캡처 + 초록 마커 4점 검출 + 코너 안정화 + 투시와핑 + 디버그 화면

import time
import collections
import numpy as np
import cv2
from picamera2 import Picamera2

# ========================= 유틸 / 안정화 =========================
def poly_area(pts: np.ndarray) -> float:
    x = pts[:, 0]; y = pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

def is_valid_quad(pts, min_area=8000, ar_min=0.6, ar_max=1.7) -> bool:
    if pts is None:
        return False
    pts = np.asarray(pts)
    if pts.shape != (4, 2):
        return False
    area = poly_area(pts.astype(np.float32))
    if area < min_area:
        return False
    w1 = np.linalg.norm(pts[1] - pts[0]); w2 = np.linalg.norm(pts[2] - pts[3])
    h1 = np.linalg.norm(pts[3] - pts[0]); h2 = np.linalg.norm(pts[2] - pts[1])
    w = (w1 + w2) / 2.0; h = (h1 + h2) / 2.0
    if w == 0 or h == 0:
        return False
    ar = w / h
    return ar_min <= ar <= ar_max

class CornerStabilizer:
    """중앙값 + EMA로 코너 안정화, 튀는 프레임 무시, 일정 횟수 쌓이면 출력"""
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
            if d > self.max_jump:          # 갑자기 많이 튀면 무시
                self.good_run = 0
                return self.get()

        self.hist.append(corners.astype(np.float32))
        self.good_run = min(self.need_good, self.good_run + 1)

        med = np.median(np.stack(self.hist, axis=0), axis=0)  # 중앙값
        self.ema = med if self.ema is None else (self.alpha * med + (1 - self.alpha) * self.ema)
        return self.get()

    def get(self):
        if self.ema is None or self.good_run < self.need_good:
            return None
        return self.ema.astype(np.float32)

# ========================= 마우스 HSV =========================
class FrameHolder:
    def __init__(self):
        self.frame = None

def mouse_callback(event, x, y, flags, holder: FrameHolder):
    if event == cv2.EVENT_LBUTTONDOWN and holder.frame is not None:
        hsv = cv2.cvtColor(holder.frame, cv2.COLOR_BGR2HSV)
        y = np.clip(y, 0, hsv.shape[0]-1)
        x = np.clip(x, 0, hsv.shape[1]-1)
        H, S, V = hsv[y, x]
        print(f"Clicked at ({x},{y}) → HSV=({int(H)}, {int(S)}, {int(V)})")

# ========================= 코너 검출/정렬/와핑 =========================
def sort_corners_by_position(pts):
    pts = sorted(pts, key=lambda p: (p[1], p[0]))  # y → x
    top_two = sorted(pts[:2], key=lambda p: p[0])
    bot_two = sorted(pts[2:], key=lambda p: p[0])
    return np.array([top_two[0], top_two[1], bot_two[1], bot_two[0]], dtype=np.float32)

def find_green_corners(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # 조명에 따라 조정 가능(마스크가 약하면 S/V 하한 더 낮추기)
    lower_green = np.array([65, 65, 65], dtype=np.uint8)
    upper_green = np.array([84, 255, 255], dtype=np.uint8)

    mask = cv2.inRange(hsv, lower_green, upper_green)
    k = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    cv2.imshow("Green Mask", mask)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:8]

    centers = []
    for c in cnts:
        if cv2.contourArea(c) < 80:
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"]/M["m00"]); cy = int(M["m01"]/M["m00"])
        centers.append([cx, cy])

    # 근접 중복 제거
    dedup = []
    for c in centers:
        if all(np.hypot(c[0]-d[0], c[1]-d[1]) > 10 for d in dedup):
            dedup.append(c)
    centers = dedup

    for i,(cx,cy) in enumerate(centers):
        cv2.circle(frame, (cx,cy), 6, (0,255,0), -1)
        cv2.putText(frame, str(i), (cx+10,cy), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

    if len(centers) == 4:
        return sort_corners_by_position(centers)
    return None

def warp_chessboard(frame, corners, size=480):
    if corners is None:
        return None
    corners = np.asarray(corners, dtype=np.float32)
    if corners.shape != (4,2):
        print(f"[warp] invalid corners shape: {corners.shape}")
        return None
    dst = np.array([[0,0],[size-1,0],[size-1,size-1],[0,size-1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(corners, dst)
    return cv2.warpPerspective(frame, M, (size, size))

# ========================= 메인 =========================
def main():
    # ---- Picamera2 설정 ----
    picam2 = Picamera2()
    cfg = picam2.create_preview_configuration(
        main={"size": (1280, 720), "format": "RGB888"},
        controls={"FrameRate": 30}
    )
    picam2.configure(cfg)
    picam2.start()

    # 뒤집힘이 느껴지면 아래를 True로 변경
    HFLIP = False
    VFLIP = False

    # 노출/화이트밸런스 고정(깜빡임 방지) — 환경에 맞게 조정 가능
    time.sleep(1.0)  # 자동이 자리잡도록 잠깐 대기
    picam2.set_controls({"AeEnable": False, "AwbEnable": False})
    # 필요 시 수동값 추가:
    # picam2.set_controls({"ExposureTime": 8000, "AnalogueGain": 1.8})

    stabilizer = CornerStabilizer(hist_len=7, ema_alpha=0.35, max_jump=60, need_good=3)

    holder = FrameHolder()
    cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Frame", mouse_callback, holder)

    while True:
        rgb = picam2.capture_array()              # RGB
        frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if HFLIP: frame = cv2.flip(frame, 1)
        if VFLIP: frame = cv2.flip(frame, 0)

        holder.frame = frame
        disp = frame.copy()

        raw_corners = find_green_corners(disp)
        if raw_corners is not None and not is_valid_quad(raw_corners, min_area=8000):
            raw_corners = None

        stable_corners = stabilizer.update(raw_corners)

        if stable_corners is not None:
            warp = warp_chessboard(frame, stable_corners, size=480)
        else:
            warp = np.zeros((480, 480, 3), dtype=np.uint8)

        # 에지 디버그(선택사항)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5,5), 0), 50, 150)
        cv2.imshow("Edges", edges)

        # 디버그 표시(원시=빨강, 안정화=초록)
        if raw_corners is not None:
            for p in raw_corners.astype(int):
                cv2.circle(disp, tuple(p), 5, (0,0,255), -1)
        if stable_corners is not None:
            for p in stable_corners.astype(int):
                cv2.circle(disp, tuple(p), 5, (0,255,0), -1)

        cv2.imshow("Frame", disp)
        cv2.imshow("Warped", warp)

        k = cv2.waitKey(1) & 0xFF
        if k in (27, ord('q')):
            break

    picam2.stop()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
