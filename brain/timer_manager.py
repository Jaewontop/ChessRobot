#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
아두이노 타이머 관리자
아두이노 시리얼 통신을 통한 타이머 데이터 처리
"""

import serial
import time
import threading
from datetime import datetime

class TimerManager:
    """아두이노 타이머 관리 클래스"""
    
    def __init__(self, port="/dev/ttyACM0", baud=9600):
        self.port = port
        self.baud = baud
        self.serial = None
        self.is_connected = False
        self.black_timer = 600
        self.white_timer = 600
        self.monitor_thread = None
        self.is_monitoring = False
        
        # 모니터링 서버 설정
        self.monitor_server_url = 'http://localhost:5002'
        self.enable_monitoring = True
        
    def connect(self):
        """아두이노 시리얼 연결"""
        try:
            self.serial = serial.Serial(self.port, self.baud, timeout=1)
            self.is_connected = True
            print(f"[✓] 아두이노 타이머 연결 성공: {self.port}")
            return True
        except serial.SerialException as e:
            print(f"[!] 아두이노 타이머 연결 실패: {self.port} - {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """아두이노 시리얼 연결 해제"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.is_connected = False
            print(f"[✓] 아두이노 타이머 연결 해제: {self.port}")
    
    def parse_timer_data(self, data):
        """다양한 형식의 타이머 데이터를 파싱합니다."""
        try:
            # 형식 1: DATA: P1:431,P2:600
            if data.startswith('DATA:') and 'P1:' in data and 'P2:' in data:
                timer_part = data.replace('DATA:', '').strip()
                if timer_part.startswith('P1:') and ',P2:' in timer_part:
                    return timer_part
            
            # 형식 2: P1:431,P2:600 (직접 형식)
            elif data.startswith('P1:') and ',P2:' in data:
                return data
            
            # 형식 3: LOG: RUNNING | P1: 432s | P2: 600s | Turn: P1
            elif data.startswith('LOG:') and 'P1:' in data and 'P2:' in data:
                parts = data.split('|')
                p1_part = None
                p2_part = None
                
                for part in parts:
                    part = part.strip()
                    if part.startswith('P1:'):
                        p1_part = part
                    elif part.startswith('P2:'):
                        p2_part = part
                
                if p1_part and p2_part:
                    p1_time = p1_part.replace('P1:', '').replace('s', '').strip()
                    p2_time = p2_part.replace('P2:', '').replace('s', '').strip()
                    return f"P1:{p1_time},P2:{p2_time}"
            
            return None
            
        except Exception as e:
            print(f"[!] 타이머 데이터 파싱 오류: {e}")
            return None
    
    def read_timer_data(self):
        """아두이노에서 타이머 데이터 읽기"""
        if not self.is_connected or not self.serial or not self.serial.is_open:
            return None
        
        try:
            if self.serial.in_waiting > 0:
                raw_data = self.serial.readline()
                data = raw_data.decode().strip()
                
                
                timer_data = self.parse_timer_data(data)
                if timer_data:
                    return timer_data                
        except Exception as e:
            print(f"[!] 아두이노 타이머 데이터 읽기 오류: {e}")
        
        return None
    
    def send_command(self, command):
        """아두이노에 명령 전송"""
        if not self.is_connected or not self.serial or not self.serial.is_open:
            return False
        
        try:
            self.serial.write(f"{command}\n".encode())
            print(f"[→] 아두이노 타이머 명령 전송: {command}")
            return True
        except Exception as e:
            print(f"[!] 아두이노 타이머 명령 전송 오류: {e}")
            return False
    
    def start_timer(self):
        """타이머 시작"""
        return self.send_command("START_TIMER")
    
    def stop_timer(self):
        """타이머 정지"""
        return self.send_command("STOP_TIMER")
    
    def reset_timer(self):
        """타이머 리셋"""
        return self.send_command("RESET_TIMER")
    
    def format_time(self, seconds):
        """초를 MM:SS 형식으로 변환"""
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02d}:{secs:02d}"
    
    def get_timer_display(self):
        """타이머 표시용 문자열 반환"""
        return f"검은색: {self.format_time(self.black_timer)} | 흰색: {self.format_time(self.white_timer)}"
    
    def update_timers_from_data(self, timer_data):
        """타이머 데이터로부터 시간 업데이트"""
        try:
            if 'P1:' in timer_data and 'P2:' in timer_data:
                parts = timer_data.split(',')
                if len(parts) == 2:
                    p1_time = int(parts[0].split(':')[1])
                    p2_time = int(parts[1].split(':')[1])
                    
                    # P1은 검은색, P2는 흰색
                    self.black_timer = p1_time
                    self.white_timer = p2_time
                    
                    # print(f"[✓] 타이머 업데이트: 흰색 {self.format_time(self.white_timer)}, 검은색 {self.format_time(self.black_timer)}")
                    return True
                    
        except Exception as e:
            print(f"[!] 타이머 업데이트 오류: {e}")
        
        return False
    
    def start_monitoring(self, callback=None):
        """타이머 모니터링 시작"""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        
        def monitor_loop():
            cycle_count = 0
            while self.is_monitoring:
                cycle_count += 1
                
                timer_data = self.read_timer_data()
                if timer_data:
                    if self.update_timers_from_data(timer_data):
                        # 콜백 함수가 있으면 호출
                        if callback:
                            try:
                                callback(self.black_timer, self.white_timer)
                            except Exception as e:
                                print(f"[!] 타이머 콜백 오류: {e}")
                    else:
                        # 업데이트 실패 (형식 불일치 등)
                        pass
                else:
                    # 데이터 없음
                    pass
                time.sleep(1)
        
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        print(f"[✓] 타이머 모니터링 시작")
    
    def stop_monitoring(self):
        """타이머 모니터링 정지"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
        print(f"[✓] 타이머 모니터링 정지")
    
    def get_status(self):
        """타이머 상태 반환"""
        return {
            'is_connected': self.is_connected,
            'is_monitoring': self.is_monitoring,
            'black_timer': self.black_timer,
            'white_timer': self.white_timer,
            'port': self.port,
            'baud': self.baud
        }
    
    def reset_timers(self):
        """타이머를 기본값으로 리셋"""
        self.black_timer = 600
        self.white_timer = 600
        print(f"[✓] 타이머 리셋: 10:00")
    
    def set_timers(self, black_time, white_time):
        """타이머 설정"""
        self.black_timer = max(0, black_time)
        self.white_timer = max(0, white_time)
        print(f"[✓] 타이머 설정: 검은색 {self.format_time(self.black_timer)}, 흰색 {self.format_time(self.white_timer)}")

# 전역 타이머 매니저 인스턴스
timer_manager = TimerManager()

def get_timer_manager():
    """전역 타이머 매니저 반환"""
    return timer_manager

def connect_timer():
    """타이머 연결 (편의 함수)"""
    return timer_manager.connect()

def disconnect_timer():
    """타이머 연결 해제 (편의 함수)"""
    timer_manager.disconnect()

def start_timer_monitoring(callback=None):
    """타이머 모니터링 시작 (편의 함수)"""
    timer_manager.start_monitoring(callback)

def stop_timer_monitoring():
    """타이머 모니터링 정지 (편의 함수)"""
    timer_manager.stop_monitoring()

def get_timer_display():
    """타이머 표시 문자열 반환 (편의 함수)"""
    return timer_manager.get_timer_display()

def get_black_timer():
    """검은색 타이머 값 반환 (편의 함수)"""
    return timer_manager.black_timer

def get_white_timer():
    """흰색 타이머 값 반환 (편의 함수)"""
    return timer_manager.white_timer

# 체스 게임용 타이머 함수들
def connect_arduino():
    """아두이노 타이머 연결 (체스 게임용)"""
    return connect_timer()

def start_arduino_thread():
    """아두이노 타이머 연결 및 모니터링 시작 (체스 게임용)"""
    if connect_arduino():
        print("[✓] 아두이노 타이머 연결 성공")
        # 타이머 모니터링 시작
        start_timer_monitoring()
        return True
    else:
        print("[!] 아두이노 타이머 연결 실패 - 타이머 없이 진행")
        return False

def init_chess_timer():
    """체스 게임용 타이머 초기화"""
    print(f"[→] 체스 게임 타이머 초기화 중...")
    
    # 타이머 연결 시도
    if start_arduino_thread():
        print(f"[✓] 체스 게임 타이머 초기화 완료")
        return True
    else:
        print(f"[!] 체스 게임 타이머 초기화 실패")
        return False

def get_chess_timer_status():
    """체스 게임용 타이머 상태 반환"""
    tm = get_timer_manager()
    return {
        'is_connected': tm.is_connected,
        'is_monitoring': tm.is_monitoring,
        'black_timer': tm.black_timer,
        'white_timer': tm.white_timer,
        'port': tm.port,
        'baud': tm.baud
    }
