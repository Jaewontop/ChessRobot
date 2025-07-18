import numpy as np
import cv2
from sklearn.cluster import KMeans
from warping_utils import find_green_corners, find_chessboard_corners, warp_chessboard

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