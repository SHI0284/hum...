from __future__ import annotations

import colorsys
import json
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageStat

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRADIENTS_DIR = PROJECT_ROOT / "assets" / "device_graphics" / "gradients"


def descriptor(path: Path) -> dict[str, object]:
    image = Image.open(path).convert("RGB").resize((32, 32), Image.Resampling.BILINEAR)
    pixels = list(image.getdata())
    mean = ImageStat.Stat(image).mean
    hsv = [colorsys.rgb_to_hsv(r / 255, g / 255, b / 255) for r, g, b in pixels]
    brightness_values = [value for _, _, value in hsv]
    saturation_values = [saturation for _, saturation, _ in hsv]
    brightness = statistics.fmean(brightness_values)
    contrast = min(1.0, statistics.pstdev(brightness_values) * 2.6)
    coolness = min(1.0, max(0.0, 0.5 + (mean[2] - mean[0]) / 255.0 / 2.0))
    return {
        "index": int(path.stem),
        "average_rgb": [round(channel) for channel in mean],
        "hue": round(colorsys.rgb_to_hsv(*(channel / 255 for channel in mean))[0], 5),
        "brightness": round(brightness, 5),
        "saturation": round(statistics.fmean(saturation_values), 5),
        "contrast": round(contrast, 5),
        "coolness": round(coolness, 5),
    }


def main() -> None:
    items = [descriptor(path) for path in GRADIENTS_DIR.glob("*.png") if path.stem.isdigit()]
    items.sort(key=lambda item: int(item["index"]))
    output = GRADIENTS_DIR / "gradient_manifest.json"
    output.write_text(
        json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(items)} gradients -> {output}")


if __name__ == "__main__":
    sys.exit(main())
