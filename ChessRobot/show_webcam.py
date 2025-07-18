import cv2

# 기본 카메라(0번) 사용
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print('웹캠을 열 수 없습니다.')
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print('프레임을 읽을 수 없습니다.')
        break
    cv2.imshow('Webcam', frame)
    # q 키를 누르면 종료
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows() 