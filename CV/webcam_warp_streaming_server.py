from flask import Flask, Response
import cv2
import numpy as np
from sklearn.cluster import KMeans

app = Flask(__name__)
cap = cv2.VideoCapture(0)

def find_chessboard_corners(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    max_area = 0
    best_quad = None
    for cnt in contours:
        epsilon = 0.02 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            area = cv2.contourArea(approx)
            if area > max_area:
                max_area = area
                best_quad = approx
    if best_quad is not None:
        corners = best_quad.reshape(4, 2)
        return order_points(corners)
    return None

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def warp_chessboard(frame, corners, size=400):
    dst = np.array([
        [0, 0],
        [size-1, 0],
        [size-1, size-1],
        [0, size-1]
    ], dtype="float32")
    M = cv2.getPerspectiveTransform(corners, dst)
    warp = cv2.warpPerspective(frame, M, (size, size))
    return warp

def find_orange_corners(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # 주황색 범위 (필요시 조정)
    lower_orange = np.array([5, 100, 100])
    upper_orange = np.array([20, 255, 255])
    mask = cv2.inRange(hsv, lower_orange, upper_orange)
    # 노이즈 제거
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    centers = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 50:  # 너무 작은 점은 무시
            M = cv2.moments(cnt)
            if M['m00'] != 0:
                cx = int(M['m10']/M['m00'])
                cy = int(M['m01']/M['m00'])
                centers.append([cx, cy])
    if len(centers) == 4:
        return order_points(np.array(centers, dtype=np.float32))
    return None

def find_green_corners(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_green = np.array([40, 100, 100])
    upper_green = np.array([80, 255, 255])
    mask = cv2.inRange(hsv, lower_green, upper_green)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    centers = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 50:
            M = cv2.moments(cnt)
            if M['m00'] != 0:
                cx = int(M['m10']/M['m00'])
                cy = int(M['m01']/M['m00'])
                centers.append([cx, cy])
    if len(centers) == 4:
        pts = np.array(centers, dtype=np.float32)
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect
    return None

def gen_warped_frames():
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        corners = find_green_corners(frame)
        if corners is None:
            corners = find_chessboard_corners(frame)
        if corners is not None:
            warp = warp_chessboard(frame, corners)
            ret2, buffer = cv2.imencode('.jpg', warp)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            ret2, buffer = cv2.imencode('.jpg', gray)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

def gen_original_frames():
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # 연두색 마커 검출 (HSV 범위는 필요시 조정)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_green = np.array([40, 100, 100])   # 연두색(형광 녹색) 범위 예시
        upper_green = np.array([80, 255, 255])
        mask = cv2.inRange(hsv, lower_green, upper_green)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        disp = frame.copy()
        centers = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 50:
                # 빨간색 테두리로 컨투어 그리기
                cv2.drawContours(disp, [cnt], -1, (0,0,255), 3)
                # 중심점 계산
                M = cv2.moments(cnt)
                if M['m00'] != 0:
                    cx = int(M['m10']/M['m00'])
                    cy = int(M['m01']/M['m00'])
                    centers.append([cx, cy])
                    cv2.circle(disp, (cx, cy), 8, (0,255,0), -1)  # 중심점 초록색 원
        if len(centers) == 4:
            pts = np.array(centers, dtype=np.float32)
            # 좌상-우상-우하-좌하 순서로 정렬
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]
            rect_int = rect.astype(int)
            cv2.polylines(disp, [rect_int], isClosed=True, color=(0,255,0), thickness=4)
        ret2, buffer = cv2.imencode('.jpg', disp)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

def gen_edges_frames():
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

@app.route('/warp')
def warp_feed():
    return Response(gen_warped_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/original')
def original_feed():
    return Response(gen_original_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/edges')
def edges_feed():
    return Response(gen_edges_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return '''
    <h1>체스판 스트리밍</h1>
    <div style="display: flex; gap: 20px;">
      <div>
        <h3 style="margin:0; font-size:16px;">원본</h3>
        <img src="/original" width="400" height="300" style="border:1px solid #aaa;">
      </div>
      <div>
        <h3 style="margin:0; font-size:16px;">와핑</h3>
        <img src="/warp" width="240" height="240" style="border:1px solid #aaa;">
      </div>
      <div>
        <h3 style="margin:0; font-size:16px;">경계(에지)</h3>
        <img src="/edges" width="240" height="180" style="border:1px solid #aaa;">
      </div>
    </div>
    '''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False) 