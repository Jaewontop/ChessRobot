from flask import Flask, Response, render_template_string
import cv2
from video_streams import gen_warped_frames, gen_original_frames, gen_edges_frames

app = Flask(__name__)
cap = cv2.VideoCapture(0)

hsv_values_global = []

def gen_original_frames_with_hsv():
    global hsv_values_global
    for frame_bytes, hsv_values in gen_original_frames(cap):
        hsv_values_global = hsv_values
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/warp')
def warp_feed():
    return Response(gen_warped_frames(cap), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/original')
def original_feed():
    return Response(gen_original_frames_with_hsv(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/edges')
def edges_feed():
    return Response(gen_edges_frames(cap), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    global hsv_values_global
    hsv_html = '<br>'.join([f'HSV {i+1}: {v}' for i, v in enumerate(hsv_values_global)]) if hsv_values_global else 'HSV 정보 없음'
    return render_template_string('''
    <h1>체스판 스트리밍</h1>
    <div style="display: flex; gap: 20px;">
      <div>
        <h3 style="margin:0; font-size:16px;">원본</h3>
        <img src="/original" width="320" height="240" style="border:1px solid #aaa;">
      </div>
      <div>
        <h3 style="margin:0; font-size:16px;">와핑</h3>
        <img src="/warp" width="320" height="240" style="border:1px solid #aaa;">
      </div>
      <div>
        <h3 style="margin:0; font-size:16px;">경계(에지)</h3>
        <img src="/edges" width="320" height="240" style="border:1px solid #aaa;">
      </div>
    </div>
    <div style="margin-top:20px; font-size:16px; color:#222;">
      <b>초록색 마커 HSV값</b><br>
      {{ hsv_html|safe }}
    </div>
    ''', hsv_html=hsv_html)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False) 