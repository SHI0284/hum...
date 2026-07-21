from __future__ import annotations

import os
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from core.config import PROJECT_ROOT


@dataclass(frozen=True)
class RecordingResult:
    path: Path
    duration_seconds: float
    sample_rate: int
    channels: int
    mock: bool = False


class Recorder:
    def __init__(
        self,
        output_dir: str | Path = "recordings",
        sample_rate: int = 44_100,
        channels: int = 1,
        input_device: int | str | None = None,
        max_recordings: int = 30,
    ) -> None:
        output_path = Path(output_dir)
        self.output_dir = (
            output_path if output_path.is_absolute() else PROJECT_ROOT / output_path
        )
        self.sample_rate = sample_rate
        self.channels = channels
        self.input_device = input_device
        self.max_recordings = max_recordings
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        duration_seconds: float,
        level_callback: Callable[[float], None] | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> RecordingResult:
        output_path = self._next_path()

        if os.getenv("HUM_MOCK_RECORDING") == "1":
            self._write_mock_wav(
                output_path,
                duration_seconds,
                level_callback,
                progress_callback,
            )
            self._trim_recording_queue()
            return RecordingResult(
                output_path,
                duration_seconds,
                self.sample_rate,
                self.channels,
                mock=True,
            )

        chunks: list[np.ndarray] = []
        started = time.monotonic()

        def on_audio(indata, frames, time_info, status) -> None:  # noqa: ANN001
            del frames, time_info
            if status:
                print(f"[audio input] {status}")

            block = indata.copy()
            chunks.append(block)
            rms = float(np.sqrt(np.mean(block * block) + 1e-12))
            # 일반적인 작은 USB 마이크의 레벨을 화면에서 잘 보이도록 확대합니다.
            level = max(0.0, min(1.0, rms * 10.0))
            if level_callback is not None:
                level_callback(level)
            if progress_callback is not None:
                progress_callback(
                    min(1.0, (time.monotonic() - started) / duration_seconds)
                )

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                device=self.input_device,
                callback=on_audio,
            ):
                sd.sleep(round(duration_seconds * 1000))
        except Exception as exc:
            raise RuntimeError(
                "마이크 입력을 열 수 없습니다. check_devices.py로 장치 번호를 확인하고 "
                "config.json의 audio_input_device를 설정해주세요.\n"
                f"원본 오류: {exc}"
            ) from exc

        if not chunks:
            raise RuntimeError("마이크에서 오디오 데이터가 들어오지 않았습니다.")

        audio = np.concatenate(chunks, axis=0)
        wanted_frames = round(duration_seconds * self.sample_rate)
        audio = audio[:wanted_frames]
        sf.write(str(output_path), audio, self.sample_rate, subtype="PCM_16")
        self._trim_recording_queue()

        return RecordingResult(
            output_path,
            duration_seconds,
            self.sample_rate,
            self.channels,
        )

    def _next_path(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return self.output_dir / f"hum_{timestamp}.wav"

    def _trim_recording_queue(self) -> None:
        recordings = sorted(
            self.output_dir.glob("*.wav"),
            key=lambda path: path.stat().st_mtime,
        )
        while len(recordings) > self.max_recordings:
            recordings.pop(0).unlink(missing_ok=True)

    def _write_mock_wav(
        self,
        output_path: Path,
        duration_seconds: float,
        level_callback: Callable[[float], None] | None,
        progress_callback: Callable[[float], None] | None,
    ) -> None:
        frames = int(duration_seconds * self.sample_rate)
        chunk = max(1, self.sample_rate // 30)
        amplitude = 10_000

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)

            for index in range(frames):
                phase = index / self.sample_rate
                envelope = 0.45 + 0.45 * abs(np.sin(phase * np.pi * 1.7))
                value = int(
                    amplitude
                    * envelope
                    * np.sin(2 * np.pi * (210 + 80 * np.sin(phase)) * phase)
                )
                wav_file.writeframes(
                    value.to_bytes(2, byteorder="little", signed=True)
                    * self.channels
                )
                if index % chunk == 0:
                    if level_callback is not None:
                        level_callback(float(envelope * 0.75))
                    if progress_callback is not None:
                        progress_callback(index / max(1, frames))
                    time.sleep(0.01)
