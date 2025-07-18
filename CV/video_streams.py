import cv2
import numpy as np
from piece_recognition import gen_edges_frames as _gen_edges_frames
from warping_utils import find_chessboard_corners, order_points, warp_chessboard, find_green_corners

def gen_warped_frames(cap):
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

def gen_original_frames(cap):
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_green = np.array([40, 100, 100])
        upper_green = np.array([80, 255, 255])
        mask = cv2.inRange(hsv, lower_green, upper_green)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        disp = frame.copy()
        centers = []
        hsv_values = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 50:
                cv2.drawContours(disp, [cnt], -1, (0,0,255), 3)
                M = cv2.moments(cnt)
                if M['m00'] != 0:
                    cx = int(M['m10']/M['m00'])
                    cy = int(M['m01']/M['m00'])
                    centers.append([cx, cy])
                    cv2.circle(disp, (cx, cy), 8, (0,255,0), -1)
                    hsv_values.append([int(x) for x in hsv[cy, cx]])
        if len(centers) == 4:
            pts = np.array(centers, dtype=np.float32)
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
        # 프레임과 HSV값을 같이 반환 (튜플)
        yield (frame_bytes, hsv_values)

def gen_edges_frames(cap):
    yield from _gen_edges_frames(cap) 