# ♟️ Chess Robot Controller

체스 로봇의 두뇌 역할을 담당하는 Python 기반 제어 시스템입니다.

## 🏗️ 프로젝트 구조

```
ChessRobot/
├── brain/                          # 두뇌 역할 (메인 로직)
│   ├── __init__.py                # 패키지 초기화
│   ├── communication.py           # 아두이노 통신 관리
│   ├── chess_engine.py            # 체스 게임 엔진
│   ├── game_controller.py         # 게임 전체 제어
│   └── test_communication.py      # 통신 테스트 스크립트
├── CV/                            # 컴퓨터 비전 (기물 인식)
├── motion/                        # 로봇 팔 제어
├── init/                          # 초기화 및 설정
├── main.py                        # 메인 실행 파일
├── requirements.txt               # Python 의존성
└── README.md                      # 이 파일
```

## 🚀 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 메인 프로그램 실행

```bash
python main.py
```

### 3. 통신 테스트

```bash
cd brain
python test_communication.py
```

## 🎮 사용법

### 메인 프로그램 명령어

- `status` - 현재 게임 상태 확인
- `move e2 e4` - 기물 이동 (예: e2에서 e4로)
- `timer` - 타이머 상태만 확인
- `reset` - 게임 리셋
- `help` - 도움말 표시
- `quit` 또는 `exit` - 프로그램 종료

### 예시

```bash
체스 로봇> status
체스 로봇> timer
체스 로봇> move e2 e4
체스 로봇> move e7 e5
체스 로봇> reset
체스 로봇> quit
```

## 🔌 아두이노 통신

### 메시지 형식

- **턴 변경**: `P1`, `P2`
- **이동 명령**: `MOVE:e2-e4`
- **상태 업데이트**: `STATUS:READY`
- **오류**: `ERROR:INVALID_MOVE`
- **확인**: `ACK:MOVE:e2-e4`

#### 타이머 관련 메시지

- **타이머 만료**: `TIMER_EXPIRED:P1:COMPUTER` (플레이어, 타입)
- **타이머 버튼 눌림**: `TIMER_PRESSED:P2:HUMAN:TRUE` (플레이어, 타입, 눌림상태)
- **타이머 상태**: `TIMER_STATUS:P1:COMPUTER:120:TRUE` (플레이어, 타입, 시간, 눌림상태)
- **타이머 리셋**: `TIMER_RESET:P1` (플레이어)

### 포트 설정

기본 포트 설정:
- 아두이노1: `/dev/ttyACM0`
- 아두이노2: `/dev/ttyACM1`
- 통신 속도: 9600 baud

## 🧠 핵심 모듈

### 1. ArduinoManager (`brain/communication.py`)

- 아두이노와의 양방향 통신 관리
- 자동 재연결 기능
- 메시지 큐 및 타입별 핸들러
- 스레드 기반 비동기 통신

### 2. ChessEngine (`brain/chess_engine.py`)

- 체스 게임 로직 처리
- 이동 유효성 검사
- 게임 상태 관리 (체크, 체크메이트 등)
- FEN 표기법 지원

### 3. GameController (`brain/game_controller.py`)

- 전체 게임 흐름 제어
- 통신과 체스 엔진 통합
- 자동 모드 지원
- 콜백 기반 이벤트 처리

## 🔧 설정 및 커스터마이징

### 포트 변경

`brain/communication.py`에서 포트 설정을 수정할 수 있습니다:

```python
arduino_manager = ArduinoManager(
    arduino1_port="/dev/ttyUSB0",  # 원하는 포트
    arduino2_port="/dev/ttyUSB1",  # 원하는 포트
    baud_rate=115200               # 원하는 통신 속도
)
```

### 메시지 핸들러 추가

```python
def custom_handler(message):
    print(f"커스텀 메시지: {message.data}")

arduino_manager.register_message_handler(
    MessageType.STATUS_UPDATE, 
    custom_handler
)
```

## 🐛 문제 해결

### 연결 문제

1. **포트 권한 확인**
   ```bash
   sudo chmod 666 /dev/ttyACM0
   sudo chmod 666 /dev/ttyACM1
   ```

2. **포트 확인**
   ```bash
   ls -la /dev/ttyACM*
   ```

3. **연결 상태 확인**
   ```bash
   python main.py
   # status 명령어로 연결 상태 확인
   ```

### 의존성 문제

```bash
# 가상환경 사용 권장
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

## 📝 개발 가이드

### 새 메시지 타입 추가

1. `MessageType` enum에 새 타입 추가
2. `_process_incoming_message`에서 파싱 로직 추가
3. 적절한 핸들러 함수 구현

### 새 기능 추가

1. `GameController`에 새 메서드 추가
2. 필요한 경우 `ChessEngine` 확장
3. 메인 프로그램에 명령어 추가

## 🤝 기여하기

1. 이슈 등록
2. 기능 브랜치 생성
3. 코드 작성 및 테스트
4. Pull Request 생성

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 📞 지원

문제가 있거나 질문이 있으시면 이슈를 등록해 주세요. 