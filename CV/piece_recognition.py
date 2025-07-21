import numpy as np
import cv2
from warping_utils import find_green_corners, warp_chessboard
import os

def gen_edges_frames(cap, base_board_path='init_board_values.npy', threshold=10):
    import os
    from main import reload_base_board, prev_board_values
    prev_warp = None
    prev_diff_vals = None
    prev_diff_mask = None
    base_board_values = None
    while True:
        # 신호가 있을 때만 npy 파일을 다시 load
        if reload_base_board or base_board_values is None:
            if not os.path.exists(base_board_path):
                print('기본값 파일 없음')
                break
            base_board_values = np.load(base_board_path)
            # 기준값이 바뀌면 prev_*도 초기화
            prev_warp = None
            prev_diff_vals = None
            prev_diff_mask = None
            from main import reload_base_board as _reload
            if _reload:
                import builtins
                builtins.reload_base_board = False
        ret, frame = cap.read()
        if not ret:
            break
        corners = find_green_corners(frame)
        if corners is None:
            corners = find_green_corners(frame)
        if corners is not None:
            warp = warp_chessboard(frame, corners, size=400)
        else:
            warp = frame.copy()
        h, w = warp.shape[:2]
        cell_size_h = h // 8
        cell_size_w = w // 8
        diff_vals = np.zeros((8,8), dtype=np.float32)
        mean_bgrs = np.zeros((8,8,3), dtype=np.uint8)
        diff_list = []
        for i in range(8):
            for j in range(8):
                y1, y2 = i*cell_size_h, (i+1)*cell_size_h
                x1, x2 = j*cell_size_w, (j+1)*cell_size_w
                cell = warp[y1:y2, x1:x2]
                mean_bgr = np.mean(cell.reshape(-1, 3), axis=0)
                mean_bgrs[i, j] = mean_bgr
                diff = np.linalg.norm(mean_bgr - base_board_values[i, j])
                diff_vals[i, j] = diff
                diff_list.append((diff, i, j))
        warp_to_draw = warp.copy()
        # 텍스트 표시
        for i in range(8):
            for j in range(8):
                y1, y2 = i*cell_size_h, (i+1)*cell_size_h
                x1, x2 = j*cell_size_w, (j+1)*cell_size_w
                text = f"{int(diff_vals[i, j])}"
                text_x = x1 + 2
                text_y = y1 + cell_size_h//2
                cv2.putText(warp_to_draw, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1, cv2.LINE_AA)
        # diff가 가장 큰 두 칸에 무조건 빨간 박스
        if len(diff_list) >= 2:
            diff_list.sort(reverse=True)
            seen = set()
            shown = 0
            for diff, i, j in diff_list:
                if (i, j) not in seen:
                    y1, y2 = i*cell_size_h, (i+1)*cell_size_h
                    x1, x2 = j*cell_size_w, (j+1)*cell_size_w
                    cv2.rectangle(warp_to_draw, (x1, y1), (x2, y2), (0,0,255), 2)
                    seen.add((i, j))
                    shown += 1
                    if shown == 2:
                        break
        _, buffer = cv2.imencode('.jpg', warp_to_draw)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n') 