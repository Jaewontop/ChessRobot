import cv2
import numpy as np

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

def main():
    img = cv2.imread('ChessRobot/test.jpeg')
    if img is None:
        print('이미지를 불러올 수 없습니다.')
        return
    corners = find_chessboard_corners(img)
    if corners is not None:
        warp = warp_chessboard(img, corners)
        cv2.imwrite('ChessRobot/warped_chessboard.jpg', warp)
        print('와핑된 이미지를 ChessRobot/warped_chessboard.jpg로 저장했습니다.')
    else:
        print('체스판의 네 코너를 찾지 못했습니다.')

if __name__ == '__main__':
    main() 