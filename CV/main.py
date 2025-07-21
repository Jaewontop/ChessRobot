from flask import Flask, Response, render_template_string
import cv2
# from piece_recognition import get_processed_images, find_green_corners, find_chessboard_corners, warp_chessboard
from piece_recognition import get_processed_images
from warping_utils import find_green_corners, find_chessboard_corners, warp_chessboard
import numpy as np
import threading
import time

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

latest_frame = None

def frame_reader():
    global latest_frame
    while True:
        ret, frame = cap.read()
        if ret:
            latest_frame = frame

# 서버 시작 전에 스레드로 실행
threading.Thread(target=frame_reader, daemon=True).start()

app = Flask(__name__)

# 실시간 스트리밍 제너레이터들

hsv_values_global = None

def gen_original_frames(cap):
    while True:
        if latest_frame is not None:
            _, buffer = cv2.imencode('.jpg', latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            frame_bytes = buffer.tobytes()
            yield (frame_bytes, None)
        time.sleep(0.01)

def gen_original_frames_with_hsv():
    global hsv_values_global
    for frame_bytes, hsv_values in gen_original_frames(cap):
        hsv_values_global = hsv_values
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

def gen_warp_frames():
    while True:
        if latest_frame is not None:
            frame = latest_frame.copy()
            corners = find_green_corners(frame)
            if corners is None:
                corners = find_chessboard_corners(frame)
            if corners is not None:
                warp = warp_chessboard(frame, corners, size=400)
            else:
                warp = frame.copy()
            _, buffer = cv2.imencode('.jpg', warp, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.005)

def gen_piece_frames():
    while True:
        if latest_frame is not None:
            frame = latest_frame.copy()
            piece_img = get_processed_images(frame)  # 넘파이 배열 반환
            _, buffer = cv2.imencode('.jpg', piece_img, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            img_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')
        time.sleep(0.01)

@app.route('/original')
def original_feed():
    return Response(gen_original_frames_with_hsv(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/warp')
def warp_feed():
    return Response(gen_warp_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/piece')
def piece_feed():
    return Response(gen_piece_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return render_template_string('''
    <h1>체스판 실시간 분석</h1>
    <div style="display: flex; gap: 20px;">
      <div>
        <h3 style="margin:0; font-size:16px;">웹캠 원본</h3>
        <img src="/original" width="320" height="320" style="border:1px solid #aaa;">
      </div>
      <div>
        <h3 style="margin:0; font-size:16px;">와핑 결과</h3>
        <img src="/warp" width="320" height="320" style="border:1px solid #aaa;">
      </div>
      <div>
        <h3 style="margin:0; font-size:16px;">기물 인식</h3>
        <img src="/piece" width="320" height="320" style="border:1px solid #aaa;">
      </div>
    </div>
    ''')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False) 