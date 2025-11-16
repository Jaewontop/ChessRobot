# warp_cam_picam2_stable_v2.py (혼합 버전)

import time, collections
import numpy as np
import cv2

# ==== 기본 설정 ====
Hmin, Hmax = 35, 85    # 초록 마커 HSV 범위
Smin, Smax = 60, 255
Vmin, Vmax = 60, 255

FRAME_SIZE = (1280, 720)
FPS = 30
HFLIP = False
VFLIP = False
USE_AUTO_EXPOSURE = True
EXPOSURE_TIME = 8000
ANALOG_GAIN = 1.8

MIN_QUAD_AREA = 5000
AR_MIN, AR_MAX = 0.8, 1.2

EMA_ALPHA = 0.35
MAX_JUMP = 60.0
NEED_GOOD = 3

VERBOSE = True

# ---------------- Utils ----------------
def poly_area(pts):
    x = pts[:,0]; y = pts[:,1]
    return 0.5*abs(np.dot(x,np.roll(y,-1))-np.dot(y,np.roll(x,-1)))

def is_valid_quad(pts, min_area=MIN_QUAD_AREA, ar_min=AR_MIN, ar_max=AR_MAX):
    if pts is None: return False,"None"
    pts = np.asarray(pts, dtype=np.float32)
    if pts.shape!=(4,2): return False,f"shape={pts.shape}"
    area = poly_area(pts)
    if area<min_area: return False,f"area<{min_area}"
    w1=np.linalg.norm(pts[1]-pts[0]); w2=np.linalg.norm(pts[2]-pts[3])
    h1=np.linalg.norm(pts[3]-pts[0]); h2=np.linalg.norm(pts[2]-pts[1])
    w=(w1+w2)/2; h=(h1+h2)/2
    if w<=1e-6 or h<=1e-6: return False,"zero"
    ar=w/h
    if not (ar_min<=ar<=ar_max): return False,f"ar={ar:.2f}"
    return True,f"ok area={area:.0f}, ar={ar:.2f}"

def sort_corners_by_position(pts):
    pts=sorted(pts,key=lambda p:(p[1],p[0]))
    top=sorted(pts[:2],key=lambda p:p[0])
    bot=sorted(pts[2:],key=lambda p:p[0])
    return np.array([top[0],top[1],bot[1],bot[0]],dtype=np.float32)

# ---------------- Stabilizer ----------------
class CornerStabilizer:
    def __init__(self,hist_len=7,ema_alpha=EMA_ALPHA,max_jump=MAX_JUMP,need_good=NEED_GOOD):
        self.hist=collections.deque(maxlen=hist_len)
        self.ema=None
        self.alpha=ema_alpha
        self.max_jump=max_jump
        self.need_good=need_good
        self.good_run=0
    def update(self,corners):
        if corners is None or np.asarray(corners).shape!=(4,2):
            self.good_run=0
            return self.get()
        corners=np.asarray(corners,dtype=np.float32)
        if self.ema is not None:
            d=np.linalg.norm(self.ema-corners,axis=1).mean()
            if d>self.max_jump: return self.get()
        self.hist.append(corners)
        self.good_run=min(self.need_good,self.good_run+1)
        med=np.median(np.stack(self.hist,axis=0),axis=0)
        self.ema = med if self.ema is None else (self.alpha*med+(1-self.alpha)*self.ema)
        return self.get()
    def get(self):
        if self.ema is None or self.good_run<self.need_good: return None
        return self.ema.astype(np.float32)

# ---------------- Green Marker Detection ----------------
def find_green_corners(frame):
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    lower=np.array([Hmin,Smin,Vmin]); upper=np.array([Hmax,Smax,Vmax])
    mask=cv2.inRange(hsv,lower,upper)

    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    pts=[]
    for c in contours:
        if cv2.contourArea(c)<200: continue
        M=cv2.moments(c)
        if M["m00"]==0: continue
        cx=int(M["m10"]/M["m00"]); cy=int(M["m01"]/M["m00"])
        pts.append([cx,cy])

    if len(pts)<4: return None
    pts=np.array(pts,dtype=np.float32)
    if len(pts)>4:
        # 가장 바깥쪽 4점 선택
        rect=cv2.minAreaRect(pts)
        box=cv2.boxPoints(rect)
        pts=box.astype(np.float32)
    return sort_corners_by_position(pts)

# ---------------- Beige Square / Fallback ----------------
def find_chessboard_by_first_last_squares(frame, white_threshold=180):
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    _,mask=cv2.threshold(gray,white_threshold,255,cv2.THRESH_BINARY)
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)

    centers=[]
    for cnt in contours:
        if cv2.contourArea(cnt)<1000: continue
        M=cv2.moments(cnt)
        if M["m00"]==0: continue
        cx=int(M["m10"]/M["m00"]); cy=int(M["m01"]/M["m00"])
        centers.append([cx,cy])
    if len(centers)>=2:
        pts=np.array(centers)
        first=pts[np.argmin(pts[:,0]+pts[:,1])]
        last =pts[np.argmax(pts[:,0]+pts[:,1])]
        dist=float(np.linalg.norm(last-first))
        if dist>100:
            chess_size=int(dist*1.414)
            sx=int(first[0]); sy=int(first[1])
            ex=sx+chess_size; ey=sy+chess_size
            corners=np.array([[sx,sy],[ex,sy],[ex,ey],[sx,ey]],dtype=np.float32)
            ok,_=is_valid_quad(corners)
            if ok:
                if VERBOSE: print("[DBG] beige corners OK")
                return sort_corners_by_position(corners)

    if contours:
        c=max(contours,key=cv2.contourArea)
        peri=cv2.arcLength(c,True)
        approx=cv2.approxPolyDP(c,0.02*peri,True)
        if len(approx)==4:
            corners=approx.reshape(4,2)
            ok,_=is_valid_quad(corners)
            if ok:
                if VERBOSE: print("[DBG] fallback contour corners OK")
                return sort_corners_by_position(corners)
    return None

# ---------------- Mixed API ----------------
def find_chessboard_corners(frame):
    corners = find_green_corners(frame)
    if corners is not None:
        if VERBOSE: print("[DBG] green corners OK")
        dbg = debug_draw_corners(frame, corners)
        cv2.imshow("DBG_CORNERS", dbg)
        cv2.waitKey(1)
        return corners

    corners = find_chessboard_by_first_last_squares(frame)
    if corners is not None:
        dbg = debug_draw_corners(frame, corners, color=(0,0,255))
        cv2.imshow("DBG_CORNERS", dbg)
        cv2.waitKey(1)
    return corners

# ---------------- Debug Overlay ----------------
def debug_draw_corners(frame, corners, color=(0,255,0)):
    dbg = frame.copy()
    if corners is not None and len(corners) == 4:
        for (x, y) in corners:
            cv2.circle(dbg, (int(x), int(y)), 8, color, -1)
        pts = np.array(corners, dtype=np.int32).reshape((-1,1,2))
        cv2.polylines(dbg, [pts], isClosed=True, color=(0,255,255), thickness=2)
    return dbg

# ---------------- Warp ----------------
def warp_chessboard(frame,corners,size=400):
    if corners is None: return None
    c=np.asarray(corners,dtype=np.float32)
    c=sort_corners_by_position(c)
    dst=np.array([[0,0],[size-1,0],[size-1,size-1],[0,size-1]],dtype=np.float32)
    M=cv2.getPerspectiveTransform(c,dst)
    return cv2.warpPerspective(frame,M,(size,size))

# ---------------- Warp Utils for Grid/Labels ----------------
def compute_warp_transform(corners, size=600):
    if corners is None:
        return None, None
    c = np.asarray(corners, dtype=np.float32)
    c = sort_corners_by_position(c)
    dst = np.array([[0,0],[size-1,0],[size-1,size-1],[0,size-1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(c, dst)
    Minv = np.linalg.inv(M)
    return M, Minv

def generate_playable_square_centers(size=600, grid_size=8, playable_parity=1):
    cell = size // grid_size
    centers = []  # list of (idx1to32, (cx, cy)) in warp space
    index = 1
    for r in range(grid_size):
        for c in range(grid_size):
            if (r + c) % 2 == playable_parity:
                cx = c * cell + cell // 2
                cy = r * cell + cell // 2
                centers.append((index, (float(cx), float(cy)), r, c))
                index += 1
    return centers

def draw_numbers_on_image(image, labeled_points, font_scale=0.6, thickness=2, color=(0,255,0)):
    img = image.copy()
    for idx, (x, y) in labeled_points:
        cv2.putText(img, str(idx), (int(x)-10, int(y)+10), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
    return img

def overlay_grid_and_numbers_on_warp(warp_image, size=600, playable_parity=1):
    if warp_image is None:
        return None, []
    img = warp_image.copy()
    grid = 8
    cell = size // grid
    # draw grid
    for i in range(1, grid):
        x = i * cell
        y = i * cell
        cv2.line(img, (x, 0), (x, size), (128, 128, 128), 1)
        cv2.line(img, (0, y), (size, y), (128, 128, 128), 1)
    # label playable squares
    centers = generate_playable_square_centers(size=size, grid_size=grid, playable_parity=playable_parity)
    labeled = [(idx, (cx, cy)) for idx, (cx, cy), r, c in centers]
    img = draw_numbers_on_image(img, labeled, font_scale=0.7, thickness=2, color=(0,255,255))
    return img, labeled

def warp_points_to_original(labeled_points_in_warp, Minv):
    if Minv is None or not labeled_points_in_warp:
        return []
    pts = np.array([[x, y, 1.0] for _, (x, y) in labeled_points_in_warp], dtype=np.float32).T
    mapped = Minv @ pts
    mapped /= mapped[2, :]
    result = []
    for i, (idx, _) in enumerate(labeled_points_in_warp):
        x = float(mapped[0, i])
        y = float(mapped[1, i])
        result.append((idx, (x, y)))
    return result

# ---------------- Camera Wrapper ----------------
class PiCam2Capture:
    def __init__(self,size=(1280,720),fps=30,hflip=False,vflip=False):
        from picamera2 import Picamera2
        self.hflip=hflip; self.vflip=vflip
        self.picam2=Picamera2()
        cfg=self.picam2.create_preview_configuration(
            main={"size":size,"format":"RGB888"},
            controls={"FrameRate":fps}
        )
        self.picam2.configure(cfg)
        self.picam2.start()
        time.sleep(0.7)
    def read(self):
        rgb=self.picam2.capture_array()
        bgr=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
        if bgr.shape[0]>bgr.shape[1]:
            bgr=cv2.rotate(bgr,cv2.ROTATE_90_CLOCKWISE)
        if self.hflip: bgr=cv2.flip(bgr,1)
        if self.vflip: bgr=cv2.flip(bgr,0)
        return True,bgr
    def release(self):
        try: self.picam2.stop()
        except Exception: pass

# ---------------- Overlay Utils ----------------
def overlay_grid_and_dark_square_numbers(image, start_dark_top_left=True, draw_grid=True, font_scale=0.7, thickness=2, color=(0,255,0)):
    """
    8x8 격자와 어두운 칸(총 32칸)에 1~32 번호를 중앙에 오버레이한다.
    - start_dark_top_left=True이면 좌상단이 어두운 칸으로 간주.
    - draw_grid=True이면 격자 선을 그림.
    """
    if image is None:
        return None
    img = image.copy()
    h, w = img.shape[:2]
    size = min(h, w)
    cell = size // 8

    if draw_grid:
        for i in range(9):
            x = i * cell
            y = i * cell
            cv2.line(img, (0, y), (cell*8, y), (200,200,200), 1)
            cv2.line(img, (x, 0), (x, cell*8), (200,200,200), 1)

    number = 1
    for r in range(8):
        for c in range(8):
            dark = ((r + c) % 2 == 0) if start_dark_top_left else ((r + c) % 2 == 1)
            if not dark:
                continue
            cx = c * cell + cell // 2
            cy = r * cell + cell // 2
            text = str(number)
            (tw, th), bl = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
            tx = int(cx - tw / 2)
            ty = int(cy + th / 2)
            # 외곽선 가독성 향상
            cv2.putText(img, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0,0,0), thickness+2, cv2.LINE_AA)
            cv2.putText(img, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
            number += 1
            if number > 32:
                break
        if number > 32:
            break

    return img