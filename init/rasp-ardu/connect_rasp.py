import serial
import time
import random

# 포트는 환경에 맞게 수정
ARDUINO1_PORT = "/dev/ttyACM0"
ARDUINO2_PORT = "/dev/ttyACM1"
BAUD = 9600

arduino1 = None
arduino2 = None
prev_time_p1 = None
prev_time_p2 = None

def try_connect_arduino1():
    global arduino1
    try:
        arduino1 = serial.Serial(ARDUINO1_PORT, BAUD, timeout=0.1)
        print(f"[✓] 아두이노1(타이머) 연결 성공: {ARDUINO1_PORT}")
        time.sleep(2)
    except serial.SerialException:
        print(f"[!] 아두이노1(타이머) 연결 실패: {ARDUINO1_PORT}")
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

        # 아두이노1(타이머)에서 1초마다 전송되는 타이머 정보 수신
        if arduino1 and arduino1.in_waiting > 0:
            try:
                msg = arduino1.readline().decode().strip()
                if msg.startswith("P1:") and "," in msg and "P2:" in msg:
                    # P1:시간,P2:시간 형식 파싱
                    parts = msg.split(",")
                    if len(parts) == 2:
                        p1_part = parts[0]  # P1:시간
                        p2_part = parts[1]  # P2:시간
                        
                        try:
                            time_p1 = int(p1_part.split(":")[1])
                            time_p2 = int(p2_part.split(":")[1])
                            
                            # 시간이 변경되었을 때만 출력
                            if time_p1 != prev_time_p1 or time_p2 != prev_time_p2:
                                print(f"[⏱️] 타이머 업데이트 - P1: {time_p1}초, P2: {time_p2}초")
                                prev_time_p1 = time_p1
                                prev_time_p2 = time_p2
                                
                        except (ValueError, IndexError):
                            print(f"[!] 타이머 데이터 파싱 오류: {msg}")
                            
            except serial.SerialException:
                print("[!] 아두이노1(타이머) 통신 오류")
                arduino1.close()
                arduino1 = None
        elif arduino1 is None:
            try_connect_arduino1()

        time.sleep(1)  # 1초마다 체크

except KeyboardInterrupt:
    print("\n[🛑] 사용자에 의해 종료됨 (Ctrl+C)")
    if arduino1:
        arduino1.close()
    if arduino2:
        arduino2.close()
    print("[✓] 포트 정리 완료, 프로그램 종료")
