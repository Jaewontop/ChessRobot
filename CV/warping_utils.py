import cv2
import numpy as np

# 마우스로 클릭한 HSV 값 확인용 콜백 함수
def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        frame = param["frame"]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        pixel = hsv[y, x]
        print(f"Clicked at ({x}, {y}) → HSV: ({pixel[0]}, {pixel[1]}, {pixel[2]})")

# 4개 점 정렬 (좌상, 우상, 우하, 좌하)
def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

# 초록색 마커 4개 검출
def find_green_corners(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_green = np.array([40, 90, 200])
    upper_green = np.array([55, 140, 255])

    mask = cv2.inRange(hsv, lower_green, upper_green)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:4]

    centers = []
    for cnt in contours:
        M = cv2.moments(cnt)
        if M['m00'] != 0:
            cx = int(M['m10']/M['m00'])
            cy = int(M['m01']/M['m00'])
            centers.append([cx, cy])

    if len(centers) == 4:
        pts = np.array(centers, dtype=np.float32)

        # 디버깅용 시각화 (중심점)
        for i, (cx, cy) in enumerate(centers):
            cv2.circle(frame, (cx, cy), 6, (0,255,0), -1)
            cv2.putText(frame, str(i), (cx+10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

        return order_points(pts)
    return None

# 체스보드 코너 검출

def find_chessboard_corners(frame, pattern_size=(7, 7)):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    ret, corners = cv2.findChessboardCorners(gray, pattern_size)
    if ret:
        # 코너를 2차원 float32 배열로 변환
        corners = corners.reshape(-1, 2)
        return order_points(corners)
    return None

# 투시 변환 (와핑)
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

# 메인 루프
def main():
    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        disp = frame.copy()
        corners = find_green_corners(disp)

        if corners is not None:
            warp = warp_chessboard(frame, corners)
            cv2.imshow("Warped", warp)


        cv2.imshow("Frame", disp)
        cv2.setMouseCallback("Frame", mouse_callback, {"frame": frame})  # 마우스 콜백 연결

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()