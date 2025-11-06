#!/usr/bin/env python3
"""
초록색 마커 검증 도구
- 감지된 4개 점이 실제 체스보드 마커인지 확인
- 기하학적 검증 (사각형 형태, 크기, 비율)
- 색상 일관성 검증
- 위치 안정성 검증
"""

import cv2
import numpy as np
import time
from picamera2 import Picamera2
from warp_cam_picam2_v2 import find_green_corners, Hmin, Hmax, Smin, Smax, Vmin, Vmax

class MarkerValidator:
    def __init__(self):
        self.picam2 = Picamera2()
        cfg = self.picam2.create_preview_configuration(
            main={"size": (1280, 720), "format": "RGB888"},
            controls={"FrameRate": 30}
        )
        self.picam2.configure(cfg)
        self.picam2.start()
        time.sleep(1)
        
        # 검증 결과 저장
        self.validation_history = []
        self.stable_count = 0
        self.required_stable_frames = 10
        
        print("🔍 초록색 마커 검증 도구 시작")
        print("📋 검증 항목:")
        print("   1. 기하학적 검증 (사각형 형태, 크기, 비율)")
        print("   2. 색상 일관성 검증")
        print("   3. 위치 안정성 검증")
        print("   4. 마커 크기 일관성 검증")
        print("⏹️  Ctrl+C로 종료")
        print("-" * 60)
    
    def geometric_validation(self, corners):
        """기하학적 검증"""
        if corners is None or len(corners) != 4:
            return False, "4개 점이 아님"
        
        # 1. 사각형 형태 검증
        pts = np.array(corners, dtype=np.float32)
        
        # 각 변의 길이 계산
        sides = []
        for i in range(4):
            p1 = pts[i]
            p2 = pts[(i + 1) % 4]
            side_length = np.linalg.norm(p2 - p1)
            sides.append(side_length)
        
        # 대변의 길이 차이 (10% 이내)
        opposite_diff1 = abs(sides[0] - sides[2]) / max(sides[0], sides[2])
        opposite_diff2 = abs(sides[1] - sides[3]) / max(sides[1], sides[3])
        
        if opposite_diff1 > 0.1 or opposite_diff2 > 0.1:
            return False, f"대변 길이 차이: {opposite_diff1:.2f}, {opposite_diff2:.2f}"
        
        # 2. 각도 검증 (90도에 가까운지)
        angles = []
        for i in range(4):
            p1 = pts[i]
            p2 = pts[(i + 1) % 4]
            p3 = pts[(i + 2) % 4]
            
            v1 = p1 - p2
            v2 = p3 - p2
            cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
            angle = np.arccos(np.clip(cos_angle, -1, 1)) * 180 / np.pi
            angles.append(angle)
        
        # 각도가 90도에 가까운지 (15도 이내)
        angle_errors = [abs(angle - 90) for angle in angles]
        max_angle_error = max(angle_errors)
        
        if max_angle_error > 15:
            return False, f"각도 오차: {max_angle_error:.1f}도"
        
        # 3. 면적 검증 (너무 작거나 크지 않은지)
        area = cv2.contourArea(pts.reshape(-1, 1, 2).astype(np.int32))
        if area < 10000 or area > 200000:  # 픽셀 단위
            return False, f"면적 부적절: {area:.0f}"
        
        return True, f"기하학적 검증 통과 (면적: {area:.0f})"
    
    def color_consistency_validation(self, frame, corners):
        """색상 일관성 검증"""
        if corners is None or len(corners) != 4:
            return False, "4개 점이 아님"
        
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        colors = []
        
        for corner in corners:
            x, y = int(corner[0]), int(corner[1])
            # 마커 중심 주변 10x10 영역의 평균 색상
            roi = hsv[max(0, y-5):min(hsv.shape[0], y+5), 
                     max(0, x-5):min(hsv.shape[1], x+5)]
            if roi.size > 0:
                mean_color = np.mean(roi.reshape(-1, 3), axis=0)
                colors.append(mean_color)
        
        if len(colors) != 4:
            return False, "색상 추출 실패"
        
        # 색상 일관성 검증 (표준편차가 작은지)
        colors = np.array(colors)
        h_std = np.std(colors[:, 0])
        s_std = np.std(colors[:, 1])
        v_std = np.std(colors[:, 2])
        
        # H, S, V의 표준편차가 임계값 이내인지
        if h_std > 10 or s_std > 30 or v_std > 30:
            return False, f"색상 불일치: H={h_std:.1f}, S={s_std:.1f}, V={v_std:.1f}"
        
        return True, f"색상 일관성 통과 (H={h_std:.1f}, S={s_std:.1f}, V={v_std:.1f})"
    
    def size_consistency_validation(self, frame, corners):
        """마커 크기 일관성 검증"""
        if corners is None or len(corners) != 4:
            return False, "4개 점이 아님"
        
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
        upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        
        # 각 마커 주변의 마스크 영역 크기 계산
        marker_sizes = []
        for corner in corners:
            x, y = int(corner[0]), int(corner[1])
            # 20x20 영역에서 마스크 픽셀 수 계산
            roi = mask[max(0, y-10):min(mask.shape[0], y+10), 
                      max(0, x-10):min(mask.shape[1], x+10)]
            size = np.sum(roi > 0)
            marker_sizes.append(size)
        
        if len(marker_sizes) != 4:
            return False, "크기 측정 실패"
        
        # 크기 일관성 검증 (표준편차가 작은지)
        sizes = np.array(marker_sizes)
        size_std = np.std(sizes)
        size_mean = np.mean(sizes)
        
        # 크기 변동계수 (표준편차/평균)가 0.3 이내인지
        cv = size_std / size_mean if size_mean > 0 else 1
        
        if cv > 0.3:
            return False, f"크기 불일치: CV={cv:.2f} (평균={size_mean:.0f})"
        
        return True, f"크기 일관성 통과 (CV={cv:.2f}, 평균={size_mean:.0f})"
    
    def position_stability_validation(self, corners):
        """위치 안정성 검증"""
        if corners is None or len(corners) != 4:
            return False, "4개 점이 아님"
        
        # 이전 위치와 비교
        if len(self.validation_history) > 0:
            prev_corners = self.validation_history[-1]['corners']
            if prev_corners is not None:
                # 각 점의 이동 거리 계산
                distances = []
                for i in range(4):
                    dist = np.linalg.norm(np.array(corners[i]) - np.array(prev_corners[i]))
                    distances.append(dist)
                
                max_distance = max(distances)
                avg_distance = np.mean(distances)
                
                # 이동 거리가 임계값 이내인지
                if max_distance > 20:  # 20픽셀 이내
                    return False, f"위치 불안정: 최대이동={max_distance:.1f}px"
                
                return True, f"위치 안정: 평균이동={avg_distance:.1f}px"
        
        return True, "첫 번째 프레임"
    
    def validate_markers(self, frame):
        """전체 마커 검증"""
        # 초록색 마커 찾기
        lower = np.array([Hmin, Smin, Vmin], dtype=np.uint8)
        upper = np.array([Hmax, Smax, Vmax], dtype=np.uint8)
        corners = find_green_corners(frame, lower, upper, min_area=60)
        
        validation_results = {
            'corners': corners,
            'timestamp': time.time(),
            'geometric': self.geometric_validation(corners),
            'color': self.color_consistency_validation(frame, corners),
            'size': self.size_consistency_validation(frame, corners),
            'stability': self.position_stability_validation(corners)
        }
        
        # 전체 검증 결과
        all_passed = all(result[0] for key, result in validation_results.items() 
                        if key not in ['corners', 'timestamp'])
        
        validation_results['overall'] = (all_passed, "전체 검증 통과" if all_passed else "일부 검증 실패")
        
        # 히스토리에 추가
        self.validation_history.append(validation_results)
        if len(self.validation_history) > 50:  # 최근 50프레임만 유지
            self.validation_history.pop(0)
        
        return validation_results
    
    def draw_validation_info(self, frame, results):
        """검증 결과를 화면에 표시"""
        corners = results['corners']
        
        # 마커 표시
        if corners is not None and len(corners) == 4:
            colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (255, 255, 0)]
            labels = ['TL', 'TR', 'BR', 'BL']
            
            for i, (corner, color, label) in enumerate(zip(corners, colors, labels)):
                x, y = int(corner[0]), int(corner[1])
                cv2.circle(frame, (x, y), 15, color, -1)
                cv2.circle(frame, (x, y), 20, (255, 255, 255), 2)
                cv2.putText(frame, label, (x-10, y-25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            
            # 4개 점을 연결하는 선 그리기
            pts = corners.reshape((-1, 1, 2)).astype(np.int32)
            cv2.polylines(frame, [pts], True, (255, 255, 255), 2)
        
        # 검증 결과 표시
        y_offset = 30
        for key, (passed, message) in results.items():
            if key in ['corners', 'timestamp']:
                continue
            
            color = (0, 255, 0) if passed else (0, 0, 255)
            status = "✅" if passed else "❌"
            text = f"{status} {key.upper()}: {message}"
            cv2.putText(frame, text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y_offset += 25
        
        # 안정성 카운트 표시
        if results['overall'][0]:
            self.stable_count += 1
        else:
            self.stable_count = 0
        
        stability_text = f"안정성: {self.stable_count}/{self.required_stable_frames}"
        stability_color = (0, 255, 0) if self.stable_count >= self.required_stable_frames else (0, 255, 255)
        cv2.putText(frame, stability_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.8, stability_color, 2)
        
        # 최종 판정
        if self.stable_count >= self.required_stable_frames:
            cv2.putText(frame, "🎯 VALID MARKERS DETECTED!", (10, y_offset + 40), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)
        elif results['corners'] is not None:
            cv2.putText(frame, "⚠️  CHECKING STABILITY...", (10, y_offset + 40), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 3)
        else:
            cv2.putText(frame, "❌ NO MARKERS DETECTED", (10, y_offset + 40), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
    
    def run(self):
        """메인 루프"""
        try:
            while True:
                # 프레임 캡처
                rgb = self.picam2.capture_array()
                frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                
                # 마커 검증
                results = self.validate_markers(frame)
                
                # 결과 표시
                self.draw_validation_info(frame, results)
                
                # 화면에 표시
                cv2.imshow('Marker Validator', frame)
                
                # 키 입력 처리
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    # 리셋
                    self.validation_history = []
                    self.stable_count = 0
                    print("🔄 검증 히스토리 리셋됨")
                elif key == ord('s'):
                    # 현재 상태 저장
                    if results['corners'] is not None:
                        print(f"💾 현재 마커 위치: {results['corners'].tolist()}")
                        print(f"📊 검증 결과: {results['overall'][1]}")
                
        except KeyboardInterrupt:
            print("\n🛑 사용자에 의해 중단됨")
        
        finally:
            self.picam2.stop()
            cv2.destroyAllWindows()
            print("📷 카메라 해제 완료")
            
            # 최종 통계
            if len(self.validation_history) > 0:
                total_frames = len(self.validation_history)
                valid_frames = sum(1 for r in self.validation_history if r['overall'][0])
                print(f"📈 최종 통계: {valid_frames}/{total_frames} 프레임 검증 통과 ({valid_frames/total_frames*100:.1f}%)")

if __name__ == "__main__":
    validator = MarkerValidator()
    validator.run()
