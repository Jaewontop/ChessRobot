import numpy as np
import cv2
from sklearn.cluster import KMeans
from warping_utils import find_green_corners, find_chessboard_corners, warp_chessboard
import base64

def get_processed_images(frame):
    # 1. 체스판 코너 검출 및 warping
    corners = find_green_corners(frame)
    if corners is None:
        corners = find_chessboard_corners(frame)
    if corners is not None:
        warp = warp_chessboard(frame, corners, size=400)
    else:
        warp = frame.copy()
    h, w = warp.shape[:2]
    cell_size_h = h // 8
    cell_size_w = w // 8
    target_size = (cell_size_w * 8, cell_size_h * 8)
    # 각 칸 평균 HSV색 또는 분홍/베이지 검출 시 검정/흰색으로 채우는 이미지
    color_img = np.zeros_like(warp)
    for i in range(8):
        for j in range(8):
            y1, y2 = i*cell_size_h, (i+1)*cell_size_h
            x1, x2 = j*cell_size_w, (j+1)*cell_size_w
            cell = warp[y1:y2, x1:x2]
            hsv = cv2.cvtColor(cell, cv2.COLOR_BGR2HSV)
            mean_h = int(np.mean(hsv[:,:,0]))
            mean_s = int(np.mean(hsv[:,:,1]))
            mean_v = int(np.mean(hsv[:,:,2]))
            text = f"H:{mean_h} S:{mean_s} V:{mean_v}"
            text_x = x1 + 2
            text_y = y1 + cell_size_h//2
            # 분홍색 마스킹
            lower_pink1 = np.array([140, 60, 60])
            upper_pink1 = np.array([180, 255, 255])
            lower_pink2 = np.array([0, 60, 60])
            upper_pink2 = np.array([15, 255, 255])
            mask_pink1 = cv2.inRange(hsv, lower_pink1, upper_pink1)
            mask_pink2 = cv2.inRange(hsv, lower_pink2, upper_pink2)
            mask_pink = cv2.bitwise_or(mask_pink1, mask_pink2)
            pink_ratio = np.sum(mask_pink > 0) / (cell_size_h * cell_size_w)
            if pink_ratio > 0.003:
                color_img[y1:y2, x1:x2] = (0,255,0)  # 초록색
            cv2.putText(color_img, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,0), 1, cv2.LINE_AA)
            cv2.rectangle(color_img, (x1, y1), (x2, y2), (0,0,255), 1)
    warp_resized = cv2.resize(warp, target_size)
    color_img_resized = cv2.resize(color_img, target_size)
    # 이미지를 JPEG로 인코딩 후 base64로 변환
    _, buf1 = cv2.imencode('.jpg', warp_resized)
    _, buf2 = cv2.imencode('.jpg', color_img_resized)
    import base64
    img1_b64 = base64.b64encode(buf1).decode('utf-8')
    img2_b64 = base64.b64encode(buf2).decode('utf-8')
    return img1_b64, img2_b64

def gen_edges_frames(cap):
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        corners = find_green_corners(frame)
        if corners is None:
            corners = find_chessboard_corners(frame)
        if corners is not None:
            warp = warp_chessboard(frame, corners, size=400)
            h, w = warp.shape[:2]
            cell_size = min(w, h) // 8
            board_img = np.ones((cell_size*8, cell_size*8, 3), dtype=np.uint8) * 255
            cell_colors = []
            for i in range(8):
                for j in range(8):
                    y1, y2 = i*cell_size, (i+1)*cell_size
                    x1, x2 = j*cell_size, (j+1)*cell_size
                    cell = warp[y1:y2, x1:x2]
                    mean_bgr = np.mean(cell.reshape(-1, 3), axis=0)
                    cell_colors.append(mean_bgr)
            cell_colors = np.array(cell_colors)
            # k-means 클러스터링 (k=4)
            kmeans = KMeans(n_clusters=4, n_init=10, random_state=42)
            labels = kmeans.fit_predict(cell_colors)
            cluster_colors = np.uint8(kmeans.cluster_centers_)
            idx = 0
            for i in range(8):
                for j in range(8):
                    color = tuple(int(c) for c in cluster_colors[labels[idx]])
                    y1, y2 = i*cell_size, (i+1)*cell_size
                    x1, x2 = j*cell_size, (j+1)*cell_size
                    cv2.rectangle(board_img, (x1, y1), (x2, y2), color, -1)
                    cv2.rectangle(board_img, (x1, y1), (x2, y2), (0,0,0), 1)
                    idx += 1
            ret2, buffer = cv2.imencode('.jpg', board_img)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blur, 50, 150)
            edges_color = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
            ret2, buffer = cv2.imencode('.jpg', edges_color)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n') 