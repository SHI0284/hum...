from __future__ import annotations

import json
import colorsys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import GRADIENT_MANIFEST_PATH


@dataclass(frozen=True)
class GradientSelection:
    index: int
    profile: str


class GradientSelector:
    """실제 그라데이션 색 통계를 소리 특성의 목표 색감과 매칭합니다."""

    def __init__(self, manifest_path: str | Path = GRADIENT_MANIFEST_PATH) -> None:
        self.manifest_path = Path(manifest_path)
        self.items = self._load_items()
        self.ranges = {
            key: (
                min(float(item[key]) for item in self.items),
                max(float(item[key]) for item in self.items),
            )
            for key in ("brightness", "coolness", "saturation", "contrast")
        }

    def select(
        self,
        *,
        loudness: float,
        brightness: float,
        roughness: float,
        variability: float,
        fingerprint: int,
        low_energy: float = 1 / 3,
        high_energy: float = 1 / 3,
    ) -> GradientSelection:
        del fingerprint  # 같은 분석값은 항상 같은 색이 되도록 랜덤 선택에 쓰지 않습니다.
        profile, target = self._target(
            loudness=loudness,
            brightness=brightness,
            roughness=roughness,
            variability=variability,
            low_energy=low_energy,
            high_energy=high_energy,
        )
        scored: list[tuple[float, int]] = []
        for item in self.items:
            hue_distance = abs(float(item["hue"]) - target["hue"])
            hue_distance = min(hue_distance, 1.0 - hue_distance)
            score = (
                1.20 * abs(self._normal(item, "brightness") - target["brightness"])
                + 1.10 * abs(self._normal(item, "coolness") - target["coolness"])
                + 0.90 * abs(self._normal(item, "saturation") - target["saturation"])
                + 1.25 * abs(self._normal(item, "contrast") - target["contrast"])
                + 1.05 * hue_distance
            )
            scored.append((score, int(item["index"])))

        scored.sort(key=lambda pair: (pair[0], pair[1]))
        candidates = scored[: min(6, len(scored))]
        # 같은 색감 프로필 안에서도 세부 분석값 구간으로 후보를 나눕니다.
        # 오디오 파일명/랜덤값이 아니라 네 특성 자체만 사용하므로 재현 가능합니다.
        feature_code = (
            round(loudness * 31) * 3
            + round(brightness * 31) * 5
            + round(roughness * 31) * 7
            + round(variability * 31) * 11
        )
        index = candidates[feature_code % len(candidates)][1]
        return GradientSelection(index=index, profile=profile)

    def _load_items(self) -> list[dict[str, Any]]:
        if not self.manifest_path.exists():
            raise FileNotFoundError(
                f"그라데이션 매니페스트가 없습니다: {self.manifest_path}"
            )
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        items = data.get("items", [])
        if not items:
            raise ValueError("gradient_manifest.json에 그라데이션 정보가 없습니다.")
        for item in items:
            if "hue" not in item:
                red, green, blue = [float(value) / 255.0 for value in item["average_rgb"]]
                item["hue"] = colorsys.rgb_to_hsv(red, green, blue)[0]
        return items

    def _normal(self, item: dict[str, Any], key: str) -> float:
        minimum, maximum = self.ranges[key]
        if maximum <= minimum:
            return 0.5
        return (float(item[key]) - minimum) / (maximum - minimum)

    @staticmethod
    def _target(
        *,
        loudness: float,
        brightness: float,
        roughness: float,
        variability: float,
        low_energy: float,
        high_energy: float,
    ) -> tuple[str, dict[str, float]]:
        activity = 0.20 * loudness + 0.40 * roughness + 0.40 * variability
        spectral_tilt = high_energy / max(1e-9, high_energy + low_energy)
        tone = min(1.0, max(0.0, 0.70 * brightness + 0.30 * spectral_tilt))
        if variability >= 0.62 or roughness >= 0.55 or activity >= 0.62:
            profile = "contrast"
        elif tone >= 0.58:
            profile = "cool_bright"
        elif activity <= 0.32:
            profile = "pastel"
        else:
            profile = "warm_dark"

        target = {
            "brightness": 0.25 + 0.62 * brightness + 0.12 * loudness,
            "coolness": 0.10 + 0.80 * tone,
            "saturation": 0.15 + 0.70 * (0.55 * roughness + 0.45 * loudness),
            "contrast": 0.05 + 0.85 * (0.55 * roughness + 0.45 * variability),
            "hue": (0.06 + 0.58 * tone + 0.12 * roughness) % 1.0,
        }
        if profile == "pastel":
            target["brightness"] = max(target["brightness"], 0.72)
            target["saturation"] *= 0.58
            target["contrast"] *= 0.52
        elif profile == "contrast":
            target["saturation"] = max(target["saturation"], 0.70)
            target["contrast"] = max(target["contrast"], 0.75)
        elif profile == "cool_bright":
            target["brightness"] = max(target["brightness"], 0.66)
            target["coolness"] = max(target["coolness"], 0.72)
        else:
            target["brightness"] = min(target["brightness"], 0.52)
            target["coolness"] = min(target["coolness"], 0.38)
            target["hue"] = 0.04 + 0.14 * tone
        return profile, {key: min(1.0, max(0.0, value)) for key, value in target.items()}
