from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import soundfile as sf

from core.gradient_selector import GradientSelector


@dataclass(frozen=True)
class AnalysisResult:
    loudness: float
    brightness: float
    roughness: float
    variability: float
    dbfs: float
    spectral_centroid_hz: float
    zero_crossing_rate: float
    spectral_flatness: float
    low_energy: float
    mid_energy: float
    high_energy: float
    day_night: str
    components: tuple[str, ...]
    gradient_index: int
    gradient_profile: str
    audio_fingerprint: int

    @property
    def image_index(self) -> int:
        """이전 UI가 사용하던 이름과의 호환용 별칭입니다."""
        return self.gradient_index

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["components"] = list(self.components)
        return data

    @classmethod
    def from_metadata(cls, data: Mapping[str, Any]) -> "AnalysisResult":
        features = data.get("features", data)
        bands = data.get("band_energy", {})
        return cls(
            loudness=float(features.get("loudness", 0.0)),
            brightness=float(features.get("brightness", 0.0)),
            roughness=float(features.get("roughness", 0.0)),
            variability=float(features.get("variability", 0.0)),
            dbfs=float(features.get("dbfs", 0.0)),
            spectral_centroid_hz=float(features.get("spectral_centroid_hz", 0.0)),
            zero_crossing_rate=float(features.get("zero_crossing_rate", 0.0)),
            spectral_flatness=float(features.get("spectral_flatness", 0.0)),
            low_energy=float(bands.get("low", 1 / 3)),
            mid_energy=float(bands.get("mid", 1 / 3)),
            high_energy=float(bands.get("high", 1 / 3)),
            day_night=str(data.get("day_night", "day")),
            components=tuple(data.get("components", ("a1", "b1", "c1"))),
            gradient_index=int(data.get("gradient_index", data.get("image_index", 1))),
            gradient_profile=str(data.get("gradient_profile", "pastel")),
            audio_fingerprint=int(data.get("audio_fingerprint", 0)),
        )


class SoundAnalyzer:
    """10초 녹음을 분석해 낮/밤, a·b·c 형태, 색 그라데이션을 결정합니다."""

    def __init__(
        self,
        settings: Mapping[str, Any] | None = None,
        gradient_selector: GradientSelector | None = None,
    ) -> None:
        self.settings = dict(settings or {})
        self.gradient_selector = gradient_selector or GradientSelector()

    def analyze(self, audio_path: str | Path) -> AnalysisResult:
        audio, sample_rate = sf.read(str(audio_path), always_2d=True, dtype="float64")
        mono = np.mean(audio, axis=1)
        if mono.size == 0:
            raise ValueError("녹음 파일에 오디오 샘플이 없습니다.")

        mono = mono[: int(sample_rate * 10)]
        mono = mono - np.mean(mono)
        eps = 1e-12
        rms = float(np.sqrt(np.mean(mono * mono) + eps))
        dbfs = 20.0 * math.log10(rms + eps)
        loudness = self._clip01((dbfs + 55.0) / 45.0)

        centroid = 0.0
        zcr = 0.0
        flatness = 0.0
        low_energy = mid_energy = high_energy = 1.0 / 3.0
        if dbfs < -58.0:
            brightness = 0.25
            roughness = 0.05
            variability = 0.05
        else:
            analysis_audio = mono[: int(sample_rate * 8)]
            window = np.hanning(len(analysis_audio))
            spectrum = np.abs(np.fft.rfft(analysis_audio * window))
            power = spectrum * spectrum
            freqs = np.fft.rfftfreq(len(analysis_audio), d=1.0 / sample_rate)
            centroid = float(np.sum(freqs * spectrum) / (np.sum(spectrum) + eps))

            low_cut = float(self.settings.get("low_band_hz", 300))
            high_cut = float(self.settings.get("high_band_hz", 2000))
            upper = min(10_000.0, sample_rate / 2.0)
            band_values = np.asarray([
                np.sum(power[(freqs >= 20.0) & (freqs < low_cut)]),
                np.sum(power[(freqs >= low_cut) & (freqs < high_cut)]),
                np.sum(power[(freqs >= high_cut) & (freqs <= upper)]),
            ], dtype="float64")
            band_values /= float(np.sum(band_values) + eps)
            low_energy, mid_energy, high_energy = map(float, band_values)

            centroid_norm = self._clip01(
                (math.log1p(max(centroid, 0.0)) - math.log1p(250.0))
                / (math.log1p(6000.0) - math.log1p(250.0))
            )
            balance = self._clip01((high_energy + 0.45 * mid_energy - 0.16) / 0.70)
            brightness = self._clip01(0.58 * centroid_norm + 0.42 * balance)

            signs = np.signbit(mono)
            zcr = float(np.mean(signs[1:] != signs[:-1])) if len(mono) > 1 else 0.0
            active_power = power[(freqs >= 20.0) & (freqs <= upper)]
            geometric_mean = float(np.exp(np.mean(np.log(active_power + eps))))
            arithmetic_mean = float(np.mean(active_power + eps))
            flatness = geometric_mean / arithmetic_mean
            roughness = self._clip01(0.55 * (flatness / 0.35) + 0.45 * (zcr / 0.20))
            variability = self._variability(mono, sample_rate, eps)

        fingerprint = self._fingerprint(mono)
        day_night = (
            "day"
            if brightness >= float(self.settings.get("day_brightness_threshold", 0.52))
            else "night"
        )
        activity = 0.25 * loudness + 0.35 * roughness + 0.40 * variability
        band_map = {"a": high_energy, "b": mid_energy, "c": low_energy}
        candidate_scores = {
            f"{band}1": energy * max(0.05, 1.0 - activity)
            for band, energy in band_map.items()
        }
        candidate_scores.update(
            {
                f"{band}2": energy * max(0.05, activity)
                for band, energy in band_map.items()
            }
        )
        component_count = self._component_count(loudness)
        selected = sorted(
            candidate_scores,
            key=lambda component: (-candidate_scores[component], component),
        )[:component_count]
        component_order = {name: index for index, name in enumerate(
            ("a1", "a2", "b1", "b2", "c1", "c2")
        )}
        components = tuple(sorted(selected, key=component_order.get))
        gradient = self.gradient_selector.select(
            loudness=loudness,
            brightness=brightness,
            roughness=roughness,
            variability=variability,
            fingerprint=fingerprint,
            low_energy=low_energy,
            high_energy=high_energy,
        )

        return AnalysisResult(
            loudness=loudness,
            brightness=brightness,
            roughness=roughness,
            variability=variability,
            dbfs=dbfs,
            spectral_centroid_hz=centroid,
            zero_crossing_rate=zcr,
            spectral_flatness=flatness,
            low_energy=low_energy,
            mid_energy=mid_energy,
            high_energy=high_energy,
            day_night=day_night,
            components=components,
            gradient_index=gradient.index,
            gradient_profile=gradient.profile,
            audio_fingerprint=fingerprint,
        )

    @staticmethod
    def _variability(mono: np.ndarray, sample_rate: int, eps: float) -> float:
        frame_len = max(256, int(sample_rate * 0.05))
        hop = max(128, frame_len // 2)
        frame_rms = [
            float(np.sqrt(np.mean(mono[start : start + frame_len] ** 2) + eps))
            for start in range(0, max(1, len(mono) - frame_len + 1), hop)
            if len(mono[start : start + frame_len]) == frame_len
        ]
        if len(frame_rms) < 2:
            return 0.0
        values = np.asarray(frame_rms)
        coefficient = float(np.std(values) / (np.mean(values) + eps))
        return SoundAnalyzer._clip01(coefficient / 1.35)

    @staticmethod
    def _fingerprint(mono: np.ndarray) -> int:
        step = max(1, len(mono) // 4096)
        samples = np.clip(mono[::step], -1.0, 1.0)
        pcm = np.round(samples * 32767.0).astype("<i2").tobytes()
        return int.from_bytes(hashlib.blake2b(pcm, digest_size=8).digest(), "big")

    def _component_count(self, loudness: float) -> int:
        thresholds = self.settings.get(
            "layer_count_thresholds",
            (0.20, 0.40, 0.62, 0.78, 0.90),
        )
        values = sorted(float(value) for value in thresholds)
        return min(6, 1 + sum(loudness >= value for value in values[:5]))

    @staticmethod
    def _clip01(value: float) -> float:
        return float(np.clip(value, 0.0, 1.0))
