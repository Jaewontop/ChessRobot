#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
로봇팔 제어 모듈
체스 움직임을 분석하여 로봇팔에 적절한 명령을 전송
명령을 단위별로 분리하고 아두이노 응답을 기다리면서 순차 실행
"""

import chess
import serial
import time
from typing import Dict, Optional, Tuple, List

class RobotArmController:
    """로봇팔 제어 클래스"""
    
    def __init__(self, enabled: bool = True, port: str = '/dev/ttyUSB0', baudrate: int = 9600):
        self.enabled = enabled
        self.port = port
        self.baudrate = baudrate
        self.serial_connection = None
        self.is_connected = False
        self.is_moving = False
        
        # 기물 타입 매핑
        self.piece_names = {
            chess.PAWN: 'pawn',
            chess.KNIGHT: 'knight', 
            chess.BISHOP: 'bishop',
            chess.ROOK: 'rook',
            chess.QUEEN: 'queen',
            chess.KING: 'king'
        }
        
        print(f"🤖 로봇팔 컨트롤러 초기화:")
        print(f"   활성화: {self.enabled}")
        print(f"   포트: {self.port}")
        print(f"   통신속도: {self.baudrate}")
    
    def connect(self) -> bool:
        """시리얼 연결 시도"""
        if not self.enabled:
            print("🤖 로봇팔이 비활성화되어 있습니다.")
            return False
        
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1
            )
            self.is_connected = True
            print(f"✅ 로봇팔 연결 성공: {self.port}")
            return True
        except Exception as e:
            print(f"❌ 로봇팔 연결 실패: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """시리얼 연결 해제"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        self.is_connected = False
        self.is_moving = False
        print("🔌 로봇팔 연결 해제됨")
    
    def _generate_move_commands(self, move_type: Dict, move_uci: str) -> List[str]:
        """움직임 타입에 따라 명령 리스트 생성"""
        commands = []
        
        if not move_type or not move_uci:
            return commands
        
        from_square = move_uci[:2]
        to_square = move_uci[2:]
        
        # 움직임 타입별 명령 생성
        if move_type.get('is_castling'):
            # 캐슬링: 킹 먼저, 룩 나중에
            if move_uci in ['e1g1', 'e8g8']:  # 킹사이드 캐슬링
                commands.append(f"{from_square}cap")  # 킹 이동
                commands.append(f"h{from_square[1]}f{from_square[1]}")  # 룩 이동
            elif move_uci in ['e1c1', 'e8c8']:  # 퀸사이드 캐슬링
                commands.append(f"{from_square}cap")  # 킹 이동
                commands.append(f"a{from_square[1]}d{from_square[1]}")  # 룩 이동
                
        elif move_type.get('is_en_passant'):
            # 앙파상: 상대 기물 잡기 + 내 기물 이동
            captured_square = from_square[0] + to_square[1]  # 잡힌 폰의 위치
            commands.append(f"{captured_square}cap")  # 상대 폰 잡기
            commands.append(f"{from_square}{to_square}")  # 내 폰 이동
            
        elif move_type.get('is_capture'):
            # 기물 잡기: 잡기 + 이동
            commands.append(f"{to_square}cap")  # 기물 잡기
            commands.append(f"{from_square}{to_square}")  # 이동
            
        elif move_type.get('is_promotion'):
            # 프로모션: 이동 (프로모션은 이동과 동시에)
            commands.append(f"{from_square}{to_square}")
            
        else:
            # 일반 이동
            commands.append(f"{from_square}{to_square}")
        
        return commands
    
    def _send_single_command(self, command: str) -> bool:
        """단일 명령 전송 및 응답 대기"""
        if not self.is_connected:
            print("🤖 로봇팔이 연결되지 않았습니다. 명령 전송을 건너뜁니다.")
            return True  # 연결되지 않아도 성공으로 처리
        
        try:
            print(f"📡 명령 전송: {command}")
            
            # 명령 전송
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.write(f"{command}\n".encode())
                
                # MOVE_COMPLETE 응답 대기
                start_time = time.time()
                timeout = 30  # 30초 타임아웃
                
                while time.time() - start_time < timeout:
                    if self.serial_connection.in_waiting:
                        response = self.serial_connection.readline().decode().strip()
                        print(f"🤖 로봇팔 응답: {response}")
                        
                        if response == "MOVE_COMPLETE":
                            print("✅ 명령 완료")
                            return True
                        elif response.startswith("ERROR"):
                            print(f"❌ 로봇팔 오류: {response}")
                            return False
                    
                    time.sleep(0.1)
                
                print("⏰ 명령 응답 타임아웃")
                return False
            else:
                print("❌ 시리얼 연결이 열려있지 않습니다.")
                return False
                
        except Exception as e:
            print(f"[!] 명령 전송 실패: {e}")
            return False
    
    def execute_move(self, move_type: Dict, move_uci: str) -> bool:
        """움직임 분석 및 로봇팔 명령 순차 실행"""
        if not self.enabled:
            return False
        
        if self.is_moving:
            print("🤖 로봇팔이 이미 움직이는 중입니다.")
            return False
        
        # 움직임 분석
        commands = self._generate_move_commands(move_type, move_uci)
        if not commands:
            print("❌ 움직임 분석 실패")
            return False
        
        print(f"🤖 움직임 분석 완료: {len(commands)}개 명령")
        for i, cmd in enumerate(commands, 1):
            print(f"   {i}. {cmd}")
        
        # 로봇팔 연결 상태 확인
        if not self.is_connected:
            print("🤖 로봇팔이 연결되지 않았습니다. 명령만 표시합니다.")
            print("📋 실행될 명령들:")
            for i, command in enumerate(commands, 1):
                print(f"   {i}. {command}")
            print("✅ 명령 분석 완료 (실제 실행 없음)")
            return True
        
        # 로봇팔 움직임 시작
        self.is_moving = True
        print("🤖 로봇이 움직이는 중...")
        
        try:
            # 명령들을 순차적으로 실행
            for i, command in enumerate(commands, 1):
                print(f"🤖 명령 {i}/{len(commands)} 실행 중: {command}")
                
                if not self._send_single_command(command):
                    print(f"❌ 명령 {i} 실행 실패")
                    self.is_moving = False
                    return False
                
                # 마지막 명령이 아니면 잠시 대기
                if i < len(commands):
                    time.sleep(0.5)
            
            print("✅ 모든 명령 실행 완료!")
            return True
            
        except Exception as e:
            print(f"[!] 명령 실행 중 오류: {e}")
            return False
        finally:
            self.is_moving = False
    
    def get_move_description(self, move_type: Dict, move_uci: str) -> str:
        """움직임에 대한 설명 반환"""
        if not move_type or not move_uci:
            return "알 수 없는 움직임"
        
        if move_type.get('is_castling'):
            return "캐슬링"
        elif move_type.get('is_en_passant'):
            return "앙파상"
        elif move_type.get('is_capture'):
            return "기물 잡기"
        elif move_type.get('is_promotion'):
            return "프로모션"
        else:
            return "일반 이동"
    
    def configure(self, enabled: bool = None, port: str = None, baudrate: int = None):
        """로봇팔 설정 조정"""
        if enabled is not None:
            self.enabled = enabled
        if port is not None:
            self.port = port
        if baudrate is not None:
            self.baudrate = baudrate
        
        print(f"🤖 로봇팔 설정 업데이트:")
        print(f"   활성화: {self.enabled}")
        print(f"   포트: {self.port}")
        print(f"   통신속도: {self.baudrate}")
    
    def get_status(self) -> Dict:
        """로봇팔 상태 정보 반환"""
        return {
            'enabled': self.enabled,
            'port': self.port,
            'baudrate': self.baudrate,
            'is_connected': self.is_connected,
            'is_moving': self.is_moving,
            'connection': 'connected' if self.is_connected else 'disconnected',
            'status': 'moving' if self.is_moving else 'idle'
        }
    
    def test_connection(self) -> bool:
        """연결 테스트"""
        if not self.enabled:
            print("🤖 로봇팔이 비활성화되어 있습니다.")
            return False
        
        if self.connect():
            self.disconnect()
            return True
        return False


# 전역 인스턴스
_robot_controller = RobotArmController()

def get_robot_controller() -> RobotArmController:
    """전역 로봇팔 컨트롤러 인스턴스 반환"""
    return _robot_controller

def init_robot_arm(enabled: bool = True, port: str = '/dev/ttyUSB0', baudrate: int = 9600) -> bool:
    """로봇팔 초기화"""
    global _robot_controller
    _robot_controller = RobotArmController(enabled, port, baudrate)
    return _robot_controller.enabled

def connect_robot_arm() -> bool:
    """로봇팔 연결"""
    return _robot_controller.connect()

def disconnect_robot_arm():
    """로봇팔 연결 해제"""
    _robot_controller.disconnect()

def execute_robot_move(move_type: Dict, move_uci: str) -> bool:
    """로봇팔 움직임 실행"""
    return _robot_controller.execute_move(move_type, move_uci)

def get_move_description(move_type: Dict, move_uci: str) -> str:
    """움직임 설명 반환"""
    return _robot_controller.get_move_description(move_type, move_uci)

def is_robot_moving() -> bool:
    """로봇팔이 움직이는 중인지 확인"""
    return _robot_controller.is_moving

def configure_robot_arm(enabled: bool = None, port: str = None, baudrate: int = None):
    """로봇팔 설정 조정"""
    _robot_controller.configure(enabled, port, baudrate)

def get_robot_status() -> Dict:
    """로봇팔 상태 정보"""
    return _robot_controller.get_status()

def test_robot_connection() -> bool:
    """로봇팔 연결 테스트"""
    return _robot_controller.test_connection()
