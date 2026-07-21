from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
ASSETS_DIR = PROJECT_ROOT / "assets"
DEVICE_GRAPHICS_DIR = ASSETS_DIR / "device_graphics"
GRADIENTS_DIR = DEVICE_GRAPHICS_DIR / "gradients"
GRADIENT_MANIFEST_PATH = GRADIENTS_DIR / "gradient_manifest.json"
GENERATED_RESULTS_DIR = ASSETS_DIR / "generated_results"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)
