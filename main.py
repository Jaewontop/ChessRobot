#!/usr/bin/env python3
"""
Chess Robot Terminal Game Launcher
터미널 체스 게임을 실행하는 간단한 런처
"""

import os
import sys
import subprocess

def main():
    """터미널 체스 게임 실행"""
    print("♔ 체스 로봇 터미널 게임 런처 ♔")
    print("=" * 50)
    
    # 현재 디렉토리 확인
    current_dir = os.path.dirname(os.path.abspath(__file__))
    terminal_chess_path = os.path.join(current_dir, "brain/terminal_chess.py")
    
    # terminal_chess.py 파일 존재 확인
    if not os.path.exists(terminal_chess_path):
        print(f"[!] 오류: {terminal_chess_path} 파일을 찾을 수 없습니다.")
        return
    
    print(f"[→] 터미널 체스 게임 실행 중...")
    print(f"[→] 파일 경로: {terminal_chess_path}")
    print("=" * 50)
    
    try:
        # terminal_chess.py 실행
        subprocess.run([sys.executable, terminal_chess_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] 게임 실행 오류: {e}")
    except KeyboardInterrupt:
        print("\n[→] 게임이 중단되었습니다.")
    except Exception as e:
        print(f"[!] 예상치 못한 오류: {e}")

if __name__ == '__main__':
    main()
