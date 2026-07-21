from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPointF, QUrl, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.analyzer import AnalysisResult, SoundAnalyzer
from core.config import (
    DEVICE_GRAPHICS_DIR,
    GENERATED_RESULTS_DIR,
    GRADIENT_MANIFEST_PATH,
    PROJECT_ROOT,
    load_config,
)
from core.gradient_selector import GradientSelector
from core.image_composer import ImageComposer
from core.library import LibraryEntry, LibraryStore
from core.player import AudioPlayer
from core.recorder import Recorder, RecordingResult
from ui.fonts import load_app_fonts
from ui.screens import (
    ArchiveScreen,
    BootScreen,
    HomeScreen,
    ProcessingScreen,
    RecordingScreen,
    ResultScreen,
    SaveDialog,
)


@dataclass(frozen=True)
class HumResult:
    recording: RecordingResult
    analysis: AnalysisResult
    artwork_path: Path


class RecordingWorker(QObject):
    started = Signal()
    levelChanged = Signal(float)
    progressChanged = Signal(float)
    recorded = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        recorder: Recorder,
        duration_seconds: float,
    ) -> None:
        super().__init__()
        self.recorder = recorder
        self.duration_seconds = duration_seconds
        self.busy = False

    def start(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.started.emit()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            recording = self.recorder.record(
                self.duration_seconds,
                level_callback=self.levelChanged.emit,
                progress_callback=self.progressChanged.emit,
            )
            self.busy = False
            self.recorded.emit(recording)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.busy = False


class AnalysisWorker(QObject):
    finished = Signal(object, object, object)
    failed = Signal(str)

    def __init__(self, analyzer: SoundAnalyzer, composer: ImageComposer) -> None:
        super().__init__()
        self.analyzer = analyzer
        self.composer = composer
        self.busy = False

    def start(self, entry: LibraryEntry) -> None:
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._run, args=(entry,), daemon=True).start()

    def _run(self, entry: LibraryEntry) -> None:
        try:
            analysis = self.analyzer.analyze(entry.path)
            artwork_path = self.composer.compose(analysis, entry.path)
            self.finished.emit(entry, analysis, artwork_path)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.busy = False


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.developer_mode = bool(self.config.get("developer_mode", False))
        self.archive_sort_mode = "time"
        self.setWindowTitle("Before words, there is hum.")
        self.setStyleSheet("QMainWindow { background: #eeeeee; }")

        size = int(self.config.get("window_size", 720))
        if not self.config.get("fullscreen", True):
            self.resize(size, size)

        self.store = LibraryStore()
        self.current_result: HumResult | None = None
        self.pending_result: HumResult | None = None
        self.processing_minimum_done = False
        self.pending_analysis_color: str | None = None
        self.current_archive_entry: LibraryEntry | None = None
        self.swipe_start: QPointF | None = None
        self.swipe_last: QPointF | None = None
        self.row_swipe = False
        self.exit_video_playing = False
        self.force_close = False
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self.show_today_artwork)

        self._build_ui()

        recorder = Recorder(
            sample_rate=int(self.config.get("sample_rate", 44_100)),
            channels=int(self.config.get("channels", 1)),
            input_device=self.config.get("audio_input_device"),
            max_recordings=int(self.config.get("max_recordings", 30)),
        )
        self.worker = RecordingWorker(
            recorder,
            float(self.config.get("record_seconds", 5)),
        )
        self.worker.started.connect(self._on_recording_started)
        self.worker.levelChanged.connect(self.recording_screen.push_level)
        self.worker.progressChanged.connect(self.recording_screen.set_progress)
        self.worker.recorded.connect(self._on_recording_finished)
        self.worker.failed.connect(self._on_recording_failed)
        graphics_dir = self._config_path("device_graphics_dir", DEVICE_GRAPHICS_DIR)
        output_dir = self._config_path("generated_results_dir", GENERATED_RESULTS_DIR)
        self.analysis_worker = AnalysisWorker(
            SoundAnalyzer(
                self.config.get("analysis", {}),
                GradientSelector(
                    self._config_path("gradient_manifest", GRADIENT_MANIFEST_PATH)
                ),
            ),
            ImageComposer(
                graphics_dir=graphics_dir,
                output_dir=output_dir,
                canvas_size=int(self.config.get("composer_canvas_size", 720)),
                graphic_family=str(self.config.get("composer_graphic_family", "A")),
                gradient_opacity=float(self.config.get("composer_gradient_opacity", 0.16)),
            ),
        )
        self.analysis_worker.finished.connect(self._on_analysis_finished)
        self.analysis_worker.failed.connect(self._on_analysis_failed)

        self.player = AudioPlayer(self.config.get("audio_output_device"))
        self.player.set_volume(float(self.config.get("initial_volume", 0.7)))
        self.player.stateChanged.connect(self._on_player_state)
        self.player.finished.connect(self._on_player_finished)
        self.player.failed.connect(self._show_error)
        self.playback_ui_timer = QTimer(self)
        self.playback_ui_timer.setInterval(50)
        self.playback_ui_timer.timeout.connect(
            lambda: self.archive_screen.set_playback_position(
                self.player.position, self.player.duration
            )
        )
        self.playback_ui_timer.start()

        self.sensor = None
        self._connect_ui()
        QApplication.instance().installEventFilter(self)
        self._reset_idle_timer()
        self._setup_sensor()

        self._play_device_video("hum_device_start.mp4", self.show_boot_sequence)

    def _config_path(self, key: str, default: Path) -> Path:
        value = Path(str(self.config.get(key, default)))
        return value if value.is_absolute() else PROJECT_ROOT / value

    def _build_ui(self) -> None:
        self.boot_screen = BootScreen()
        self.home_screen = HomeScreen()
        self.recording_screen = RecordingScreen()
        self.processing_screen = ProcessingScreen()
        self.result_screen = ResultScreen(
            bool(self.config.get("show_feature_values", True))
        )
        self.archive_screen = ArchiveScreen()
        self.video_screen = QVideoWidget()
        self.video_screen.setStyleSheet("background: #000000;")
        self.video_player = QMediaPlayer(self)
        self.video_audio = QAudioOutput(self)
        self.video_player.setAudioOutput(self.video_audio)
        self.video_player.setVideoOutput(self.video_screen)
        self.video_player.mediaStatusChanged.connect(self._on_video_status)
        self.video_player.errorOccurred.connect(self._on_video_error)
        self.video_finished_callback = None

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: #000000;")
        for screen in (
            self.video_screen,
            self.boot_screen,
            self.home_screen,
            self.recording_screen,
            self.processing_screen,
            self.result_screen,
            self.archive_screen,
        ):
            screen.setAttribute(Qt.WA_AcceptTouchEvents, True)
            self.stack.addWidget(screen)

        horizontal = QHBoxLayout()
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.addStretch(1)
        horizontal.addWidget(self.stack)
        horizontal.addStretch(1)

        vertical = QVBoxLayout()
        vertical.setContentsMargins(0, 0, 0, 0)
        vertical.addStretch(1)
        vertical.addLayout(horizontal)
        vertical.addStretch(1)

        host = QWidget()
        host.setStyleSheet("background: #eeeeee;")
        host.setLayout(vertical)
        self.setCentralWidget(host)

    def _play_device_video(self, filename: str, finished_callback) -> None:
        path = PROJECT_ROOT / "assets" / "video" / filename
        self.video_finished_callback = finished_callback
        if not path.is_file():
            QTimer.singleShot(0, finished_callback)
            return
        self.stack.setCurrentWidget(self.video_screen)
        self.video_player.setSource(QUrl.fromLocalFile(str(path)))
        self.video_player.play()

    def _on_video_status(self, status) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        callback = self.video_finished_callback
        self.video_finished_callback = None
        if callback is not None:
            QTimer.singleShot(0, callback)

    def _on_video_error(self, error, message: str) -> None:
        del error
        if message:
            print(f"[video] {message}")
        callback = self.video_finished_callback
        self.video_finished_callback = None
        if callback is not None:
            QTimer.singleShot(0, callback)

    def show_boot_sequence(self) -> None:
        """Show the original logo/message intro after the device-start video."""
        self.boot_screen.restart()
        self.stack.setCurrentWidget(self.boot_screen)
        boot_ms = max(
            0,
            round(float(self.config.get("boot_seconds", 6.6)) * 1000),
        )
        QTimer.singleShot(boot_ms, self.show_home)

    def _connect_ui(self) -> None:
        self.home_screen.recordRequested.connect(self.show_recording)
        self.home_screen.archiveRequested.connect(self.show_recording)
        self.home_screen.volumeChanged.connect(self.player.set_volume)

        self.recording_screen.startRequested.connect(self.start_recording)
        self.recording_screen.previousRequested.connect(self.show_home)
        self.recording_screen.nextRequested.connect(self.show_archive)
        self.recording_screen.recordingsRequested.connect(self.show_archive)
        self.recording_screen.continueRequested.connect(self.continue_recording)
        self.recording_screen.volumeChanged.connect(self.player.set_volume)

        self.result_screen.playRequested.connect(self.toggle_current_playback)
        self.result_screen.recordRequested.connect(self.show_recording)
        self.result_screen.saveRequested.connect(self.save_current_hum)
        self.result_screen.archiveRequested.connect(self.show_archive)
        self.result_screen.volumeChanged.connect(self.player.set_volume)
        self.result_screen.previousRequested.connect(self.show_archive)

        self.archive_screen.backRequested.connect(self.show_recording)
        self.archive_screen.playRequested.connect(self.play_archive_entry)
        self.archive_screen.favoriteRequested.connect(self.toggle_favorite)
        self.archive_screen.deleteRequested.connect(self.delete_archive_entry)
        self.archive_screen.analyzeRequested.connect(self.analyze_archive_entry)
        self.archive_screen.colorAnalyzeRequested.connect(self.analyze_archive_entry)
        self.archive_screen.sortRequested.connect(self.set_archive_sort_mode)
        self.archive_screen.previousRequested.connect(self.show_recording)
        self.archive_screen.nextRequested.connect(self.show_today_artwork)
        self.archive_screen.volumeChanged.connect(self.player.set_volume)

    def _setup_sensor(self) -> None:
        if not self.config.get("sensor_enabled", False):
            print("[sensor] disabled")
            return
        try:
            from gpiozero import Button

            pin = int(self.config.get("sensor_gpio_pin", 17))
            self.sensor = Button(
                pin,
                pull_up=bool(self.config.get("sensor_pull_up", True)),
                bounce_time=float(self.config.get("sensor_bounce_seconds", 0.3)),
            )
            self.sensor.when_pressed = lambda: QTimer.singleShot(0, self.start_recording)
            print(f"[sensor] GPIO {pin} ready")
        except Exception as exc:
            print(f"[sensor] setup failed: {exc}")

    def resizeEvent(self, event) -> None:  # noqa: N802
        side = max(320, min(self.width(), self.height()))
        self.stack.setFixedSize(side, side)
        super().resizeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Space, Qt.Key_R):
            self.start_recording()
            return
        if event.key() == Qt.Key_A:
            self.show_archive()
            return
        if event.key() == Qt.Key_Escape:
            if self.stack.currentWidget() not in (self.home_screen, self.boot_screen):
                self.show_home()
            else:
                self.close()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802, ANN001
        event_type = event.type()
        if event_type in (
            QEvent.MouseButtonPress,
            QEvent.TouchBegin,
            QEvent.KeyPress,
        ):
            self._reset_idle_timer()
        if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self.swipe_start = QPointF(event.globalPosition())
            self.swipe_last = self.swipe_start
            target = watched
            self.row_swipe = False
            while target is not None:
                if target.__class__.__name__ == "ArchiveRow":
                    self.row_swipe = True
                    break
                target = target.parent() if hasattr(target, "parent") else None
        elif event_type == QEvent.MouseMove and self.swipe_start is not None:
            self.swipe_last = QPointF(event.globalPosition())
        elif event_type == QEvent.MouseButtonRelease and self.swipe_start is not None:
            end = QPointF(event.globalPosition())
            start = self.swipe_start
            self.swipe_start = None
            self.swipe_last = None
            row_swipe = self.row_swipe
            self.row_swipe = False
            if not row_swipe and self._handle_page_swipe(end - start):
                return True
        elif event_type in (QEvent.TouchBegin, QEvent.TouchUpdate):
            points = event.points()
            if points:
                position = QPointF(points[0].globalPosition())
                if event_type == QEvent.TouchBegin:
                    self.swipe_start = position
                self.swipe_last = position
        elif event_type == QEvent.TouchEnd and self.swipe_start is not None:
            end = self.swipe_last or self.swipe_start
            start = self.swipe_start
            self.swipe_start = None
            self.swipe_last = None
            if self._handle_page_swipe(end - start):
                return True
        return super().eventFilter(watched, event)

    def _reset_idle_timer(self) -> None:
        seconds = float(self.config.get("idle_exhibition_seconds", 600))
        self.idle_timer.start(max(1, round(seconds * 1000)))

    def _handle_page_swipe(self, delta: QPointF) -> bool:
        if abs(delta.x()) < 85 or abs(delta.x()) <= abs(delta.y()) * 1.25:
            return False
        current = self.stack.currentWidget()
        if delta.x() < 0:
            if current is self.home_screen:
                self.show_recording()
            elif current is self.recording_screen:
                self.show_archive()
            elif current is self.archive_screen:
                self.show_today_artwork()
            else:
                return False
        else:
            if current is self.recording_screen:
                self.show_home()
            elif current is self.archive_screen:
                self.show_recording()
            elif current is self.result_screen:
                self.show_archive()
            else:
                return False
        return True

    def start_recording(self) -> None:
        if self.worker.busy:
            return
        if self._daily_recording_locked():
            self._show_daily_recording_lock()
            return
        self.player.stop()
        self.pending_result = None
        self.processing_minimum_done = False
        self.worker.start()

    def _on_recording_started(self) -> None:
        seconds = float(self.config.get("record_seconds", 5))
        self.recording_screen.reset(seconds)
        self.stack.setCurrentWidget(self.recording_screen)

    def _on_recording_finished(self, recording: RecordingResult) -> None:
        self.store.register_raw(recording.path, recording.duration_seconds)
        self.player.stop()
        self.recording_screen.set_progress(1.0)
        self.recording_screen.show_completion(recording.path.stem)
        self.stack.setCurrentWidget(self.recording_screen)

    def continue_recording(self) -> None:
        if self._daily_recording_locked():
            self._show_daily_recording_lock()
            self.show_archive()
            return
        self.player.stop()
        self.recording_screen.prepare()
        self.stack.setCurrentWidget(self.recording_screen)

    def analyze_archive_entry(self, entry: LibraryEntry, color: str | None = None) -> None:
        if self.analysis_worker.busy:
            return
        self.pending_analysis_color = color
        self.player.stop()
        if entry.artwork_path is not None and entry.image_index is not None and entry.features:
            analysis = entry.analysis_result()
            self.show_result(HumResult(
                RecordingResult(entry.path, entry.duration_seconds, 44100, 1),
                analysis,
                entry.artwork_path,
            ))
            if color is not None:
                self._commit_daily_hum(entry.path, color)
                self.pending_analysis_color = None
            return
        self.pending_result = None
        self.processing_minimum_done = False
        self.processing_screen.reset()
        self.processing_screen.set_progress(0.04)
        self.stack.setCurrentWidget(self.processing_screen)
        minimum_ms = max(
            0,
            round(float(self.config.get("processing_minimum_seconds", 2.0)) * 1000),
        )
        for fraction, progress in ((0.25, 0.28), (0.50, 0.55), (0.75, 0.82)):
            QTimer.singleShot(
                round(minimum_ms * fraction),
                lambda value=progress: self.processing_screen.set_progress(value),
            )
        QTimer.singleShot(minimum_ms, lambda: self.processing_screen.set_progress(1.0))
        QTimer.singleShot(minimum_ms, self._processing_minimum_complete)
        self.analysis_worker.start(entry)

    def _processing_minimum_complete(self) -> None:
        self.processing_minimum_done = True
        self._show_pending_result_if_ready()

    def _on_analysis_finished(
        self,
        entry: LibraryEntry,
        analysis: AnalysisResult,
        artwork_path: Path,
    ) -> None:
        result = HumResult(
            RecordingResult(entry.path, entry.duration_seconds, 44100, 1),
            analysis,
            artwork_path,
        )
        self.pending_result = result
        self.store.register(
            result.recording.path,
            result.recording.duration_seconds,
            result.analysis,
            result.artwork_path,
        )
        self._show_pending_result_if_ready()

    def _on_analysis_failed(self, message: str) -> None:
        self.show_archive()
        self._show_error(message)

    def _show_pending_result_if_ready(self) -> None:
        if not self.processing_minimum_done or self.pending_result is None:
            return
        self.show_result(self.pending_result)
        self.pending_result = None
        if self.pending_analysis_color is not None and self.current_result is not None:
            color = self.pending_analysis_color
            self._commit_daily_hum(self.current_result.recording.path, color)
            self.pending_analysis_color = None

    def show_result(self, result: HumResult) -> None:
        self.current_result = result
        self.result_screen.set_result(
            result.artwork_path,
            result.analysis,
            float(self.config.get("initial_volume", 0.7)),
            "D" + "".join(filter(str.isdigit, result.recording.path.stem))[-12:].rjust(12, "0"),
        )
        self.player.load(result.recording.path)
        self.stack.setCurrentWidget(self.result_screen)

    def _on_recording_failed(self, message: str) -> None:
        self.show_home()
        self._show_error(message)

    def toggle_current_playback(self) -> None:
        if self.current_result is None:
            return
        if self.stack.currentWidget() is self.result_screen:
            self.player.toggle()

    def play_archive_entry(self, entry: LibraryEntry) -> None:
        try:
            self.archive_screen.set_active_entry(entry.path)
            if self.current_archive_entry is None or self.current_archive_entry.path != entry.path:
                self.player.load(entry.path)
                self.current_archive_entry = entry
            self.player.toggle()
        except Exception as exc:
            self._show_error(str(exc))

    def _on_player_state(self, state: str) -> None:
        self.result_screen.set_player_state(state)
        self.archive_screen.set_player_state(state)

    def _on_player_finished(self) -> None:
        self.result_screen.set_player_state("stopped")
        self.archive_screen.set_player_state("stopped")

    def save_current_hum(self) -> None:
        if self.current_result is None:
            return
        dialog = SaveDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self._commit_daily_hum(
                self.current_result.recording.path,
                dialog.selected_color,
            )

    def show_home(self) -> None:
        self.player.stop()
        self.current_archive_entry = None
        self.home_screen.restart_typing()
        self.stack.setCurrentWidget(self.home_screen)

    def show_recording(self) -> None:
        if self.worker.busy:
            return
        if self._daily_recording_locked():
            self._show_daily_recording_lock()
            return
        self.player.stop()
        self.recording_screen.prepare()
        self.stack.setCurrentWidget(self.recording_screen)

    def show_archive(self) -> None:
        if self.worker.busy:
            return
        self.player.stop()
        self.current_archive_entry = None
        self._refresh_archive()
        self.stack.setCurrentWidget(self.archive_screen)

    def show_today_artwork(self) -> None:
        if self.current_result is not None:
            self.show_result(self.current_result)
            return
        entries = self.store.entries()
        latest = next(
            (entry for entry in entries if entry.kept and entry.artwork_path is not None),
            None,
        ) or next(
            (entry for entry in entries if entry.artwork_path is not None),
            None,
        )
        if latest is not None:
            self.analyze_archive_entry(latest)
        else:
            self.stack.setCurrentWidget(self.result_screen)

    def toggle_favorite(self, entry: LibraryEntry) -> None:
        self.store.set_favorite(entry.path, not entry.favorite)
        self._refresh_archive()

    def delete_archive_entry(self, entry: LibraryEntry) -> None:
        if self.current_archive_entry and self.current_archive_entry.path == entry.path:
            self.player.stop()
            self.current_archive_entry = None
        self.store.delete(entry.path)
        self._refresh_archive()

    def set_archive_sort_mode(self, mode: str) -> None:
        self.archive_sort_mode = "favorite" if mode == "favorite" else "time"
        self.archive_screen.set_sort_mode(self.archive_sort_mode)
        self._refresh_archive()

    def _refresh_archive(self) -> None:
        self.archive_screen.set_entries(
            self.store.entries(sort_mode=self.archive_sort_mode)
        )

    def _commit_daily_hum(self, path: Path, color: str) -> None:
        deleted = set(self.store.keep_only_for_day(path, color))
        if self.current_archive_entry is not None and self.current_archive_entry.path in deleted:
            self.player.stop()
            self.current_archive_entry = None
        self.result_screen.set_accent(color)
        self.result_screen.mark_saved()

    def _daily_recording_locked(self) -> bool:
        return (
            not self.developer_mode
            and self.store.has_kept_recording_for_day()
        )

    def _show_daily_recording_lock(self) -> None:
        QMessageBox.information(
            self,
            "Today's Hum",
            "오늘의 Hum을 이미 남겼어요. 새로운 녹음은 내일 다시 할 수 있어요.",
        )

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "HumO error", message)

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.force_close:
            event.ignore()
            if not self.exit_video_playing:
                self.exit_video_playing = True
                self.player.stop()
                self._play_device_video("hum_device_end.mp4", self._finish_close)
            return
        self.player.stop()
        self.video_player.stop()
        if self.sensor is not None:
            try:
                self.sensor.close()
            except Exception:
                pass
        event.accept()

    def _finish_close(self) -> None:
        self.force_close = True
        self.close()


def main() -> None:
    app = QApplication(sys.argv)
    load_app_fonts()
    window = MainWindow()
    if window.config.get("fullscreen", True):
        window.showFullScreen()
    else:
        window.show()
    sys.exit(app.exec())
