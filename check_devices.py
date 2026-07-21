from __future__ import annotations

import sounddevice as sd

print("=== 기본 장치 [입력, 출력] ===")
print(sd.default.device)
print()
print("=== 전체 오디오 장치 ===")
print(sd.query_devices())
print()
print("USB 마이크의 번호를 config.json의 audio_input_device에 입력하세요.")
print('예: "audio_input_device": 2')
print("스피커가 기본 출력이 아니면 audio_output_device에도 번호를 입력하세요.")
