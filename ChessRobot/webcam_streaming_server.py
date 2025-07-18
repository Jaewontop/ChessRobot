from flask import Flask, Response
import cv2

app = Flask(__name__)

# 카메라 객체 생성
cap = cv2.VideoCapture(0)

def gen_frames():
    while True:
        success, frame = cap.read()
        if not success:
            break
        else:
            # JPEG로 인코딩
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            # multipart/x-mixed-replace로 스트리밍
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return '<h1>웹캠 스트리밍</h1><img src="/video_feed">'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False) 