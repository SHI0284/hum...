from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter

from core.analyzer import AnalysisResult
from core.config import DEVICE_GRAPHICS_DIR, GENERATED_RESULTS_DIR


class ImageComposer:
    """검정 캔버스에 c → b → a → 그라데이션 순으로 최종 PNG를 만듭니다."""

    def __init__(
        self,
        graphics_dir: str | Path = DEVICE_GRAPHICS_DIR,
        output_dir: str | Path = GENERATED_RESULTS_DIR,
        canvas_size: int = 720,
        graphic_family: str = "A",
        gradient_opacity: float = 0.16,
    ) -> None:
        self.graphics_dir = Path(graphics_dir)
        self.output_dir = Path(output_dir)
        self.canvas_size = int(canvas_size)
        self.graphic_family = graphic_family.casefold()
        self.gradient_opacity = min(0.35, max(0.05, float(gradient_opacity)))
        self._png_files = list(self.graphics_dir.rglob("*.png"))

    def compose(self, analysis: AnalysisResult, audio_path: str | Path) -> Path:
        audio_path = Path(audio_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{audio_path.stem}_artwork.png"
        canvas = Image.new("RGBA", (self.canvas_size, self.canvas_size), (0, 0, 0, 255))
        stack = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        band_energy = {
            "a": analysis.high_energy,
            "b": analysis.mid_energy,
            "c": analysis.low_energy,
        }
        scale = 0.84 + 0.24 * analysis.loudness

        # loudness에 따라 분석기가 고른 1~6개의 PNG만 사용합니다.
        layer_order = {"c": 0, "b": 1, "a": 2}
        selected_components = sorted(
            analysis.components,
            key=lambda component: (layer_order[component[0]], component[1]),
        )
        for component in selected_components:
            band, selected_variant = component[0], component[1]
            layer_path = self._find_layer(band, selected_variant, analysis.day_night)
            with Image.open(layer_path) as source:
                layer = self._fit_and_scale(source.convert("RGBA"), scale)
            band_opacity = 0.80 + 0.20 * min(1.0, band_energy[band] * 2.0)
            layer.putalpha(
                layer.getchannel("A").point(
                    lambda alpha, value=band_opacity: round(alpha * value)
                )
            )
            stack = Image.alpha_composite(stack, layer)

        gradient_path = self.graphics_dir / "gradients" / f"{analysis.gradient_index}.png"
        if not gradient_path.exists():
            raise FileNotFoundError(f"그라데이션 레이어를 찾을 수 없습니다: {gradient_path}")
        with Image.open(gradient_path) as source:
            gradient = source.convert("RGB").resize(
                canvas.size, Image.Resampling.LANCZOS
            )

        # 그라데이션은 사각 배경 전체가 아니라 그래픽의 alpha 영역에만 입힙니다.
        # multiply는 유리 질감의 명암을 보존하면서 색만 자연스럽게 바꿉니다.
        graphic_rgb = stack.convert("RGB")
        tinted_rgb = ImageChops.multiply(graphic_rgb, gradient)
        color_strength = min(
            0.86,
            0.54 + self.gradient_opacity + 0.08 * analysis.roughness,
        )
        tinted_rgb = Image.blend(graphic_rgb, tinted_rgb, color_strength)
        tinted_rgb = ImageEnhance.Color(tinted_rgb).enhance(1.24)
        tinted_rgb = ImageEnhance.Brightness(tinted_rgb).enhance(1.42)
        tinted_rgb = ImageEnhance.Contrast(tinted_rgb).enhance(
            1.04 + 0.08 * analysis.roughness
        )
        colored = tinted_rgb.convert("RGBA")
        colored.putalpha(stack.getchannel("A"))

        glow_radius = 3.0 + 6.0 * analysis.roughness
        glow = colored.filter(ImageFilter.GaussianBlur(glow_radius))
        glow_strength = 0.09 + 0.10 * analysis.loudness
        glow.putalpha(
            glow.getchannel("A").point(
                lambda alpha: round(alpha * glow_strength)
            )
        )
        canvas = Image.alpha_composite(canvas, glow)
        canvas = Image.alpha_composite(canvas, colored)

        temporary = output_path.with_suffix(".tmp.png")
        canvas.convert("RGB").save(temporary, "PNG", optimize=True)
        os.replace(temporary, output_path)
        return output_path

    def _find_layer(self, band: str, variant: str, day_night: str) -> Path:
        suffix = "d" if day_night == "day" else "n"
        expected = f"{band}{variant}_{suffix}"

        # Windows 전달본은 ZIP 해제 시 한글 폴더명이 깨지는 문제를 피하기 위해
        # assets/device_graphics/layers/A/day|night 영문 경로를 우선 사용합니다.
        family = self.graphic_family.upper()
        ascii_path = (
            self.graphics_dir
            / "layers"
            / family
            / ("day" if day_night == "day" else "night")
            / f"{family}{band}{variant}_{suffix.upper()}.png"
        )
        if ascii_path.is_file():
            return ascii_path

        # 앱을 시작한 뒤 에셋이 복사된 경우도 찾을 수 있도록 다시 검색합니다.
        self._png_files = list(self.graphics_dir.rglob("*.png"))
        candidates = [
            path
            for path in self._png_files
            if "gradients" not in {part.casefold() for part in path.parts}
            and path.stem.casefold().endswith(expected)
        ]
        if not candidates:
            raise FileNotFoundError(
                f"{day_night} {band}{variant} 그래픽 레이어를 "
                f"{self.graphics_dir}에서 찾을 수 없습니다. "
                f"예상 경로: {ascii_path}"
            )
        preferred = [
            path
            for path in candidates
            if self.graphic_family in {part.casefold() for part in path.parts}
        ]
        return sorted(preferred or candidates, key=lambda path: str(path).casefold())[0]

    def _fit_and_scale(self, image: Image.Image, scale: float) -> Image.Image:
        fitted = Image.new("RGBA", (self.canvas_size, self.canvas_size), (0, 0, 0, 0))
        image.thumbnail((self.canvas_size, self.canvas_size), Image.Resampling.LANCZOS)
        fitted.alpha_composite(
            image,
            ((self.canvas_size - image.width) // 2, (self.canvas_size - image.height) // 2),
        )
        scaled_size = max(1, round(self.canvas_size * scale))
        scaled = fitted.resize((scaled_size, scaled_size), Image.Resampling.LANCZOS)
        if scaled_size >= self.canvas_size:
            offset = (scaled_size - self.canvas_size) // 2
            return scaled.crop((offset, offset, offset + self.canvas_size, offset + self.canvas_size))
        result = Image.new("RGBA", fitted.size, (0, 0, 0, 0))
        result.alpha_composite(
            scaled,
            ((self.canvas_size - scaled_size) // 2, (self.canvas_size - scaled_size) // 2),
        )
        return result
