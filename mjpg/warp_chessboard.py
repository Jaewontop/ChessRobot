import cv2
import numpy as np

cap = cv2.VideoCapture("http://192.168.1.180:5000/?action=stream")

# 마우스로 HSV 확인용
def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        frame = param["frame"]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        pixel = hsv[y, x]
        print(f"Clicked at ({x}, {y}) → HSV: ({pixel[0]}, {pixel[1]}, {pixel[2]})")

# 중심점 4개를 좌상→우상→우하→좌하 순서로 정렬
def sort_corners_by_position(pts):
    pts = sorted(pts, key=lambda x: (x[1], x[0]))  # y 우선, 그다음 x
    top_two = sorted(pts[:2], key=lambda x: x[0])
    bottom_two = sorted(pts[2:], key=lambda x: x[0])
    return np.array([top_two[0], top_two[1], bottom_two[1], bottom_two[0]], dtype="float32")

# 초록 마커 4개 중심 검출
def find_green_corners(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # HSV 범위 (너의 환경에 맞게 조정 가능)
    lower_green = np.array([35, 60, 100])
    upper_green = np.array([80, 255, 255])

    mask = cv2.inRange(hsv, lower_green, upper_green)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))

    cv2.imshow("Green Mask", mask)  # ✅ 마스크 확인용

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:4]

    centers = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 50:
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                centers.append([cx, cy])

    print(f"[find_green_corners] 마커 {len(centers)}개 감지됨")  # ✅ 코너 수 출력

    for i, (cx, cy) in enumerate(centers):
        cv2.circle(frame, (cx, cy), 6, (0, 255, 0), -1)
        cv2.putText(frame, str(i), (cx + 10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    if len(centers) == 4:
        return sort_corners_by_position(centers)
    return None

# 투시 변환 (와핑)
def warp_chessboard(frame, corners, size=400):
    if corners is None or len(corners) != 4:
        print("[warp_chessboard] corners 오류, 원본 반환")
        return frame.copy()
    
    corners = np.array(corners, dtype=np.float32)
    print(f"[warp_chessboard] corners: {corners}")  # ✅ 좌표 확인용

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
    cap = cv2.VideoCapture(0)  # 또는 스트리밍 주소

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        disp = frame.copy()
        corners = find_green_corners(disp)

        if corners is not None:
            warp = warp_chessboard(frame, corners)
        else:
            warp = np.zeros((400, 400, 3), dtype=np.uint8)  # ✅ Warped 창 기본 제공

        cv2.imshow("Warped", warp)
        cv2.imshow("Frame", disp)
        cv2.setMouseCallback("Frame", mouse_callback, {"frame": frame})

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
