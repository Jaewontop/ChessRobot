# piece_detector.py
# 체스 기물 변화 감지를 위한 독립 모듈
# - gen_edges_frames: 기물 변화를 시각화하는 제너레이터
# - initialize_board: 체스판 초기 상태를 설정하는 함수
# - detect_piece_changes: 기물 변화를 감지하는 함수

import cv2
import numpy as np
import os
from pathlib import Path

# warp_cam_picam2_v2에서 필요한 함수들 import
try:
    from warp_cam_picam2_v2 import (
    find_green_corners,
    warp_chessboard,
    FRAME_SIZE, FPS, HFLIP, VFLIP,
    USE_AUTO_EXPOSURE, EXPOSURE_TIME, ANALOG_GAIN,
    Hmin, Hmax, Smin, Smax, Vmin, Vmax
)
except ImportError:
    # warp_cam_picam2_v2가 없는 경우를 대비한 기본값
    Hmin, Hmax = 35, 85
    Smin, Smax = 50, 255
    Vmin, Vmax = 50, 255
    
    def find_green_corners(frame, lower=None, upper=None, min_area=60):
        """기본 코너 검출 함수 (fallback)"""
        # 간단한 녹색 마커 검출
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        if lower is None:
            lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
        if upper is None:
            upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)
        
        mask = cv2.inRange(hsv, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 가장 큰 4개의 컨투어를 코너로 사용
        if len(contours) >= 4:
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:4]
            corners = []
            for cnt in contours:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    corners.append([cx, cy])
            if len(corners) == 4:
                return np.array(corners, dtype=np.float32)
        return None
    
    def warp_chessboard(frame, corners, size=400):
        """기본 와핑 함수 (fallback)"""
        if corners is None or len(corners) != 4:
            return cv2.resize(frame, (size, size))
        
        # 간단한 원근 변환
        src_points = corners.astype(np.float32)
        dst_points = np.array([[0, 0], [size, 0], [size, size], [0, size]], dtype=np.float32)
        
        matrix = cv2.getPerspectiveTransform(src_points, dst_points)
        warped = cv2.warpPerspective(frame, matrix, (size, size))
        return warped

# ===================== CONFIG =====================
GRID = 8
WARP_SIZE = 400
CELL_MARGIN_RATIO = 0.08

# 기본 설정값
DEFAULT_THRESHOLD = 12.0
DEFAULT_TOP_K = 4

# ==================================================

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
    y1 = max(0, min(y1, H - 1))
    y2 = max(y1 + 1, min(y2, H))
    x1 = max(0, min(x1, W - 1))
    x2 = max(x1 + 1, min(x2, W))
    return y1, y2, x1, x2

def coord_to_chess_notation(i, j):
    """(0,0)=a8, (7,7)=h1 체스 표기로 변환"""
    file = chr(ord('a') + j)  # 열: a, b, c, d, e, f, g, h
    rank = str(8 - i)          # 행: 8, 7, 6, 5, 4, 3, 2, 1
    return file + rank

def compute_board_means_BGR(image_bgr, grid=GRID, margin_ratio=CELL_MARGIN_RATIO):
    """BGR 평균값을 계산하여 반환 (8x8x3 float32)"""
    H, W = image_bgr.shape[:2]
    cs_h, cs_w, my, mx = _split_sizes(H, W, grid)
    means = np.zeros((grid, grid, 3), np.float32)
    
    for i in range(grid):
        for j in range(grid):
            y1, y2, x1, x2 = _cell_region(i, j, cs_h, cs_w, my, mx, H, W)
            cell = image_bgr[y1:y2, x1:x2]
            means[i, j] = cell.reshape(-1, 3).mean(axis=0).astype(np.float32)
    
    return means

def initialize_board(cap, save_path='init_board_values.npy'):
    """
    현재 체스판 상태를 초기 기준값으로 설정
    
    Args:
        cap: OpenCV 캡처 객체
        save_path: 저장할 파일 경로
    
    Returns:
        bool: 초기화 성공 여부
    """
    try:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] 프레임을 읽을 수 없습니다.")
            return False
        
        # 녹색 코너 검출
        lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
        upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)
        corners = find_green_corners(frame.copy(), lower, upper, min_area=60)
        
        if corners is None or len(corners) != 4:
            print("[WARNING] 체스판 코너를 찾을 수 없습니다. 전체 프레임을 사용합니다.")
            warp = cv2.resize(frame, (WARP_SIZE, WARP_SIZE))
        else:
            warp = warp_chessboard(frame, corners, size=WARP_SIZE)
        
        # BGR 평균값 계산
        board_values = compute_board_means_BGR(warp, grid=GRID, margin_ratio=CELL_MARGIN_RATIO)
        
        # 파일로 저장
        np.save(save_path, board_values)
        print(f"[SUCCESS] 초기 기준값 저장 완료: {save_path}")
        print(f"[INFO] 보드 값 형태: {board_values.shape}, 타입: {board_values.dtype}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 초기화 중 오류 발생: {e}")
        return False

def detect_piece_changes(cap, base_board_path='init_board_values.npy', threshold=None, top_k=None):
    """
    기물 변화를 감지하여 변화가 있는 칸들을 반환
    
    Args:
        cap: OpenCV 캡처 객체
        base_board_path: 기준값 파일 경로
        threshold: 변화 감지 임계값 (None이면 기본값 사용)
        top_k: 반환할 최대 변화 칸 수 (None이면 기본값 사용)
    
    Returns:
        list: 변화가 감지된 칸들의 리스트 [(i, j, diff_value), ...]
    """
    if threshold is None:
        threshold = DEFAULT_THRESHOLD
    if top_k is None:
        top_k = DEFAULT_TOP_K
    
    # 기준값 로드
    if not os.path.exists(base_board_path):
        print(f"[ERROR] 기준값 파일이 없습니다: {base_board_path}")
        return []
    
    try:
        base_board_values = np.load(base_board_path)
        if base_board_values.shape != (GRID, GRID, 3):
            print(f"[ERROR] 기준값 형태가 올바르지 않습니다: {base_board_values.shape}")
            return []
    except Exception as e:
        print(f"[ERROR] 기준값 로드 실패: {e}")
        return []
    
    # 현재 프레임 캡처
    ret, frame = cap.read()
    if not ret:
        print("[ERROR] 프레임을 읽을 수 없습니다.")
        return []
    
    # 와핑
    lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
    upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)
    corners = find_green_corners(frame.copy(), lower, upper, min_area=60)
    
    if corners is None or len(corners) != 4:
        print("[WARNING] 체스판 코너를 찾을 수 없습니다.")
        return []
    
    warp = warp_chessboard(frame, corners, size=WARP_SIZE)
    
    # 변화 감지
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
    
    # 상위 변화 칸들 찾기
    flat_diffs = diffs.flatten()
    indices = np.argsort(-flat_diffs)
    
    changes = []
    for idx in indices:
        if len(changes) >= top_k:
            break
        
        i = idx // GRID
        j = idx % GRID
        diff_value = flat_diffs[idx]
        
        if diff_value >= threshold:
            changes.append((i, j, diff_value))
        else:
            break
    
    return changes

def detect_move_and_update(cap=None, base_board_path='init_board_values.npy', threshold=None, top_k=None, max_attempts=50):
    """
    기물 변화를 감지하고 감지 후 새로운 기준값으로 업데이트하는 함수
    
    Args:
        cap: OpenCV 캡처 객체 (None이면 내부에서 생성)
        base_board_path: 기준값 파일 경로
        threshold: 변화 감지 임계값 (None이면 기본값 사용)
        top_k: 반환할 최대 변화 칸 수 (None이면 기본값 사용)
        max_attempts: 최대 시도 횟수 (기본 50프레임)
    
    Returns:
        str: 감지된 체스 좌표 문자열 (예: "e2e4") 또는 None
    """
    if threshold is None:
        threshold = DEFAULT_THRESHOLD
    if top_k is None:
        top_k = DEFAULT_TOP_K
    
    # cap이 없으면 내부에서 생성
    created_cap = False
    if cap is None:
        import cv2
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[CV] 웹캠을 열 수 없습니다.")
            return None
        created_cap = True
    
    print(f"[CV] 기물 변화 감지 시작... (최대 {max_attempts}프레임 확인)")
    
    try:
        for attempt in range(max_attempts):
            # 현재 프레임과 기준값 비교
            changes = detect_piece_changes(cap, base_board_path, threshold, top_k)
        
        if len(changes) >= 2:
            # 두 칸 변화 감지됨 - 체스 좌표로 변환
            i1, j1, diff1 = changes[0]
            i2, j2, diff2 = changes[1]
            
            coord1 = coord_to_chess_notation(i1, j1)
            coord2 = coord_to_chess_notation(i2, j2)
            chess_coords = f"{coord1}{coord2}"
            
            print(f"[CV] 기물 변화 감지! {chess_coords} (차이값: {diff1:.1f}, {diff2:.1f})")
            
            # 감지 후 새로운 기준값으로 업데이트
            print("[CV] 새로운 기준값으로 업데이트 중...")
            if initialize_board(cap, base_board_path):
                print("[CV] 기준값 업데이트 완료!")
            else:
                print("[CV] 기준값 업데이트 실패")
            
            return chess_coords
            
        elif len(changes) == 1:
            # 한 칸만 변화 감지됨
            i, j, diff = changes[0]
            coord = coord_to_chess_notation(i, j)
            
            print(f"[CV] 한 칸 변화 감지: {coord} (차이값: {diff:.1f})")
            # 한 칸만 변화된 경우는 기준값 업데이트하지 않음
            
        # 약간 대기
        import time
        time.sleep(0.05)  # 50ms 대기
        
        print(f"[CV] {max_attempts}프레임 확인했지만 유효한 변화를 감지하지 못했습니다.")
        return None
        
    finally:
        # cap을 내부에서 생성했으면 해제
        if created_cap and cap is not None:
            cap.release()

def gen_edges_frames(cap, base_board_path='init_board_values.npy', threshold=None, top_k=None):
    """
    기물 변화를 시각화하는 MJPEG 스트리밍 제너레이터 (기준값 고정)
    
    Args:
        cap: OpenCV 캡처 객체
        base_board_path: 기준값 파일 경로
        threshold: 변화 감지 임계값 (None이면 기본값 사용)
        top_k: 표시할 최대 변화 칸 수 (None이면 기본값 사용)
    
    Yields:
        tuple: (frame_data, chess_coords) 형태
        - frame_data: MJPEG 프레임 데이터
        - chess_coords: 변화된 체스 좌표 문자열 (예: "e2 e4" 또는 "d5")
    """
    if threshold is None:
        threshold = DEFAULT_THRESHOLD
    if top_k is None:
        top_k = DEFAULT_TOP_K
    
    # 기준값 로드
    base_board_values = None
    if os.path.exists(base_board_path):
        try:
            base_board_values = np.load(base_board_path)
            if base_board_values.shape != (GRID, GRID, 3):
                print(f"[WARNING] 기준값 형태가 올바르지 않습니다: {base_board_values.shape}")
                base_board_values = None
        except Exception as e:
            print(f"[WARNING] 기준값 로드 실패: {e}")
            base_board_values = None
    else:
        print(f"[INFO] 기준값 파일이 없습니다: {base_board_path}")
    
    prev_warp = None
    lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
    upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)
    
    while True:
        change_coords = []  # 매 프레임마다 초기화
        ret, frame = cap.read()
        if not ret:
            break
        
        # 코너 검출 & 와핑
        corners = find_green_corners(frame.copy(), lower, upper, min_area=60)
        if corners is not None and len(corners) == 4:
            warp = warp_chessboard(frame, corners, size=WARP_SIZE)
            prev_warp = warp
        else:
            warp = prev_warp if prev_warp is not None else frame
        
        vis = warp.copy()
        
        # 기준이 있으면 BGR 평균과 비교
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
                    
                    # 차이값 표시
                    cv2.putText(vis, str(int(diff)), (x1 + 2, y1 + cs_h // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
            
            # 상위 변화 칸들에 박스 표시 및 체스 좌표 표시
            flat_diffs = diffs.flatten()
            indices = np.argsort(-flat_diffs)
            
            drawn_count = 0
            change_coords = []  # 변화된 좌표들을 저장
            
            for idx in indices:
                if drawn_count >= top_k:
                    break
                
                if flat_diffs[idx] < threshold:
                    break
                
                i = idx // GRID
                j = idx % GRID
                x1, y1 = j * cs_w, i * cs_h
                x2, y2 = (j + 1) * cs_w, (i + 1) * cs_h
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
                
                # 체스 좌표 저장
                chess_coord = coord_to_chess_notation(i, j)
                change_coords.append(chess_coord)
                
                drawn_count += 1
            
            # 변화된 두 칸이 있으면 체스 좌표를 화면에 표시
            if len(change_coords) >= 2:
                coord_text = f"{change_coords[0]} {change_coords[1]}"
                cv2.putText(vis, coord_text, (10, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
            elif len(change_coords) == 1:
                coord_text = f"{change_coords[0]}"
                cv2.putText(vis, coord_text, (10, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
        else:
            # 기준값이 없는 경우 안내 메시지
            cv2.putText(vis, "NO BASE FILE: Use initialize_board() first",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
        
        # JPEG로 인코딩하여 MJPEG 스트리밍
        _, buffer = cv2.imencode('.jpg', vis)
        frame_data = (b'--frame\r\n'
                     b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        # 체스 좌표 문자열 생성
        if len(change_coords) >= 2:
            chess_coords = f"{change_coords[0]} {change_coords[1]}"
        elif len(change_coords) == 1:
            chess_coords = change_coords[0]
        else:
            chess_coords = ""
        
        yield (frame_data, chess_coords)

# ===================== 사용 예시 =====================
if __name__ == "__main__":
    # 테스트용 코드
    print("체스 기물 감지 모듈 테스트")
    print("사용 가능한 함수들:")
    print("- initialize_board(cap, save_path): 체스판 초기화")
    print("- detect_piece_changes(cap, base_board_path): 기물 변화 감지")
    print("- detect_move_and_update(cap, base_board_path): 변화 감지 + 기준값 업데이트")
    print("- gen_edges_frames(cap, base_board_path): 변화 시각화 스트리밍")
    print("\n사용법:")
    print("# 기준값 업데이트 방식:")
    print("chess_coords = detect_move_and_update(cap)")
    print("if chess_coords:")
    print("    print(f'감지된 이동: {chess_coords}')")
    print("\n# 스트리밍 방식:")
    print("for frame_data, chess_coords in gen_edges_frames(cap):")
    print("    if chess_coords:")
    print("        print(f'감지된 좌표: {chess_coords}')")
    print("    # frame_data를 웹 스트리밍 등에 사용")
