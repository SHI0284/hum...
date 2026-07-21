from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from PySide6.QtCore import QObject, Signal


class AudioPlayer(QObject):
    stateChanged = Signal(str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, output_device: int | str | None = None) -> None:
        super().__init__()
        self.output_device = output_device
        self._audio: np.ndarray | None = None
        self._sample_rate = 44_100
        self._index = 0
        self._volume = 0.7
        self._stream: sd.OutputStream | None = None
        self._playing = False
        self._paused = False
        self._lock = threading.Lock()

    @property
    def duration(self) -> float:
        if self._audio is None:
            return 0.0
        return len(self._audio) / self._sample_rate

    @property
    def position(self) -> float:
        return self._index / self._sample_rate

    @property
    def state(self) -> str:
        if self._paused:
            return "paused"
        if self._playing:
            return "playing"
        return "stopped"

    def load(self, path: str | Path) -> None:
        self.stop()
        audio, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
        self._audio = np.asarray(audio, dtype=np.float32)
        self._sample_rate = int(sample_rate)
        self._index = 0

    def set_volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, float(value)))

    def play(self) -> None:
        if self._audio is None:
            self.failed.emit("재생할 녹음 파일이 없습니다.")
            return

        if self._paused and self._stream is not None:
            self._paused = False
            self._playing = True
            self.stateChanged.emit("playing")
            return

        if self._playing:
            return

        if self._index >= len(self._audio):
            self._index = 0

        try:
            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=self._audio.shape[1],
                dtype="float32",
                device=self.output_device,
                callback=self._callback,
                finished_callback=self._on_stream_finished,
            )
            self._playing = True
            self._paused = False
            self._stream.start()
            self.stateChanged.emit("playing")
        except Exception as exc:
            self._playing = False
            self._paused = False
            self.failed.emit(
                "오디오 출력 장치를 열 수 없습니다. 스피커 연결과 출력 설정을 확인해주세요.\n"
                f"원본 오류: {exc}"
            )

    def pause(self) -> None:
        if self._playing:
            self._paused = True
            self._playing = False
            self.stateChanged.emit("paused")

    def toggle(self) -> None:
        if self.state == "playing":
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        stream = self._stream
        self._stream = None
        self._playing = False
        self._paused = False
        self._index = 0
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self.stateChanged.emit("stopped")

    def _callback(self, outdata, frames, time_info, status) -> None:  # noqa: ANN001
        del time_info
        if status:
            print(f"[audio output] {status}")

        if self._audio is None or self._paused:
            outdata.fill(0)
            return

        with self._lock:
            start = self._index
            end = min(start + frames, len(self._audio))
            chunk = self._audio[start:end]
            outdata.fill(0)
            outdata[: len(chunk)] = chunk * self._volume
            self._index = end

        if end >= len(self._audio):
            raise sd.CallbackStop()

    def _on_stream_finished(self) -> None:
        completed = self._audio is not None and self._index >= len(self._audio)
        self._playing = False
        self._paused = False
        self._stream = None
        self.stateChanged.emit("stopped")
        if completed:
            self.finished.emit()
