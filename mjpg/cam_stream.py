from flask import Flask, render_template, Response
from picamera2 import Picamera2
import cv2

app = Flask(__name__)
camera = Picamera2()
camera.configure(camera.create_video_configuration(main={"size": (640, 480)}))
camera.start()

def gen_frames():
    while True:
        frame = camera.capture_array()
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return '<h2>📷 Pi Camera Streaming</h2><img src="/video_feed">'

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

