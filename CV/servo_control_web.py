from flask import Flask, render_template_string, request, jsonify
import serial
import time

# 아두이노와 연결된 시리얼 포트와 속도 지정 (포트명은 환경에 맞게 수정)
SERIAL_PORT = '/dev/serial0'  # 또는 '/dev/ttyACM0' 등
BAUD_RATE = 9600

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # 시리얼 초기화 대기
except Exception as e:
    ser = None
    print(f"시리얼 연결 실패: {e}")

app = Flask(__name__)

HTML = '''
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>서보모터 제어</title>
    <style>
        body { font-family: sans-serif; }
        .servo-group { margin-bottom: 20px; }
        button { width: 60px; height: 40px; font-size: 18px; margin: 0 5px; }
    </style>
</head>
<body>
    <h1>서보모터 제어 패널</h1>
    {% for i in range(6) %}
    <div class="servo-group">
        <span>서보 {{i+1}} <span id="angle{{i}}">(알 수 없음)</span></span>
        <button onclick="move({{i}}, 'up')">▲</button>
        <button onclick="move({{i}}, 'down')">▼</button>
    </div>
    {% endfor %}
    <button onclick="resetAll()">초기화(90도)</button>
    <div id="status"></div>
    <script>
    function move(idx, dir) {
        fetch('/move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({servo: idx, direction: dir})
        })
        .then(res => res.json())
        .then(data => {
            document.getElementById('status').innerText = data.msg;
            if (data.angle !== undefined) {
                document.getElementById('angle'+idx).innerText = '('+data.angle+'도)';
            }
        });
    }
    function resetAll() {
        fetch('/reset', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            document.getElementById('status').innerText = data.msg;
            for (let i = 0; i < 6; i++) {
                document.getElementById('angle'+i).innerText = '(90도)';
            }
        });
    }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/move', methods=['POST'])
def move():
    data = request.get_json()
    servo = int(data['servo'])
    direction = data['direction']
    if ser is None:
        return jsonify({'msg': '시리얼 연결 실패'}), 500
    # 아두이노로 명령 전송 (예: "S0U\n" = 0번 서보 업, "S0D\n" = 0번 서보 다운)
    cmd = f'S{servo}{"U" if direction=="up" else "D"}\n'
    ser.write(cmd.encode())
    time.sleep(0.05)  # 아두이노 응답 대기
    angle = None
    if ser.in_waiting:
        try:
            resp = ser.readline().decode(errors='ignore').strip()
            # 응답 예시: S0:100
            if resp.startswith(f'S{servo}:'):
                angle = int(resp.split(':')[1])
        except:
            pass
    return jsonify({'msg': f'서보 {servo+1} {"▲" if direction=="up" else "▼"} 명령 전송', 'angle': angle})

@app.route('/reset', methods=['POST'])
def reset():
    if ser is None:
        return jsonify({'msg': '시리얼 연결 실패'}), 500
    for i in range(6):
        cmd = f'S{i}R\n'  # 아두이노에서 'R' 명령을 90도로 리셋하도록 구현 필요
        ser.write(cmd.encode())
        time.sleep(0.05)
    return jsonify({'msg': '모든 서보를 90도로 초기화'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False) 