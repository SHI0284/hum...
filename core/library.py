from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.analyzer import AnalysisResult
from core.config import GENERATED_RESULTS_DIR, PROJECT_ROOT


@dataclass(frozen=True)
class LibraryEntry:
    path: Path
    title: str
    duration_seconds: float
    image_index: int | None
    artwork_path: Path | None
    favorite: bool
    kept: bool
    features: dict[str, float]
    components: tuple[str, ...]
    color: str
    day_night: str
    gradient_profile: str
    band_energy: dict[str, float]
    audio_fingerprint: int

    def analysis_result(self) -> AnalysisResult:
        return AnalysisResult.from_metadata({
            "features": self.features,
            "band_energy": self.band_energy,
            "day_night": self.day_night,
            "components": self.components,
            "gradient_index": self.image_index or 1,
            "gradient_profile": self.gradient_profile,
            "audio_fingerprint": self.audio_fingerprint,
        })


class LibraryStore:
    def __init__(
        self,
        recordings_dir: str | Path = "recordings",
        metadata_path: str | Path = "recordings/library.json",
    ) -> None:
        recordings = Path(recordings_dir)
        metadata = Path(metadata_path)
        self.recordings_dir = recordings if recordings.is_absolute() else PROJECT_ROOT / recordings
        self.metadata_path = metadata if metadata.is_absolute() else PROJECT_ROOT / metadata
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

    def register(
        self,
        path: Path,
        duration_seconds: float,
        analysis: AnalysisResult,
        artwork_path: Path,
    ) -> None:
        metadata = self._read()
        current = metadata.get(path.name, {})
        try:
            stored_artwork = str(artwork_path.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError:
            stored_artwork = str(artwork_path.resolve())
        current.update({
            "analysis_schema": 2,
            "duration_seconds": duration_seconds,
            "image_index": analysis.gradient_index,
            "gradient_index": analysis.gradient_index,
            "gradient_profile": analysis.gradient_profile,
            "day_night": analysis.day_night,
            "audio_fingerprint": analysis.audio_fingerprint,
            "artwork_path": stored_artwork,
            "favorite": bool(current.get("favorite", False)),
            "kept": bool(current.get("kept", False)),
            "features": {
                "loudness": analysis.loudness,
                "brightness": analysis.brightness,
                "roughness": analysis.roughness,
                "variability": analysis.variability,
                "dbfs": analysis.dbfs,
                "spectral_centroid_hz": analysis.spectral_centroid_hz,
                "zero_crossing_rate": analysis.zero_crossing_rate,
                "spectral_flatness": analysis.spectral_flatness,
            },
            "band_energy": {
                "low": analysis.low_energy,
                "mid": analysis.mid_energy,
                "high": analysis.high_energy,
            },
            "components": list(analysis.components),
        })
        metadata[path.name] = current
        self._write(metadata)

    def entries(
        self,
        favorites_only: bool = False,
        sort_mode: str = "time",
    ) -> list[LibraryEntry]:
        metadata = self._read()
        files = sorted(
            self.recordings_dir.glob("*.wav"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        result: list[LibraryEntry] = []
        for path in files:
            info = metadata.get(path.name, {})
            favorite = bool(info.get("favorite", False))
            if favorites_only and not favorite:
                continue
            artwork_path = self._resolve_artwork(info.get("artwork_path"))
            modified = datetime.fromtimestamp(path.stat().st_mtime)
            result.append(LibraryEntry(
                path=path,
                title=modified.strftime("%y.%m.%d. %H:%M"),
                duration_seconds=float(info.get("duration_seconds", 10.0)),
                image_index=(
                    int(
                        info["gradient_index"]
                        if "gradient_index" in info
                        else info["image_index"]
                    )
                    if "image_index" in info or "gradient_index" in info
                    else None
                ),
                artwork_path=artwork_path,
                favorite=favorite,
                kept=bool(info.get("kept", False)),
                features={key: float(value) for key, value in info.get("features", {}).items()},
                components=tuple(info.get("components", [])),
                color=str(info.get("color", "#FFE9B8")),
                day_night=str(info.get("day_night", "day")),
                gradient_profile=str(info.get("gradient_profile", "pastel")),
                band_energy={
                    key: float(value) for key, value in info.get("band_energy", {}).items()
                },
                audio_fingerprint=int(info.get("audio_fingerprint", 0)),
            ))
        if sort_mode == "favorite":
            result.sort(
                key=lambda entry: (
                    not entry.favorite,
                    -entry.path.stat().st_mtime,
                )
            )
        return result

    def set_favorite(self, path: Path, favorite: bool) -> None:
        self._patch(path, {"favorite": favorite})

    def set_kept(self, path: Path, kept: bool = True) -> None:
        self._patch(path, {"kept": kept})

    def set_color(self, path: Path, color: str) -> None:
        self._patch(path, {"color": color})

    def keep_only_for_day(self, path: Path, color: str) -> list[Path]:
        """Keep one recording and delete every other recording from its date."""
        target_day = self.recording_day(path)
        self._patch(path, {"kept": True, "color": color})
        deleted: list[Path] = []
        for entry in self.entries():
            if entry.path != path and self.recording_day(entry.path) == target_day:
                deleted.append(entry.path)
                self.delete(entry.path)
        return deleted

    def has_kept_recording_for_day(self, target_day: date | None = None) -> bool:
        wanted = target_day or date.today()
        return any(
            entry.kept and self.recording_day(entry.path) == wanted
            for entry in self.entries()
        )

    @staticmethod
    def recording_day(path: Path) -> date:
        return datetime.fromtimestamp(path.stat().st_mtime).date()

    def delete(self, path: Path) -> None:
        metadata = self._read()
        info = metadata.pop(path.name, {})
        artwork = self._resolve_artwork(info.get("artwork_path"))
        if artwork is not None:
            try:
                artwork.resolve().relative_to(GENERATED_RESULTS_DIR.resolve())
                artwork.unlink(missing_ok=True)
            except ValueError:
                pass
        path.unlink(missing_ok=True)
        self._write(metadata)

    def _patch(self, path: Path, patch: dict[str, Any]) -> None:
        metadata = self._read()
        info = metadata.get(path.name, {})
        info.update(patch)
        metadata[path.name] = info
        self._write(metadata)

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.metadata_path.exists():
            return {}
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, metadata: dict[str, dict[str, Any]]) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def register_raw(self, path: Path, duration_seconds: float) -> None:
        metadata = self._read()
        current = metadata.get(path.name, {})
        current.update({
            "duration_seconds": duration_seconds,
            "favorite": bool(current.get("favorite", False)),
            "kept": bool(current.get("kept", False)),
        })
        metadata[path.name] = current
        self._write(metadata)

    @staticmethod
    def _resolve_artwork(value: Any) -> Path | None:
        if not value:
            return None
        path = Path(str(value))
        path = path if path.is_absolute() else PROJECT_ROOT / path
        return path if path.exists() else None
