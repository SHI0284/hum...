from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFontDatabase


MONO_CANDIDATES = [
    "Geist Mono",
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Monospace",
]
KO_CANDIDATES = [
    "Pretendard",
    "Pretendard Variable",
    "Noto Sans CJK KR",
    "Noto Sans KR",
    "NanumGothic",
    "Sans Serif",
]


def _pick(candidates: list[str]) -> str:
    families = set(QFontDatabase.families())
    return next((name for name in candidates if name in families), candidates[-1])


EN_FONT = "Monospace"
KO_FONT = "Sans Serif"


def load_app_fonts() -> None:
    global EN_FONT, KO_FONT
    project_fonts = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    for path in project_fonts.glob("*.*"):
        if path.suffix.lower() in {".ttf", ".otf"}:
            QFontDatabase.addApplicationFont(str(path))
    EN_FONT = _pick(MONO_CANDIDATES)
    KO_FONT = _pick(KO_CANDIDATES)
