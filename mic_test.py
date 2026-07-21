from __future__ import annotations

from core.config import load_config
from core.recorder import Recorder

config = load_config()
recorder = Recorder(
    sample_rate=int(config.get("sample_rate", 44_100)),
    channels=int(config.get("channels", 1)),
    input_device=config.get("audio_input_device"),
)
print("3초 시험 녹음을 시작합니다...")
result = recorder.record(3.0)
print(f"완료: {result.path}")
print(f'aplay "{result.path}"')
