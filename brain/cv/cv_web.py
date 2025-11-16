"""간단한 CV 웹 UI.

terminal_chess 등에서 import하여 `start_cv_web_server`를 호출하면
브라우저 기반 4점 지정/기준 저장/턴 전환을 사용할 수 있다.

단독 실행도 가능하다::

    python -m brain.cv_web
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, Iterable, Tuple
import pickle

import cv2
import numpy as np
from flask import Flask, Response, render_template_string, request, jsonify

from cv import cv_manager

BASE_DIR = Path(__file__).resolve().parent


class USBCapture:
    """USB 카메라를 위한 간단 래퍼 (cv2.VideoCapture 기반).

    rotate_180=True 이면 영상이 뒤집혀 있을 때 180도 회전 보정.
    기본값은 False (카메라가 이미 올바른 방향이라는 가정).
    """

    def __init__(self, index: int = 0, size=(1280, 720), fps: int = 30, rotate_180: bool = False):
        # GStreamer 대신 V4L2 백엔드를 명시적으로 사용해 본다.
        self._cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        self._rotate_180 = rotate_180
        if not self._cap.isOpened():
            print(f"[USBCapture] /dev/video{index} 를 열 수 없습니다.")
        try:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
            self._cap.set(cv2.CAP_PROP_FPS, fps)
        except Exception as e:
            print(f"[USBCapture] 카메라 속성 설정 실패: {e}")

    def read(self):
        ret, frame = self._cap.read()
        if not ret or frame is None:
            print("[USBCapture] frame read 실패")
            return ret, frame

        # 카메라가 180도 뒤집혀 있을 때 보정
        if self._rotate_180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)

        return True, frame

    def release(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass


class ThreadSafeCapture:
    """멀티스레드 환경에서 안전하게 read()를 보장하는 래퍼."""

    def __init__(self, cap):
        self._cap = cap
        self._lock = threading.Lock()

    def read(self):
        with self._lock:
            return self._cap.read()

    def release(self):
        with self._lock:
            if hasattr(self._cap, "release"):
                self._cap.release()


def _encode_jpeg(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", img)
    if not ok:
        raise RuntimeError("JPEG 인코딩 실패")
    return buf.tobytes()


def _default_board() -> list:
    return [
        ['BR', 'BN', 'BB', 'BQ', 'BK', 'BB', 'BN', 'BR'],
        ['BP', 'BP', 'BP', 'BP', 'BP', 'BP', 'BP', 'BP'],
        ['', '', '', '', '', '', '', ''],
        ['', '', '', '', '', '', '', ''],
        ['', '', '', '', '', '', '', ''],
        ['', '', '', '', '', '', '', ''],
        ['WP', 'WP', 'WP', 'WP', 'WP', 'WP', 'WP', 'WP'],
        ['WR', 'WN', 'WB', 'WQ', 'WK', 'WB', 'WN', 'WR'],
    ]


def build_app(state: Dict[str, Any]) -> Flask:
    app = Flask(__name__)

    cap: ThreadSafeCapture = state["cap"]
    np_path: Path = state["np_path"]
    pkl_path: Path = state["pkl_path"]

    def capture_frame() -> Optional[np.ndarray]:
        """항상 가능한 한 최신 프레임을 반환하도록 버퍼를 조금 비운 뒤 마지막 프레임을 사용."""
        last_frame: Optional[np.ndarray] = None
        # 짧은 시간 동안 여러 번 read() 해서 버퍼에 쌓인 이전 프레임은 버리고 마지막 것만 사용
        for _ in range(4):
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            last_frame = frame
        if last_frame is None:
            print("[cv_web] capture_frame: 유효한 프레임을 읽지 못했습니다")
            return None
        return last_frame

    @app.route("/")
    def index():
        move_str = " -> ".join(state["move_history"])
        return render_template_string('''
        <h1>체스판 CV 도우미</h1>
        <div id="turn-info" style="margin-bottom:10px; font-size:18px;">
          <b>현재 턴:</b> {{turn_color}}<br>
          <b>이전 턴:</b> {{prev_turn_color if prev_turn_color else '없음'}}
        </div>
        <button onclick="setInitialBoard()">완전 초기상태 저장</button>
        <button onclick="nextTurn()">턴 기록 및 전환</button>
        <div style="margin:10px 0;">
          <a href="/manual" target="_blank">[수동 4점 설정 페이지 열기]</a>
        </div>
        <div id="status" style="margin:12px 0; color:#006400;"></div>
        <div style="margin-top:20px; font-size:16px; color:#222;">
          <b>기물 이동 내역:</b><br>
          {{ move_str }}
        </div>
        <script>
        function setStatus(msg, ok=true){
          const s = document.getElementById('status');
          s.style.color = ok ? '#006400' : '#8B0000';
          s.textContent = msg;
        }
        function setInitialBoard(){
          fetch('/set_init_board', {method:'POST'})
            .then(r => r.text())
            .then(msg => setStatus(msg, true))
            .catch(e => setStatus('오류: '+e, false));
        }
        function nextTurn(){
          fetch('/next_turn', {method:'POST'})
            .then(r => r.text())
            .then(msg => {
              setStatus(msg, true);
              window.location.reload();
            })
            .catch(e => setStatus('오류: '+e, false));
        }
        </script>
        ''', turn_color=state["turn_color"], prev_turn_color=state["prev_turn_color"], move_str=move_str)

    @app.route("/snapshot_original")
    def snapshot_original():
        frame = capture_frame()
        if frame is None:
            return "카메라 프레임 없음", 500
        return Response(_encode_jpeg(frame), mimetype="image/jpeg")

    @app.route("/set_init_board", methods=["POST"])
    def set_init_board():
        frame = capture_frame()
        if frame is None:
            return "프레임을 읽을 수 없습니다.", 500
        board_vals = cv_manager.save_initial_board_from_frame(frame, str(np_path))
        state["init_board_values"] = board_vals
        return "초기상태 저장 완료", 200

    @app.route("/next_turn", methods=["POST"])
    def next_turn():
        try:
            result = cv_manager.process_turn_transition(
                state["cap"],
                str(np_path),
                str(pkl_path),
                state["chess_pieces"],
                state["turn_color"],
            )
        except Exception as e:
            return f"턴 전환 실패: {e}", 500

        state["turn_color"] = result["turn_color"]
        state["prev_turn_color"] = result["prev_turn_color"]
        state["init_board_values"] = result["init_board_values"]
        state["chess_pieces"] = result["chess_pieces"]
        state["move_history"].append(result["move_str"])

        return f"턴 전환 완료: {result['move_str']}", 200

    @app.route("/set_corners", methods=["POST"])
    def set_corners():
        try:
            data = request.get_json(force=True)
            pts = data.get("points")
            if not pts or len(pts) != 4:
                return jsonify({"ok": False, "error": "points must be length 4"}), 400
            cv_manager.set_manual_corners(pts)
            return jsonify({"ok": True, "manual_mode": True}), 200
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/clear_corners", methods=["POST"])
    def clear_corners():
        cv_manager.clear_manual_corners()
        return jsonify({"ok": True, "manual_mode": False}), 200

    @app.route("/get_corners")
    def get_corners():
        corners = cv_manager.get_manual_corners()
        return jsonify({
            "manual_mode": cv_manager.manual_mode_enabled(),
            "points": corners.tolist() if corners is not None else None
        })

    @app.route("/manual")
    def manual():
        return render_template_string('''
        <html>
        <head>
          <meta charset="utf-8" />
          <title>수동 코너 설정</title>
          <style>
            body { font-family: sans-serif; }
            #wrap { display: flex; gap: 20px; }
            #left { flex: 0 0 auto; }
            #right { flex: 1 1 auto; }
            canvas { border: 1px solid #aaa; cursor: crosshair; }
            .btn { padding: 6px 10px; margin-right: 6px; }
            .pt { width: 70px; display: inline-block; }
          </style>
        </head>
        <body>
          <h2>수동 4점 설정 (이미지를 클릭하여 TL,TR,BR,BL 순으로 선택하세요)</h2>
          <div id="wrap">
            <div id="left">
              <div style="margin-bottom:8px;">
                <button class="btn" onclick="loadSnapshot()">스냅샷 새로고침</button>
                <button class="btn" onclick="clearPoints()">포인트 초기화</button>
                <button class="btn" onclick="sendPoints()">저장(/set_corners)</button>
                <button class="btn" onclick="clearServer()">서버 해제(/clear_corners)</button>
              </div>
              <div>
                <img id="img" src="/snapshot_original?ts=" style="display:none;" onload="drawImage()" />
                <canvas id="canvas" width="400" height="400"></canvas>
              </div>
            </div>
            <div id="right">
              <div><b>선택된 포인트</b> (이미지 좌표):</div>
              <div id="pts"></div>
              <div id="status" style="margin-top:10px;color:#006400;"></div>
            </div>
          </div>
          <script>
          const img = document.getElementById('img');
          const canvas = document.getElementById('canvas');
          const ctx = canvas.getContext('2d');
          let points = [];

          function loadSnapshot() {
            document.getElementById('img').src = '/snapshot_original?ts=' + Date.now();
          }

          function drawImage() {
            const w = img.naturalWidth || img.width;
            const h = img.naturalHeight || img.height;
            canvas.width = w; canvas.height = h;
            ctx.clearRect(0,0,w,h);
            ctx.drawImage(img, 0, 0, w, h);
            drawOverlay();
          }

          function drawOverlay() {
            for (let i=0;i<points.length;i++){
              const p = points[i];
              ctx.beginPath();
              ctx.arc(p.x, p.y, 6, 0, Math.PI*2);
              ctx.fillStyle = '#00ff00';
              ctx.fill();
              ctx.strokeStyle = '#003300';
              ctx.stroke();
              ctx.fillStyle = '#ffffff';
              ctx.font = '14px sans-serif';
              ctx.fillText((i+1).toString(), p.x+8, p.y-8);
            }
            if (points.length === 4) {
              ctx.beginPath();
              ctx.moveTo(points[0].x, points[0].y);
              ctx.lineTo(points[1].x, points[1].y);
              ctx.lineTo(points[2].x, points[2].y);
              ctx.lineTo(points[3].x, points[3].y);
              ctx.closePath();
              ctx.strokeStyle = '#ffff00';
              ctx.lineWidth = 2;
              ctx.stroke();
            }
            updatePtsPanel();
          }

          function canvasPos(evt){
            const rect = canvas.getBoundingClientRect();
            const x = evt.clientX - rect.left;
            const y = evt.clientY - rect.top;
            return {x,y};
          }

          canvas.addEventListener('click', (evt) => {
            if (points.length >= 4) return;
            const p = canvasPos(evt);
            points.push(p);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            drawOverlay();
          });

          function clearPoints(){
            points = [];
            drawImage();
            setStatus('포인트 초기화 완료');
          }

          function updatePtsPanel(){
            const div = document.getElementById('pts');
            let html = '';
            for (let i=0;i<points.length;i++){
              const p = points[i];
              html += `<div>#${i+1} <span class="pt">x:${Math.round(p.x)}</span> <span class="pt">y:${Math.round(p.y)}</span></div>`;
            }
            div.innerHTML = html;
          }

          function setStatus(msg, ok=true){
            const s = document.getElementById('status');
            s.style.color = ok ? '#006400' : '#8B0000';
            s.textContent = msg;
          }

          async function sendPoints(){
            if (points.length !== 4){ setStatus('포인트 4개를 선택하세요', false); return; }
            const pts = points.map(p => [Math.round(p.x), Math.round(p.y)]);
            try{
              const res = await fetch('/set_corners', {
                method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({points: pts})
              });
              const j = await res.json();
              if (j.ok){ setStatus('저장 성공. 수동 와핑 사용 중'); }
              else { setStatus('저장 실패: '+(j.error||res.status), false); }
            }catch(e){ setStatus('요청 실패: '+e, false); }
          }

          async function clearServer(){
            try{
              const res = await fetch('/clear_corners', {method:'POST'});
              const j = await res.json();
              if (j.ok){ setStatus('서버 수동 모드 해제'); }
              else { setStatus('해제 실패', false); }
            }catch(e){ setStatus('요청 실패: '+e, false); }
          }

          loadSnapshot();
          </script>
        </body>
        </html>
        ''')

    return app


def start_cv_web_server(
        np_path: Optional[str] = None,
        pkl_path: Optional[str] = None,
        *,
        host: str = "0.0.0.0",
        port: int = 5001,
        use_thread: bool = True,
        cap = None
) -> threading.Thread | None:
    """Flask CV 웹 서버를 시작한다. use_thread=True이면 데몬 스레드로 실행."""
    if np_path is None:
        np_path = str(BASE_DIR / "init_board_values.npy")
    if pkl_path is None:
        pkl_path = str(BASE_DIR / "chess_pieces.pkl")

    if cap is None:
        cap = USBCapture()
    safe_cap = ThreadSafeCapture(cap)

    init_board_values = np.load(np_path) if os.path.exists(np_path) else None
    if os.path.exists(pkl_path):
        try:
            with open(pkl_path, "rb") as f:
                chess_pieces = pickle.load(f)
        except Exception:
            chess_pieces = _default_board()
    else:
        chess_pieces = _default_board()

    state = {
        "cap": safe_cap,
        "np_path": Path(np_path),
        "pkl_path": Path(pkl_path),
        "init_board_values": init_board_values,
        "chess_pieces": chess_pieces,
        "turn_color": "white",
        "prev_turn_color": "white",
        "move_history": [],
    }

    app = build_app(state)

    def run_app():
        try:
            app.run(host=host, port=port, debug=False, use_reloader=False)
        finally:
            safe_cap.release()

    if use_thread:
        t = threading.Thread(target=run_app, daemon=True)
        t.start()
        print(f"[cv_web] Flask 서버를 백그라운드로 시작했습니다: http://{host}:{port}")
        return t
    else:
        print(f"[cv_web] Flask 서버 실행: http://{host}:{port}")
        try:
            run_app()
        finally:
            safe_cap.release()
        return None


if __name__ == "__main__":
    start_cv_web_server(use_thread=False)

