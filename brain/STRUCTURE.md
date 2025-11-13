# Brain 모듈 구조 문서

## 📁 전체 구조 개요

```
brain/
├── terminal_chess.py        # 메인 게임 루프 (통합 실행)
├── engine_manager.py        # Stockfish 체스 엔진 관리
├── timer_manager.py         # 아두이노 타이머 관리
├── move_analyzer.py         # 체스 움직임 분석
├── robot_arm_controller.py  # 로봇팔 제어
└── piece_detector.py        # 컴퓨터 비전 기물 감지
```

---

## 🔗 모듈 간 의존성 관계

```
┌─────────────────────────────────────────────────────────┐
│           terminal_chess.py (메인 게임 루프)            │
└─────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│engine_manager│  │timer_manager │  │move_analyzer │
│              │  │              │  │              │
│ Stockfish    │  │ 아두이노     │  │ 움직임 분석  │
│ 엔진 관리    │  │ 타이머 관리  │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────────────────────┐
│robot_arm_    │  │ piece_detector.py            │
│controller    │  │                              │
│              │  │ 컴퓨터 비전 기물 감지        │
│ 로봇팔 제어  │  │ - 초기화                     │
│              │  │ - 변화 감지                  │
│              │  │ - 스트리밍                   │
└──────────────┘  └──────────────────────────────┘
```

---

## 📄 파일별 상세 설명

### 1. `terminal_chess.py` (메인 게임 루프)
**역할**: 전체 체스 게임을 통합하여 실행하는 메인 모듈

**주요 기능**:
- 게임 루프 관리 (플레이어 vs Stockfish)
- 타이머 버튼 입력 처리
- CV 기물 변화 감지 및 로봇팔 실행
- 보드 상태 표시 (터미널)
- 게임 종료 조건 확인

**의존성**:
- `engine_manager.py` - Stockfish 엔진 사용
- `timer_manager.py` - 타이머 관리
- `robot_arm_controller.py` - 로봇팔 제어
- `move_analyzer.py` - 움직임 분석
- `piece_detector.py` - CV 기물 감지

**주요 함수**:
```python
main()                    # 메인 게임 루프
display_board()           # 보드 표시
detect_and_execute_cv_move()  # CV로 기물 변화 감지 및 로봇 실행
get_move_from_user()      # 사용자 입력 받기
make_stockfish_move()     # Stockfish 수 실행
check_time_over()         # 시간 초과 확인
```

---

### 2. `engine_manager.py` (Stockfish 엔진 관리)
**역할**: Stockfish 체스 엔진의 초기화, 평가, 최선수 계산

**주요 기능**:
- Stockfish 엔진 초기화/종료
- 포지션 평가 (승률, 점수, 체크메이트 경로)
- 최선 수 계산 및 실행
- 움직임 타입 분석 (캐슬링, 앙파상, 기물 잡기 등)

**의존성**: 없음 (독립 모듈)

**주요 함수**:
```python
init_engine()                    # 엔진 초기화
shutdown_engine()                # 엔진 종료
evaluate_position(board, depth)  # 포지션 평가
engine_make_best_move(board, depth)  # 최선 수 실행
```

**반환 데이터 예시**:
```python
{
    'cp': 50,                    # 백 관점 점수 (centipawns)
    'mate': None,                # 체크메이트 수 (없으면 None)
    'win_prob_white': 0.53,      # 백 승률 (0.0~1.0)
    'best_move': 'e2e4',         # 최선 수 (UCI)
    'best_move_san': 'e4',       # 최선 수 (SAN)
    'move_type': {               # 움직임 타입 정보
        'is_capture': False,
        'is_castling': False,
        'is_en_passant': False,
        'is_promotion': False,
        'piece_type': 1,         # chess.PAWN
        ...
    }
}
```

---

### 3. `timer_manager.py` (아두이노 타이머 관리)
**역할**: 아두이노 시리얼 통신을 통한 체스 타이머 관리

**주요 기능**:
- 아두이노 시리얼 연결/해제
- 타이머 데이터 읽기 및 파싱
- 버튼 입력 감지 (턴 넘기기 신호)
- 타이머 모니터링 (백그라운드 스레드)
- 시간 초과 검사

**의존성**: 없음 (독립 모듈)

**주요 함수**:
```python
init_chess_timer()           # 타이머 초기화
get_timer_display()          # 타이머 표시 문자열
get_black_timer()            # 검은색 타이머 값
get_white_timer()            # 흰색 타이머 값
check_timer_button()         # 버튼 입력 확인
get_chess_timer_status()     # 타이머 상태 반환
```

**시리얼 통신 형식**:
- 타이머 데이터: `P1:431,P2:600` 또는 `DATA: P1:431,P2:600`
- 버튼 입력: `BUTTON_P1`, `BUTTON_P2`, `BTN:P1`, `BTN:P2` 등
- 명령 전송: `START_TIMER`, `STOP_TIMER`, `RESET_TIMER`

---

### 4. `move_analyzer.py` (체스 움직임 분석)
**역할**: 체스 움직임을 분석하여 상세 정보 제공

**주요 기능**:
- 두 좌표에서 출발지/도착지 자동 판단
- 움직임 유효성 검사
- 움직임 타입 분석 (캐슬링, 앙파상, 기물 잡기 등)
- 가능한 모든 움직임 조회

**의존성**: `chess` 라이브러리

**주요 함수**:
```python
analyze_coordinates(board, coord1, coord2)    # 좌표 분석
analyze_move_with_context(board, coord1, coord2)  # 상세 분석
suggest_move(board, coord1, coord2)           # 움직임 제안
get_all_possible_moves(board)                 # 모든 가능한 움직임
```

**반환 데이터 예시**:
```python
{
    'from_square': 'e2',
    'to_square': 'e4',
    'piece_type': '흰색 폰',
    'move_type': '일반 이동',
    'is_valid': True,
    'reason': '유효한 움직임입니다'
}
```

---

### 5. `robot_arm_controller.py` (로봇팔 제어)
**역할**: 체스 움직임을 로봇팔 명령으로 변환하여 실행

**주요 기능**:
- 로봇팔 시리얼 연결/해제
- 움직임 타입별 명령 생성
- 명령 순차 실행 (응답 대기)
- 로봇팔 상태 관리

**의존성**: 없음 (독립 모듈)

**주요 함수**:
```python
init_robot_arm(enabled, port, baudrate)  # 로봇팔 초기화
connect_robot_arm()                      # 로봇팔 연결
disconnect_robot_arm()                   # 로봇팔 연결 해제
execute_robot_move(move_type, move_uci)  # 움직임 실행
is_robot_moving()                        # 움직임 중인지 확인
get_robot_status()                       # 로봇팔 상태
test_robot_connection()                  # 연결 테스트
```

**명령 형식**:
- 일반 이동: `e2e4`
- 기물 잡기: `e5cap` (잡기) → `d4e5` (이동)
- 캐슬링: `e1g1` (킹) → `h1f1` (룩)
- 앙파상: `e5cap` (잡기) → `d5e6` (이동)
- 프로모션: `e7e8` (프로모션과 함께 이동)

**응답 대기**:
- 각 명령 전송 후 `MOVE_COMPLETE` 응답 대기
- 타임아웃: 30초
- 오류 시 `ERROR` 메시지 처리

---

### 6. `piece_detector.py` (컴퓨터 비전 기물 감지)
**역할**: 카메라로 체스판을 인식하여 기물 변화 감지

**주요 기능**:
- 체스판 초기화 (기준값 저장)
- 기물 변화 감지 (BGR 색상 비교)
- 변화된 칸 좌표 반환
- MJPEG 스트리밍 (변화 시각화)

**의존성**: 
- `warp_cam_picam2_v2` (체스판 와핑)
- `cv2`, `numpy`

**주요 함수**:
```python
initialize_board(cap, save_path)           # 체스판 초기화
initialize_board_with_picamera(save_path)  # Picamera2로 초기화
detect_piece_changes(cap, base_board_path, threshold, top_k)  # 변화 감지
detect_move_and_update(threshold, top_k, max_attempts)  # 변화 감지 + 업데이트
gen_edges_frames(cap, base_board_path, threshold, top_k)  # 스트리밍
test_webcam()                              # 웹캠 테스트
```

**작동 방식**:
1. 초기화: 8x8 그리드의 각 칸 BGR 평균값 저장
2. 변화 감지: 현재 프레임과 기준값 비교 (L2 norm)
3. 임계값 초과 칸 찾기 (기본: 12.0)
4. 상위 N개 칸 반환 (기본: 4개)
5. 체스 좌표 변환 (예: `e2e4`)

**반환 데이터**:
```python
# detect_piece_changes 반환값
[(i, j, diff_value), ...]  # 예: [(6, 4, 15.3), (4, 4, 13.2)]

# detect_move_and_update 반환값
"e2e4"  # 체스 좌표 문자열 (4자리)
```

---

## 🔄 데이터 흐름

### 게임 시작 흐름
```
1. terminal_chess.py 실행
   ↓
2. 엔진 초기화 (engine_manager)
   ↓
3. 로봇팔 초기화 (robot_arm_controller)
   ↓
4. 타이머 초기화 (timer_manager)
   ↓
5. CV 기준값 초기화 (piece_detector)
   ↓
6. 게임 루프 시작
```

### 플레이어 수 입력 흐름
```
1. 사용자 키보드 입력 (e2e4)
   ↓
2. move_analyzer로 분석
   ↓
3. 보드에 적용
   ↓
4. 타이머 버튼 대기
```

### CV 기물 감지 흐름
```
1. 타이머 버튼 입력 감지
   ↓
2. piece_detector로 변화 감지
   ↓
3. 변화된 좌표 반환 (e2e4)
   ↓
4. move_analyzer로 분석
   ↓
5. robot_arm_controller로 명령 전송
   ↓
6. 보드에 적용
   ↓
7. 기준값 업데이트
```

### Stockfish 수 실행 흐름
```
1. engine_manager로 평가 및 최선 수 계산
   ↓
2. move_analyzer로 움직임 타입 분석
   ↓
3. robot_arm_controller로 명령 전송
   ↓
4. 보드에 적용
```

---

## 🎯 주요 설정값

### `terminal_chess.py`
- `STOCKFISH_PATH`: Stockfish 경로 (`/usr/games/stockfish`)
- `player_color`: 플레이어 색상 (`'white'` 또는 `'black'`)
- `difficulty`: 난이도 (기본: 15)

### `engine_manager.py`
- `STOCKFISH_PATH`: Stockfish 경로
- `depth`: 탐색 깊이 (기본: 10, 게임에서는 difficulty 사용)

### `timer_manager.py`
- `port`: 시리얼 포트 (기본: `/dev/ttyACM0`)
- `baudrate`: 통신 속도 (기본: 9600)
- 기본 타이머: 600초 (10분)

### `robot_arm_controller.py`
- `port`: 시리얼 포트 (기본: `/dev/ttyUSB0`)
- `baudrate`: 통신 속도 (기본: 9600)
- `timeout`: 명령 응답 대기 시간 (30초)

### `piece_detector.py`
- `GRID`: 그리드 크기 (8x8)
- `WARP_SIZE`: 와핑 이미지 크기 (400)
- `CELL_MARGIN_RATIO`: 셀 마진 비율 (0.08)
- `DEFAULT_THRESHOLD`: 변화 감지 임계값 (12.0)
- `DEFAULT_TOP_K`: 반환할 최대 변화 칸 수 (4)

---

## 📊 상태 관리

### 전역 상태 (terminal_chess.py)
```python
current_board = chess.Board()  # 현재 보드 상태
player_color = 'white'         # 플레이어 색상
difficulty = 15                # 난이도
game_over = False              # 게임 종료 여부
move_count = 0                 # 이동 횟수
```

### 엔진 상태 (engine_manager.py)
- 싱글톤 패턴으로 전역 엔진 인스턴스 관리
- `_manager._engine`: Stockfish 엔진 인스턴스

### 타이머 상태 (timer_manager.py)
- 싱글톤 패턴으로 전역 타이머 매니저 관리
- `timer_manager.black_timer`: 검은색 타이머 (초)
- `timer_manager.white_timer`: 흰색 타이머 (초)
- 백그라운드 스레드로 모니터링

### 로봇팔 상태 (robot_arm_controller.py)
- 싱글톤 패턴으로 전역 컨트롤러 관리
- `_robot_controller.is_connected`: 연결 상태
- `_robot_controller.is_moving`: 움직임 중 여부

---

## 🚀 실행 방법

### 메인 게임 실행
```bash
cd brain
python terminal_chess.py
```

### 개별 모듈 테스트
```python
# piece_detector 테스트
from piece_detector import test_webcam
test_webcam()

# 로봇팔 연결 테스트
from robot_arm_controller import test_robot_connection
test_robot_connection()

# 타이머 연결 테스트
from timer_manager import init_chess_timer
init_chess_timer()
```

---

## 🔧 문제 해결

### Stockfish를 찾을 수 없는 경우
- 경로 확인: `/usr/games/stockfish` 또는 `/opt/homebrew/bin/stockfish`
- `engine_manager.py`의 `STOCKFISH_PATH` 수정

### 아두이노 타이머 연결 실패
- 포트 확인: `ls /dev/ttyACM*` 또는 `ls /dev/ttyUSB*`
- `timer_manager.py`의 `port` 수정

### 로봇팔 연결 실패
- 포트 확인: `ls /dev/ttyUSB*`
- `robot_arm_controller.py`의 `port` 수정
- 권한 확인: `sudo chmod 666 /dev/ttyUSB0`

### CV 기물 감지 실패
- 카메라 연결 확인
- 조명 조건 확인
- `piece_detector.py`의 `threshold` 조정
- 기준값 재초기화

---

## 📝 참고사항

1. **모듈 독립성**: 각 모듈은 가능한 한 독립적으로 설계되어 있어 개별 테스트가 가능합니다.
2. **싱글톤 패턴**: 엔진, 타이머, 로봇팔은 싱글톤 패턴으로 전역 인스턴스를 관리합니다.
3. **에러 처리**: 각 모듈은 연결 실패 시 게임을 계속 진행할 수 있도록 설계되어 있습니다.
4. **비동기 처리**: 타이머 모니터링은 백그라운드 스레드로 실행됩니다.
5. **명령 순차 실행**: 로봇팔 명령은 응답을 기다리면서 순차적으로 실행됩니다.

---

**최종 업데이트**: 2024년
