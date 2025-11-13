"""체스판 CV 제어 유틸.

수동 4점 지정, 초기 기준 저장, 턴 전환 로직을 함수 형태로 제공한다.
`terminal_chess.py` 등 다른 모듈에서 import 하여 직접 사용할 수 있다.
"""

from __future__ import annotations

import os
import time
import pickle
from typing import Iterable, List, Optional, Tuple, Callable, Dict, Any

import cv2
import numpy as np

from warp_cam_picam2_stable_v2 import warp_chessboard
from piece_auto_update import update_chess_pieces

try:
    from piece_recognition import _pair_moves as default_pair_moves_fn
except ImportError:
    default_pair_moves_fn = None  # type: ignore


_manual_corners: Optional[np.ndarray] = None  # TL, TR, BR, BL


# ---------------------------------------------------------------------------
# 수동 코너 지정
# ---------------------------------------------------------------------------
def _order_corners_tl_tr_br_bl(pts: Iterable[Iterable[float]]) -> np.ndarray:
    pts = np.array(list(pts), dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    ordered = np.array([tl, tr, br, bl], dtype=np.float32)
    return ordered


def set_manual_corners(points: Iterable[Iterable[float]]) -> None:
    """수동 코너(TL,TR,BR,BL 순)가 지정되면 이후 와핑 시 사용."""
    global _manual_corners
    ordered = _order_corners_tl_tr_br_bl(points)
    _manual_corners = ordered
    print(f"[cv_manager] manual corners set: {ordered.tolist()}")


def clear_manual_corners() -> None:
    """수동 코너를 해제."""
    global _manual_corners
    _manual_corners = None
    print("[cv_manager] manual corners cleared")


def get_manual_corners(copy: bool = True) -> Optional[np.ndarray]:
    if _manual_corners is None:
        return None
    return _manual_corners.copy() if copy else _manual_corners


def manual_mode_enabled() -> bool:
    return _manual_corners is not None


# ---------------------------------------------------------------------------
# 와핑 & 보드 평균 계산
# ---------------------------------------------------------------------------
def warp_with_manual_corners(frame: np.ndarray, size: int = 400) -> np.ndarray:
    """수동 코너가 있으면 와핑, 없으면 리사이즈."""
    corners = get_manual_corners(copy=False)
    if corners is not None and corners.shape == (4, 2):
        try:
            return warp_chessboard(frame, corners, size=size)
        except Exception as e:
            print(f"[cv_manager] warp failed, fallback resize: {e}")
    try:
        return cv2.resize(frame, (size, size))
    except Exception:
        return frame


def _mean_lab_board_from_warp(warp: np.ndarray) -> np.ndarray:
    h, w = warp.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    lab = cv2.cvtColor(warp, cv2.COLOR_BGR2LAB)
    out = np.zeros((8, 8, 3), np.float32)
    for i in range(8):
        for j in range(8):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            cell = lab[y1:y2, x1:x2]
            out[i, j] = cell.reshape(-1, 3).mean(axis=0)
    return out


def capture_avg_lab_board(cap,
                          n_frames: int = 8,
                          sleep_sec: float = 0.02,
                          warp_size: int = 400
                          ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """다중 프레임을 캡처해 LAB 평균과 마지막 와프 이미지를 반환."""
    acc = np.zeros((8, 8, 3), np.float32)
    cnt = 0
    last_warp = None

    for _ in range(n_frames):
        ret, frame = cap.read()
        if not ret:
            break

        warp = warp_with_manual_corners(frame, size=warp_size)
        last_warp = warp
        acc += _mean_lab_board_from_warp(warp)
        cnt += 1
        time.sleep(sleep_sec)

    if cnt == 0:
        return None, None
    return acc / cnt, last_warp


def compute_board_means_bgr(warp: np.ndarray) -> np.ndarray:
    h, w = warp.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    board_vals = np.zeros((8, 8, 3), np.float32)
    for i in range(8):
        for j in range(8):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            cell = warp[y1:y2, x1:x2]
            board_vals[i, j] = np.mean(cell.reshape(-1, 3), axis=0)
    return board_vals


# ---------------------------------------------------------------------------
# 초기 기준 저장
# ---------------------------------------------------------------------------
def save_initial_board_from_frame(frame: np.ndarray, np_path: str, warp_size: int = 400) -> np.ndarray:
    """프레임을 와핑하여 초기 기준을 저장하고 값을 반환."""
    warp = warp_with_manual_corners(frame, size=warp_size)
    board_vals = compute_board_means_bgr(warp)
    np.save(np_path, board_vals)
    print(f"[cv_manager] initial board saved to {np_path}")
    return board_vals


def save_initial_board_from_capture(cap, np_path: str,
                                    warp_size: int = 400) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """카메라에서 한 프레임을 캡처하여 초기 기준을 저장."""
    ret, frame = cap.read()
    if not ret:
        print("[cv_manager] failed to read frame for initial board")
        return None, None
    board_vals = save_initial_board_from_frame(frame, np_path, warp_size=warp_size)
    warp = warp_with_manual_corners(frame, size=warp_size)
    return board_vals, warp


# ---------------------------------------------------------------------------
# 좌표/표기 유틸
# ---------------------------------------------------------------------------
def coord_to_chess_notation(i: int, j: int) -> str:
    file = chr(ord('a') + j)
    rank = str(8 - i)
    return file + rank


def piece_to_fen(piece: str) -> str:
    if not piece or len(piece) < 2:
        return ''
    color, kind = piece[0], piece[1]
    kind_map = {'K': 'K', 'Q': 'Q', 'R': 'R', 'B': 'B', 'N': 'N', 'P': 'P'}
    fen = kind_map.get(kind.upper(), '?')
    if color == 'W':
        return fen.upper()
    if color == 'B':
        return fen.lower()
    return '?'


def _bgr_to_lab_grid(board_vals: np.ndarray) -> np.ndarray:
    prev_lab = np.zeros((8, 8, 3), np.float32)
    for i in range(8):
        for j in range(8):
            bgr = np.array(board_vals[i, j], dtype=np.uint8)[None, None, :]
            lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
            prev_lab[i, j] = lab[0, 0]
    return prev_lab


# ---------------------------------------------------------------------------
# 턴 전환 처리
# ---------------------------------------------------------------------------
def process_turn_transition(
        cap,
        np_path: str,
        pkl_path: str,
        chess_pieces: List[List[str]],
        turn_color: str,
        *,
        pair_moves_fn: Optional[Callable[[np.ndarray, np.ndarray, float], List[Tuple[int, int]]]] = None,
        threshold: float = 9.0,
        n_frames: int = 8,
        sleep_sec: float = 0.02,
        warp_size: int = 400
) -> Dict[str, Any]:
    """
    턴 전환 로직을 실행한다.
    반환값에는 다음 키가 포함된다.
    - turn_color, prev_turn_color
    - init_board_values (새 기준)
    - chess_pieces (업데이트된 배열)
    - move_str (기보 문자열)
    - src, dst (행/열 좌표)
    - warp (마지막 와프 이미지)
    """
    if pair_moves_fn is None:
        if default_pair_moves_fn is None:
            raise RuntimeError("pair_moves_fn not provided and default could not be imported")
        pair_moves_fn = default_pair_moves_fn

    prev_turn_color = turn_color
    new_turn_color = 'black' if turn_color == 'white' else 'white'

    # 현재 배열을 안전하게 저장
    try:
        with open(pkl_path, 'wb') as f:
            pickle.dump(chess_pieces, f)
    except Exception as e:
        print(f"[cv_manager] warning: failed to pre-save chess pieces: {e}")

    prev_board_values = np.load(np_path) if os.path.exists(np_path) else None

    curr_lab, warp = capture_avg_lab_board(cap, n_frames=n_frames, sleep_sec=sleep_sec, warp_size=warp_size)
    if curr_lab is None or warp is None:
        raise RuntimeError("현재 보드를 캡처할 수 없습니다.")

    prev_lab = _bgr_to_lab_grid(prev_board_values) if prev_board_values is not None else curr_lab.copy()

    deltas = curr_lab - prev_lab
    mean_shift = deltas.reshape(-1, 3).mean(axis=0, dtype=np.float32)
    deltas = deltas - mean_shift
    norms = np.linalg.norm(deltas, axis=2).astype(np.float32)

    pairs = pair_moves_fn(deltas.reshape(-1, 3), norms.reshape(-1), threshold=threshold)
    if pairs:
        a, b = pairs[0]
        src = (a // 8, a % 8)
        dst = (b // 8, b % 8)
        print(f"[cv_manager] pair matched src={src}, dst={dst}")
    else:
        flat = norms.flatten()
        order = np.argsort(-flat)
        src = (int(order[0]) // 8, int(order[0]) % 8)
        dst = (int(order[1]) // 8, int(order[1]) % 8)
        print(f"[cv_manager] pair not found -> fallback {src}->{dst}")

    board_vals = compute_board_means_bgr(warp)

    try:
        with open(pkl_path, 'rb') as f:
            chess_pieces = pickle.load(f)
    except Exception:
        pass

    before = [row[:] for row in chess_pieces]
    chess_pieces = update_chess_pieces(chess_pieces, src, dst)

    piece_src = before[src[0]][src[1]]
    piece_dst = before[dst[0]][dst[1]]
    if piece_src and not piece_dst:
        move_str = f"{piece_to_fen(piece_src)} {coord_to_chess_notation(src[0], src[1])}-{coord_to_chess_notation(dst[0], dst[1])}"
    elif piece_dst and not piece_src:
        move_str = f"{piece_to_fen(piece_dst)} {coord_to_chess_notation(dst[0], dst[1])}-{coord_to_chess_notation(src[0], src[1])}"
    else:
        move_str = f"? {coord_to_chess_notation(src[0], src[1])}<->{coord_to_chess_notation(dst[0], dst[1])}"
    print(f"[cv_manager] move detected: {move_str}")

    try:
        with open(pkl_path, 'wb') as f:
            pickle.dump(chess_pieces, f)
    except Exception as e:
        print(f"[cv_manager] warning: failed to save chess pieces: {e}")

    if os.path.exists(np_path):
        try:
            os.remove(np_path)
            print(f"[cv_manager] removed old board values: {np_path}")
        except Exception as e:
            print(f"[cv_manager] failed to remove old board file: {e}")

    np.save(np_path, board_vals)
    try:
        updated_board_vals = np.load(np_path)
    except Exception as e:
        print(f"[cv_manager] warning: failed to reload board values: {e}")
        updated_board_vals = board_vals

    return {
        'turn_color': new_turn_color,
        'prev_turn_color': prev_turn_color,
        'init_board_values': updated_board_vals,
        'chess_pieces': chess_pieces,
        'move_str': move_str,
        'src': src,
        'dst': dst,
        'warp': warp,
    }


__all__ = [
    'set_manual_corners',
    'clear_manual_corners',
    'get_manual_corners',
    'manual_mode_enabled',
    'warp_with_manual_corners',
    'capture_avg_lab_board',
    'compute_board_means_bgr',
    'save_initial_board_from_frame',
    'save_initial_board_from_capture',
    'process_turn_transition',
    'coord_to_chess_notation',
    'piece_to_fen',
]
