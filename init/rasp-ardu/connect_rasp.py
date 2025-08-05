import serial
import time
import random

# 포트는 환경에 맞게 수정
ARDUINO1_PORT = "/dev/ttyACM0"
ARDUINO2_PORT = "/dev/ttyACM1"
BAUD = 9600

arduino1 = None
arduino2 = None
prev_state = None

def try_connect_arduino1():
    global arduino1
    try:
        arduino1 = serial.Serial(ARDUINO1_PORT, BAUD, timeout=0.1)
        print(f"[✓] 아두이노1 연결 성공: {ARDUINO1_PORT}")
        time.sleep(2)
    except serial.SerialException:
        print(f"[!] 아두이노1 연결 실패: {ARDUINO1_PORT}")
        arduino1 = None

def try_connect_arduino2():
    global arduino2
    try:
        arduino2 = serial.Serial(ARDUINO2_PORT, BAUD, timeout=1)
        print(f"[✓] 아두이노2 연결 성공: {ARDUINO2_PORT}")
        time.sleep(2)
    except serial.SerialException:
        print(f"[!] 아두이노2 연결 실패: {ARDUINO2_PORT}")
        arduino2 = None

try:
    try_connect_arduino1()
    try_connect_arduino2()

    while True:
        # 1초마다 아두이노2에 랜덤값 전송
        if arduino2:
            value = random.randint(0, 9)
            print(f"[→] 아두이노2에 전송: {value}")
            try:
                arduino2.write(f"{value}\n".encode())
            except serial.SerialException:
                print("[!] 아두이노2 전송 중 오류 발생")
                arduino2.close()
                arduino2 = None
        else:
            try_connect_arduino2()

        # 동시에 아두이노1에서 메시지 수신 여부 확인
        if arduino1 and arduino1.in_waiting > 0:
            try:
                msg = arduino1.readline().decode().strip()
                if msg in ["P1", "P2"] and msg != prev_state:
                    print(f"[✓] 턴 전환 감지: {msg}")
                    prev_state = msg
            except serial.SerialException:
                print("[!] 아두이노1 통신 오류")
                arduino1.close()
                arduino1 = None
        elif arduino1 is None:
            try_connect_arduino1()

        time.sleep(1)  # 랜덤값 주기

except KeyboardInterrupt:
    print("\n[🛑] 사용자에 의해 종료됨 (Ctrl+C)")
    if arduino1:
        arduino1.close()
    if arduino2:
        arduino2.close()
    print("[✓] 포트 정리 완료, 프로그램 종료")
