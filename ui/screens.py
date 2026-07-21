from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtSvg import QSvgRenderer

from core.analyzer import AnalysisResult
from core.library import LibraryEntry
from ui import fonts
from ui.theme import (
    ACCENTS,
    BG,
    BUTTON_STYLE,
    FG,
    ICON_BUTTON_STYLE,
    INK,
    MUTED,
    PANEL,
    SLIDER_STYLE,
    SOFT,
)


IMAGE_DIR = Path(__file__).resolve().parents[1] / "assets" / "images"
_SVG_RENDERERS: dict[str, QSvgRenderer] = {}


def draw_svg(
    painter: QPainter,
    name: str,
    target: QRectF,
    opacity: float = 1.0,
    color: str | None = None,
) -> None:
    """Draw an SVG asset without rasterizing it at a fixed resolution."""
    renderer = _SVG_RENDERERS.get(name)
    if renderer is None:
        renderer = QSvgRenderer(str(IMAGE_DIR / name))
        _SVG_RENDERERS[name] = renderer
    if not renderer.isValid():
        return
    painter.save()
    painter.setOpacity(opacity)
    if color is None:
        renderer.render(painter, target)
    else:
        width = max(1, math.ceil(target.width()))
        height = max(1, math.ceil(target.height()))
        image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        image_painter = QPainter(image)
        renderer.render(image_painter, QRectF(0, 0, width, height))
        image_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        image_painter.fillRect(image.rect(), QColor(color))
        image_painter.end()
        painter.drawImage(target, image)
    painter.restore()


def svg_icon(name: str, color: str, size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    draw_svg(painter, name, QRectF(0, 0, size, size), color=color)
    painter.end()
    return QIcon(pixmap)


def draw_sound_icon(
    painter: QPainter,
    center: QPointF,
    scale: float,
    volume: float,
    adjustment_open: bool = False,
) -> None:
    """Draw a fixed-size sound icon, enlarged only while its controls are open."""
    size = (70 if adjustment_open else 52) * scale
    draw_svg(
        painter,
        "mute2.svg" if volume <= 0.0 else "icon_sound.svg",
        QRectF(center.x() - size / 2, center.y() - size / 2, size, size),
        color="#BFDFFF",
    )


def accent_icon_name(color: str) -> str:
    try:
        return f"{6483783 + ACCENTS.index(color)}.svg"
    except ValueError:
        return "6483783.svg"


def draw_orbit_details(
    painter: QPainter,
    center: QPointF,
    radius: float,
    scale: float,
) -> None:
    """Draw the small pill and cross registration marks used on the outer ring."""
    detail_color = QColor("#FFF9F0")
    painter.setPen(QPen(detail_color, max(1.0, 1.2 * scale), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(detail_color)
    for degree in (0, 90, 180, 270):
        angle = math.radians(degree)
        marker = QPointF(
            center.x() + math.cos(angle) * radius,
            center.y() + math.sin(angle) * radius,
        )
        painter.drawEllipse(marker, 7 * scale, 7 * scale)
        tangent = QPointF(-math.sin(angle) * 4 * scale, math.cos(angle) * 4 * scale)
        painter.setPen(QPen(QColor(BG), max(1.0, 1.6 * scale), Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(marker - tangent, marker + tangent)
        painter.setPen(QPen(detail_color, max(1.0, 1.2 * scale), Qt.SolidLine, Qt.RoundCap))

    arm = 4.0 * scale
    for degree in (45, 135, 225, 315):
        angle = math.radians(degree)
        marker = QPointF(
            center.x() + math.cos(angle) * radius,
            center.y() + math.sin(angle) * radius,
        )
        radial = QPointF(math.cos(angle) * arm, math.sin(angle) * arm)
        painter.drawLine(marker - radial, marker + radial)


def typed_text(text: str, elapsed_ms: int, character_ms: int = 85) -> str:
    """Return the portion of text revealed by a typewriter animation."""
    visible_characters = max(0, elapsed_ms) // max(1, character_ms)
    return text[:visible_characters]


def looping_typed_text(
    text: str,
    elapsed_ms: int,
    character_ms: int = 180,
    hold_ms: int = 900,
) -> str:
    """Type text, hold it briefly, then restart forever."""
    typing_ms = len(text) * max(1, character_ms)
    cycle_ms = max(1, typing_ms + max(0, hold_ms))
    return typed_text(text, elapsed_ms % cycle_ms, character_ms)


def format_recording_time(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


class BootScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.elapsed = QElapsedTimer()
        self.elapsed.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def restart(self) -> None:
        self.elapsed.restart()
        self.update()

    def _tick(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG))

        side = min(self.width(), self.height())
        elapsed = self.elapsed.elapsed()
        if elapsed < 600:
            opacity = elapsed / 600.0
        elif elapsed < 5900:
            opacity = 1.0
        else:
            opacity = max(0.0, (6600 - elapsed) / 700.0)
        painter.setOpacity(opacity)
        painter.setPen(QColor(FG))
        painter.setFont(QFont(fonts.EN_FONT, max(15, int(side * 0.038))))
        painter.drawText(
            QRectF(side * 0.18, 0, self.width() - side * 0.36, self.height()),
            Qt.AlignCenter,
            typed_text("Before words,\nthere is hum.", elapsed, 125),
        )
        painter.setOpacity(1.0)
        painter.end()


class HomeScreen(QWidget):
    recordRequested = Signal()
    archiveRequested = Signal()
    volumeChanged = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.press_pos: QPoint | None = None
        self.volume = 0.7
        self.volume_overlay = False
        self.volume_dragging = False
        self.phase = 0.0
        self.typing_elapsed = QElapsedTimer()
        self.typing_elapsed.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(45)

    def _tick(self) -> None:
        self.phase = (self.phase + 0.006) % 1.0
        self.update()

    def restart_typing(self) -> None:
        self.typing_elapsed.restart()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG))
        side = min(self.width(), self.height())
        scale = side / 720.0

        logo = QPixmap(str(IMAGE_DIR / "logo_image.png"))
        if not logo.isNull():
            logo_size = 600 * scale
            logo_rect = QRectF(
                self.width() / 2 - logo_size / 2,
                350 * scale - logo_size / 2,
                logo_size,
                logo_size,
            )
            painter.save()
            painter.setOpacity(0.42)
            painter.drawPixmap(logo_rect, logo, QRectF(logo.rect()))
            painter.restore()

        painter.setPen(QColor(FG))
        painter.setFont(QFont(fonts.EN_FONT, max(12, int(25 * scale))))
        painter.drawText(
            QRectF(0, 48 * scale, self.width(), 38 * scale),
            Qt.AlignCenter,
            typed_text("Catch that sounds...", self.typing_elapsed.elapsed(), 145),
        )

        center = QPointF(self.width() / 2, 350 * scale)

        painter.setPen(QPen(QColor(SOFT), max(1, int(1 * scale))))
        painter.setBrush(Qt.NoBrush)
        radii = (82, 160, 240)
        for radius in radii:
            painter.drawEllipse(center, radius * scale, radius * scale)

        outer = radii[-1] * scale
        draw_orbit_details(painter, center, outer, scale)

        volume_center = QPointF(53 * scale, 58 * scale)
        if not self.volume_overlay:
            draw_sound_icon(painter, volume_center, scale, self.volume)

        dot_y = self.height() - 102 * scale
        start_x = self.width() / 2 - 30 * scale
        painter.setPen(Qt.NoPen)
        for index in range(4):
            painter.setBrush(QColor(FG if index == 0 else MUTED))
            painter.drawEllipse(
                QPointF(start_x + index * 18 * scale, dot_y),
                4 * scale,
                4 * scale,
            )

        if self.volume_overlay:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 188))
            slider_x = 65 * scale
            slider_top = 160 * scale
            slider_bottom = 590 * scale
            handle_y = slider_bottom - self.volume * (slider_bottom - slider_top)
            painter.setPen(QPen(QColor("#FFF7EA"), max(1, int(2 * scale))))
            painter.drawLine(QPointF(slider_x, slider_top), QPointF(slider_x, slider_bottom))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#FFF7EA"))
            painter.drawEllipse(QPointF(slider_x, slider_top), 9 * scale, 9 * scale)
            painter.drawEllipse(QPointF(slider_x, slider_bottom), 9 * scale, 9 * scale)
            painter.drawEllipse(QPointF(slider_x, handle_y), 18 * scale, 18 * scale)
            painter.setPen(QColor("#FFF7EA"))
            painter.setFont(QFont("Arial", max(13, int(20 * scale))))
            painter.drawText(QRectF(35 * scale, 118 * scale, 60 * scale, 30 * scale), Qt.AlignCenter, "+")
            painter.drawText(QRectF(35 * scale, 603 * scale, 60 * scale, 30 * scale), Qt.AlignCenter, "−")
            draw_sound_icon(
                painter,
                volume_center,
                scale,
                self.volume,
                adjustment_open=True,
            )

        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.press_pos = event.pos()
            scale = min(self.width(), self.height()) / 720.0
            volume_center = QPointF(53 * scale, 58 * scale)
            if (QPointF(event.pos()) - volume_center).manhattanLength() <= 55 * scale:
                self.volume_overlay = not self.volume_overlay
                self.press_pos = None
                self.update()
                return
            if self.volume_overlay and event.pos().x() <= 125 * scale:
                self.volume_dragging = True
                self._set_volume_from_y(event.pos().y())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.volume_dragging:
            self._set_volume_from_y(event.pos().y())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.press_pos is None:
            return
        if self.volume_dragging:
            self.volume_dragging = False
            self.press_pos = None
            return
        if self.volume_overlay:
            self.volume_overlay = False
            self.press_pos = None
            self.update()
            return
        delta = event.pos() - self.press_pos
        self.press_pos = None
        if delta.x() < -85 and abs(delta.x()) > abs(delta.y()) * 1.25:
            self.archiveRequested.emit()
        elif abs(delta.x()) < 30 and abs(delta.y()) < 30:
            self.recordRequested.emit()

    def _set_volume_from_y(self, y: float) -> None:
        scale = min(self.width(), self.height()) / 720.0
        top, bottom = 160 * scale, 590 * scale
        self.volume = max(0.0, min(1.0, (bottom - y) / (bottom - top)))
        self.volumeChanged.emit(self.volume)
        self.update()


class StepHeader:
    @staticmethod
    def draw(
        painter: QPainter,
        rect: QRectF,
        active_step: int,
        scale: float,
        icon_multiplier: float = 1.0,
    ) -> None:
        count = 4
        margin = 25 * scale
        y = rect.top() + 38 * scale
        left = rect.left() + margin
        right = rect.right() - margin
        step_width = (right - left) / (count - 1)

        painter.setPen(QPen(QColor(FG), max(1, int(2 * scale))))
        painter.drawLine(QPointF(left, y), QPointF(right, y))

        for index in range(count):
            x = left + step_width * index
            active = index == active_step
            painter.setBrush(QColor(FG if active else BG))
            painter.setPen(QPen(QColor(FG), max(1, int((3 if active else 2) * scale))))
            painter.drawEllipse(
                QPointF(x, y),
                22 * scale * icon_multiplier,
                22 * scale * icon_multiplier,
            )
            icon_size = 29 * scale * icon_multiplier
            step_icons = ("6483788.svg", "6483791.svg", "6483789.svg", "6483790.svg")
            draw_svg(
                painter,
                step_icons[index],
                QRectF(x - icon_size / 2, y - icon_size / 2, icon_size, icon_size),
                color=BG if active else FG,
            )


class RecordingScreen(QWidget):
    startRequested = Signal()
    previousRequested = Signal()
    nextRequested = Signal()
    recordingsRequested = Signal()
    continueRequested = Signal()
    volumeChanged = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.levels = [0.03] * 56
        self.level = 0.0
        self.progress = 0.0
        self.seconds_total = 5.0
        self.recording = False
        self.press_pos: QPoint | None = None
        self.volume = 0.7
        self.volume_overlay = False
        self.volume_dragging = False
        self.completion_visible = False
        self.recording_number = "00000000000000"

    def prepare(self) -> None:
        self.recording = False
        self.completion_visible = False
        self.levels = [0.03] * 56
        self.level = 0.0
        self.progress = 0.0
        self.update()

    def reset(self, seconds: float) -> None:
        self.recording = True
        self.completion_visible = False
        self.levels = [0.03] * 56
        self.level = 0.0
        self.progress = 0.0
        self.seconds_total = seconds
        self.update()

    def show_completion(self, recording_number: str) -> None:
        self.recording = False
        self.completion_visible = True
        digits = "".join(character for character in recording_number if character.isdigit())
        self.recording_number = (digits[:14] or "00000000000000").ljust(14, "0")
        self.update()

    def push_level(self, value: float) -> None:
        self.level = max(0.0, min(1.0, value))
        self.levels.append(self.level)
        self.levels = self.levels[-56:]
        self.update()

    def set_progress(self, value: float) -> None:
        self.progress = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG))
        side = min(self.width(), self.height())
        scale = side / 720.0

        StepHeader.draw(
            painter,
            QRectF(115 * scale, 28 * scale, self.width() - 130 * scale, 90 * scale),
            0,
            scale,
        )

        box = QRectF(20 * scale, 150 * scale, self.width() - 40 * scale, 310 * scale)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#111111"))
        painter.drawRect(box)

        inner = box.adjusted(10 * scale, 48 * scale, -10 * scale, -48 * scale)
        center_y = inner.center().y()
        count = len(self.levels)
        step = inner.width() / count
        painter.setPen(Qt.NoPen)
        equalizer_gradient = QLinearGradient(inner.left(), center_y, inner.right(), center_y)
        equalizer_gradient.setColorAt(0.0, QColor("#9BCBF4"))
        equalizer_gradient.setColorAt(0.48, QColor("#DCEEFF"))
        equalizer_gradient.setColorAt(1.0, QColor("#FFF7EA"))
        for index, level in enumerate(self.levels):
            if self.recording:
                energy = max(0.04, level)
            else:
                distance = abs(index - (count - 1) / 2) / (count / 2)
                energy = 0.04 + (1 - distance) * (0.16 + 0.30 * abs(math.sin(index * 1.37)))
            height = inner.height() * (0.06 + 0.75 * energy)
            x = inner.left() + index * step + step * 0.25
            width = max(2.0, step * 0.45)
            painter.setBrush(equalizer_gradient)
            painter.drawRoundedRect(
                QRectF(x, center_y - height / 2, width, height),
                width / 2,
                width / 2,
            )

        elapsed_seconds = self.progress * self.seconds_total if self.recording else 0.0
        painter.setPen(QColor(FG))
        timer_font = QFont("Arial", max(24, int(43 * scale)))
        timer_font.setWeight(QFont.Light)
        painter.setFont(timer_font)
        painter.drawText(
            QRectF(0, 485 * scale, self.width(), 80 * scale),
            Qt.AlignCenter,
            format_recording_time(elapsed_seconds),
        )

        volume_center = QPointF(53 * scale, 58 * scale)
        if not self.volume_overlay:
            draw_sound_icon(painter, volume_center, scale, self.volume)

        dot_y = self.height() - 38 * scale
        for index in range(4):
            painter.setBrush(QColor(FG if index == 1 else MUTED))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(self.width() / 2 - 27 * scale + index * 18 * scale, dot_y), 4 * scale, 4 * scale)

        if self.volume_overlay:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 188))
            slider_x, slider_top, slider_bottom = 65 * scale, 160 * scale, 590 * scale
            handle_y = slider_bottom - self.volume * (slider_bottom - slider_top)
            painter.setPen(QPen(QColor("#FFF7EA"), max(1, int(2 * scale))))
            painter.drawLine(QPointF(slider_x, slider_top), QPointF(slider_x, slider_bottom))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#FFF7EA"))
            painter.drawEllipse(QPointF(slider_x, slider_top), 9 * scale, 9 * scale)
            painter.drawEllipse(QPointF(slider_x, slider_bottom), 9 * scale, 9 * scale)
            painter.drawEllipse(QPointF(slider_x, handle_y), 18 * scale, 18 * scale)
            painter.setPen(QColor("#FFF7EA"))
            painter.setFont(QFont("Arial", max(13, int(20 * scale))))
            painter.drawText(QRectF(35 * scale, 118 * scale, 60 * scale, 30 * scale), Qt.AlignCenter, "+")
            painter.drawText(QRectF(35 * scale, 603 * scale, 60 * scale, 30 * scale), Qt.AlignCenter, "−")
            draw_sound_icon(
                painter,
                volume_center,
                scale,
                self.volume,
                adjustment_open=True,
            )
        if self.completion_visible:
            self._draw_completion_popup(painter, scale)
        painter.end()

    def _draw_completion_popup(self, painter: QPainter, scale: float) -> None:
        painter.fillRect(self.rect(), QColor(0, 0, 0, 145))
        panel = QRectF(126 * scale, 182 * scale, 390 * scale, 265 * scale)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(164, 158, 149, 242))
        painter.drawRoundedRect(panel, 12 * scale, 12 * scale)

        painter.setPen(QColor("#FFFDF7"))
        painter.setFont(QFont(fonts.KO_FONT, max(15, int(21 * scale))))
        painter.drawText(
            QRectF(panel.left(), panel.top() + 28 * scale, panel.width(), 38 * scale),
            Qt.AlignCenter,
            "새로운 Hum이 저장되었어요.",
        )
        painter.setPen(QColor("#EEEAE3"))
        painter.setFont(QFont(fonts.KO_FONT, max(10, int(13 * scale))))
        painter.drawText(
            QRectF(panel.left(), panel.top() + 70 * scale, panel.width(), 26 * scale),
            Qt.AlignCenter,
            f"녹음 번호 : {self.recording_number}",
        )
        painter.setFont(QFont(fonts.KO_FONT, max(11, int(14 * scale))))
        painter.drawText(
            QRectF(panel.left() + 25 * scale, panel.top() + 112 * scale,
                   panel.width() - 50 * scale, 65 * scale),
            Qt.AlignCenter,
            "목록에서 다시 들어보고\n오늘의 소리로 남겨보세요.",
        )

        divider_y = panel.top() + 210 * scale
        painter.setPen(QPen(QColor(255, 255, 255, 80), max(1, int(scale))))
        painter.drawLine(QPointF(panel.left(), divider_y), QPointF(panel.right(), divider_y))
        painter.drawLine(QPointF(panel.center().x(), divider_y), QPointF(panel.center().x(), panel.bottom()))
        painter.setFont(QFont(fonts.KO_FONT, max(11, int(14 * scale))))
        painter.setPen(QColor("#FFFDF7"))
        painter.drawText(
            QRectF(panel.left(), divider_y, panel.width() / 2, panel.bottom() - divider_y),
            Qt.AlignCenter,
            "녹음 목록 보기",
        )
        painter.drawText(
            QRectF(panel.center().x(), divider_y, panel.width() / 2, panel.bottom() - divider_y),
            Qt.AlignCenter,
            "계속 녹음하기",
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.press_pos = event.pos()
            if self.completion_visible:
                return
            scale = min(self.width(), self.height()) / 720.0
            volume_center = QPointF(53 * scale, 58 * scale)
            if (QPointF(event.pos()) - volume_center).manhattanLength() <= 55 * scale:
                self.volume_overlay = not self.volume_overlay
                self.press_pos = None
                self.update()
                return
            if self.volume_overlay and event.pos().x() <= 125 * scale:
                self.volume_dragging = True
                self._set_volume_from_y(event.pos().y())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.volume_dragging:
            self._set_volume_from_y(event.pos().y())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.press_pos is None:
            return
        if self.completion_visible:
            scale = min(self.width(), self.height()) / 720.0
            panel = QRectF(126 * scale, 182 * scale, 390 * scale, 265 * scale)
            buttons = QRectF(panel.left(), panel.top() + 210 * scale, panel.width(), 55 * scale)
            position = QPointF(event.pos())
            self.press_pos = None
            if buttons.contains(position):
                self.completion_visible = False
                if position.x() < panel.center().x():
                    self.recordingsRequested.emit()
                else:
                    self.prepare()
                    self.continueRequested.emit()
            return
        if self.volume_dragging:
            self.volume_dragging = False
            self.press_pos = None
            return
        if self.volume_overlay:
            self.volume_overlay = False
            self.press_pos = None
            self.update()
            return
        delta = event.pos() - self.press_pos
        self.press_pos = None
        if delta.x() < -85 and abs(delta.x()) > abs(delta.y()) * 1.25:
            self.nextRequested.emit()
        elif delta.x() > 85 and abs(delta.x()) > abs(delta.y()) * 1.25:
            self.previousRequested.emit()
        elif not self.recording and abs(delta.x()) < 30 and abs(delta.y()) < 30:
            self.startRequested.emit()

    def _set_volume_from_y(self, y: float) -> None:
        scale = min(self.width(), self.height()) / 720.0
        top, bottom = 160 * scale, 590 * scale
        self.volume = max(0.0, min(1.0, (bottom - y) / (bottom - top)))
        self.volumeChanged.emit(self.volume)
        self.update()


class ProcessingScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.phase = 0.0
        self.progress = 0.0
        self.typing_elapsed = QElapsedTimer()
        self.typing_elapsed.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(32)

    def reset(self) -> None:
        self.phase = 0.0
        self.progress = 0.0
        self.typing_elapsed.restart()
        self.update()

    def set_progress(self, value: float) -> None:
        self.progress = max(0.0, min(1.0, value))
        self.update()

    def _tick(self) -> None:
        self.phase = (self.phase + 0.012) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG))
        side = min(self.width(), self.height())
        scale = side / 720.0

        painter.setPen(QColor(FG))
        painter.setFont(QFont(fonts.EN_FONT, max(11, int(20 * scale))))
        painter.drawText(
            QRectF(0, 35 * scale, self.width(), 30 * scale),
            Qt.AlignCenter,
            looping_typed_text("Humming...", self.typing_elapsed.elapsed()),
        )
        center = QPointF(self.width() / 2, 350 * scale)
        painter.setBrush(Qt.NoBrush)
        radii = (70, 120, 170, 220)
        for index, radius in enumerate(radii):
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(SOFT), max(1, int(1.1 * scale))))
            painter.drawEllipse(center, radius * scale, radius * scale)

            direction = 1 if index % 2 == 0 else -1
            speed = 0.55 + index * 0.24
            angle = 2 * math.pi * (self.phase * speed * direction + index * 0.17)
            marker = QPointF(
                center.x() + math.cos(angle) * radius * scale,
                center.y() + math.sin(angle) * radius * scale,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(FG))
            painter.drawEllipse(marker, (5 + index) * scale, (5 + index) * scale)

            opposite = angle + math.pi
            tick = QPointF(
                center.x() + math.cos(opposite) * radius * scale,
                center.y() + math.sin(opposite) * radius * scale,
            )
            painter.setPen(QPen(QColor(FG), max(1, int(2 * scale))))
            tangent_x = -math.sin(opposite) * 6 * scale
            tangent_y = math.cos(opposite) * 6 * scale
            painter.drawLine(
                QPointF(tick.x() - tangent_x, tick.y() - tangent_y),
                QPointF(tick.x() + tangent_x, tick.y() + tangent_y),
            )

        painter.setPen(QColor(SOFT))
        painter.setFont(QFont(fonts.KO_FONT, max(9, int(13 * scale))))
        painter.drawText(
            QRectF(50 * scale, 575 * scale, self.width() - 100 * scale, 30 * scale),
            Qt.AlignCenter,
            "선택한 소리를 분석해 아트워크를 만들고 있어요.",
        )
        painter.setPen(Qt.NoPen)
        for index in range(4):
            painter.setBrush(QColor(FG if index == 2 else MUTED))
            painter.drawEllipse(
                QPointF(self.width() / 2 - 27 * scale + index * 18 * scale, 630 * scale),
                4 * scale,
                4 * scale,
            )
        painter.end()


class ArtworkPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.pixmap: QPixmap | None = None
        self.colored_pixmap: QPixmap | None = None
        self.image_index = 1
        self.hum_id = "D000000000000"
        self.accent = "#90B8DC"
        self.fade_duration_ms = 1800
        self.fade_active = False
        self.fade_elapsed = QElapsedTimer()
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self._tick_fade)
        self.setMinimumHeight(390)

    def set_artwork(self, path: Path, image_index: int) -> None:
        pixmap = QPixmap(str(path))
        self.pixmap = None if pixmap.isNull() else pixmap
        self._rebuild_colored_pixmap()
        self.image_index = image_index
        self.fade_active = self.pixmap is not None
        if self.fade_active:
            self.fade_elapsed.restart()
            self.fade_timer.start(16)
        else:
            self.fade_timer.stop()
        self.update()

    def _tick_fade(self) -> None:
        if not self.fade_active:
            self.fade_timer.stop()
            return
        if self.fade_elapsed.elapsed() >= self.fade_duration_ms:
            self.fade_active = False
            self.fade_timer.stop()
        self.update()

    def _artwork_opacity(self) -> float:
        if not self.fade_active:
            return 1.0
        progress = max(
            0.0,
            min(1.0, self.fade_elapsed.elapsed() / self.fade_duration_ms),
        )
        return 0.5 - 0.5 * math.cos(math.pi * progress)

    def set_hum_id(self, hum_id: str) -> None:
        self.hum_id = hum_id
        self.update()

    def set_accent(self, color: str) -> None:
        self.accent = color
        self.update()

    def _rebuild_colored_pixmap(self) -> None:
        if self.pixmap is None:
            self.colored_pixmap = None
            return
        # 합성 모듈이 결정한 그라데이션 색을 UI에서 다시 덮어쓰지 않습니다.
        self.colored_pixmap = self.pixmap

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG))

        side = min(self.width(), self.height())
        stage_side = side * 0.82
        stage = QRectF(
            (self.width() - stage_side) / 2,
            side * 0.115,
            stage_side,
            stage_side,
        )
        painter.setPen(QColor(FG))
        painter.setFont(QFont(fonts.EN_FONT, max(12, int(side * 0.026))))
        painter.drawText(
            QRectF(0, side * 0.035, self.width(), side * 0.05),
            Qt.AlignCenter,
            f"Hum list : {self.hum_id}",
        )

        artwork = self.colored_pixmap or self.pixmap
        if artwork is not None:
            target = stage.adjusted(
                stage.width() * 0.018,
                stage.height() * 0.018,
                -stage.width() * 0.018,
                -stage.height() * 0.018,
            )
            painter.setOpacity(self._artwork_opacity())
            painter.drawPixmap(target, artwork, QRectF(artwork.rect()))
            painter.setOpacity(1.0)

        # 원형 가이드는 아트워크 뒤에 가려지지 않도록 마지막에 얇게 표시합니다.
        ring_color = QColor(FG)
        ring_color.setAlpha(205)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(ring_color, 1))
        for ring in (0.0, 0.17, 0.33):
            inset = stage.width() * ring
            painter.drawEllipse(stage.adjusted(inset, inset, -inset, -inset))
        draw_orbit_details(
            painter,
            stage.center(),
            stage.width() / 2,
            max(0.65, side / 720.0),
        )

        painter.setPen(Qt.NoPen)
        dot_y = min(self.height() - 24, stage.bottom() + side * 0.055)
        for index in range(4):
            painter.setBrush(QColor(FG))
            painter.drawEllipse(
                QPointF(self.width() / 2 - 27 + index * 18, dot_y),
                5,
                5,
            )
        painter.end()


class StackedIconButton(QPushButton):
    """Button with its SVG glyph centered above its label."""

    def __init__(self, icon_name: str, text: str) -> None:
        super().__init__(text)
        self.icon_name = icon_name

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.isDown():
            painter.fillRect(self.rect(), QColor(255, 255, 255, 24))
        icon_size = 22
        draw_svg(
            painter,
            self.icon_name,
            QRectF(self.width() / 2 - icon_size / 2, 5, icon_size, icon_size),
            color=FG,
        )
        painter.setPen(QColor(FG))
        painter.setFont(self.font())
        painter.drawText(
            QRectF(0, 29, self.width(), self.height() - 29),
            Qt.AlignHCenter | Qt.AlignTop,
            self.text(),
        )
        painter.end()


class ResultScreen(QWidget):
    playRequested = Signal()
    recordRequested = Signal()
    saveRequested = Signal()
    archiveRequested = Signal()
    volumeChanged = Signal(float)
    previousRequested = Signal()

    def __init__(self, show_features: bool = True) -> None:
        super().__init__()
        self.show_features = show_features
        self.analysis: AnalysisResult | None = None
        self.press_pos: QPoint | None = None

        self.title = QLabel("Today's artwork")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setFont(QFont(fonts.EN_FONT, 17))
        self.title.setStyleSheet(f"color: {FG}; background: transparent;")
        self.title.hide()

        self.artwork = ArtworkPanel()

        self.feature_label = QLabel("")
        self.feature_label.setAlignment(Qt.AlignCenter)
        self.feature_label.setFont(QFont(fonts.EN_FONT, 9))
        self.feature_label.setStyleSheet(f"color: {SOFT}; background: transparent;")
        self.feature_label.setVisible(show_features)

        self.record_button = QPushButton("↻\nAGAIN")
        self.play_button = QPushButton("▶\nLISTEN")
        self.save_button = StackedIconButton("icon_like.svg", "LEAVE")
        self.archive_button = QPushButton("···\nLIST")
        for button in (
            self.record_button,
            self.play_button,
            self.save_button,
            self.archive_button,
        ):
            button.setFont(QFont(fonts.EN_FONT, 10))
            button.setFixedSize(88, 58)
            button.setStyleSheet(ICON_BUTTON_STYLE)
        self.record_button.clicked.connect(self.recordRequested.emit)
        self.play_button.clicked.connect(self.playRequested.emit)
        self.save_button.clicked.connect(self.saveRequested.emit)
        self.archive_button.clicked.connect(self.archiveRequested.emit)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(10)
        controls.addStretch(1)
        controls.addWidget(self.record_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.save_button)
        controls.addWidget(self.archive_button)
        controls.addStretch(1)

        self.volume_box = QWidget()
        self.volume_box.setStyleSheet("background: transparent;")
        volume_layout = QHBoxLayout(self.volume_box)
        volume_layout.setContentsMargins(70, 0, 70, 0)
        volume_layout.setSpacing(12)
        quiet = QLabel("VOL")
        quiet.setFont(QFont(fonts.EN_FONT, 9))
        quiet.setStyleSheet(f"color: {SOFT};")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setStyleSheet(SLIDER_STYLE)
        self.volume_slider.valueChanged.connect(
            lambda value: self.volumeChanged.emit(value / 100.0)
        )
        loud = QLabel("MAX")
        loud.setFont(QFont(fonts.EN_FONT, 9))
        loud.setStyleSheet(f"color: {SOFT};")
        volume_layout.addWidget(quiet)
        volume_layout.addWidget(self.volume_slider, 1)
        volume_layout.addWidget(loud)
        self.volume_box.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.title)
        layout.addWidget(self.artwork, 1)
        layout.addWidget(self.feature_label)
        layout.addLayout(controls)
        layout.addWidget(self.volume_box)
        page_dots = QLabel("○  ○  ○  ●")
        page_dots.setAlignment(Qt.AlignCenter)
        page_dots.setFont(QFont(fonts.EN_FONT, 10))
        page_dots.setStyleSheet(f"color: {SOFT}; background: transparent;")
        page_dots.hide()
        layout.addWidget(page_dots)
        self.setStyleSheet(f"background: {BG}; color: {FG};")

    def set_result(
        self,
        image_path: Path,
        analysis: AnalysisResult,
        initial_volume: float,
        hum_id: str = "D000000000000",
    ) -> None:
        self.analysis = analysis
        self.artwork.set_artwork(image_path, analysis.image_index)
        self.artwork.set_hum_id(hum_id)
        self.volume_slider.setValue(round(initial_volume * 100))
        self.feature_label.setText(
            f"VOLUME {analysis.loudness:.2f}   TONE {analysis.brightness:.2f}   "
            f"TEXTURE {analysis.roughness:.2f}   MOTION {analysis.variability:.2f}   "
            f"{analysis.day_night.upper()} {'+'.join(analysis.components).upper()} "
            f"G{analysis.gradient_index}"
        )
        self.set_player_state("stopped")

    def set_player_state(self, state: str) -> None:
        if state == "playing":
            self.play_button.setText("Ⅱ\nPAUSE")
            self.volume_box.show()
        elif state == "paused":
            self.play_button.setText("▶\nRESUME")
            self.volume_box.hide()
        else:
            self.play_button.setText("▶\nLISTEN")
            self.volume_box.hide()

    def mark_saved(self) -> None:
        self.save_button.setText("LEFT")

    def set_accent(self, color: str) -> None:
        self.artwork.set_accent(color)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.press_pos = event.pos()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.press_pos is None:
            return
        delta = event.pos() - self.press_pos
        self.press_pos = None
        if delta.x() > 85 and abs(delta.x()) > abs(delta.y()) * 1.25:
            self.previousRequested.emit()


class SaveDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Leave Hum")
        self.setFixedSize(390, 250)
        self.selected_color = ACCENTS[0]
        self.setStyleSheet(
            f"""
            QDialog {{ background: {PANEL}; color: {INK}; }}
            QLabel {{ background: transparent; color: {INK}; }}
            QPushButton {{ background: transparent; color: {INK}; border: none; padding: 8px; }}
            QPushButton:pressed {{ color: #666666; }}
            """
        )

        title = QLabel("오늘의 Hum으로 남길까요?")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont(fonts.KO_FONT, 16))
        body = QLabel(
            "아트워크에 남길 색을 고르세요.\n"
            "남기면 오늘의 다른 녹음은 삭제됩니다."
        )
        body.setAlignment(Qt.AlignCenter)
        body.setFont(QFont(fonts.KO_FONT, 10))
        colors = QHBoxLayout()
        colors.setSpacing(10)
        color_buttons: list[QPushButton] = []
        for color in ACCENTS:
            button = QPushButton("")
            button.setFixedSize(42, 42)
            button.setCheckable(True)
            button.setIcon(QIcon(str(IMAGE_DIR / accent_icon_name(color))))
            button.setIconSize(QSize(34, 34))
            button.setStyleSheet(
                f"QPushButton {{ background: transparent; border: 2px solid transparent; border-radius: 21px; }}"
                f"QPushButton:checked {{ border-color: {INK}; }}"
            )
            button.clicked.connect(lambda checked=False, c=color: self._select_color(c, color_buttons))
            button.setProperty("color", color)
            color_buttons.append(button)
            colors.addWidget(button)
        color_buttons[0].setChecked(True)
        cancel = QPushButton("[취소]")
        keep = QPushButton("[남기기]")
        cancel.setFont(QFont(fonts.KO_FONT, 11))
        keep.setFont(QFont(fonts.KO_FONT, 11))
        cancel.clicked.connect(self.reject)
        keep.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(keep)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 34, 34, 28)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addSpacing(18)
        layout.addWidget(body)
        layout.addSpacing(18)
        layout.addLayout(colors)
        layout.addSpacing(12)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def _select_color(self, color: str, buttons: list[QPushButton]) -> None:
        self.selected_color = color
        for button in buttons:
            button.setChecked(button.property("color") == color)


class ArchiveRow(QFrame):
    playRequested = Signal(object)
    favoriteRequested = Signal(object)
    deleteRequested = Signal(object)
    analyzeRequested = Signal(object)

    def __init__(self, entry: LibraryEntry) -> None:
        super().__init__()
        self.entry = entry
        self.setFixedHeight(104)
        self.drag_dx = 0
        self.playing = False
        self.playback_position = 0.0
        self.playback_duration = max(0.01, entry.duration_seconds)
        self.envelope = self._load_envelope(entry.path)
        self.press_pos: QPoint | None = None
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        offset = max(-116.0, min(116.0, float(self.drag_dx)))
        painter.fillRect(self.rect(), QColor(BG))
        if abs(offset) > 4:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#3A342D"))
            if offset > 0:
                action_rect = QRectF(0, 0, offset, self.height())
                painter.drawRect(action_rect)
                icon_size = 30
                draw_svg(
                    painter,
                    "icon_like.svg",
                    QRectF(
                        action_rect.center().x() - icon_size / 2,
                        action_rect.center().y() - icon_size / 2,
                        icon_size,
                        icon_size,
                    ),
                    color="#C9DFF0",
                )
            else:
                action_rect = QRectF(self.width() + offset, 0, -offset, self.height())
                painter.drawRect(action_rect)
                center = action_rect.center()
                arm = 13
                painter.setPen(QPen(QColor("#BDB7AE"), 4, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(center.x() - arm, center.y() - arm),
                                 QPointF(center.x() + arm, center.y() + arm))
                painter.drawLine(QPointF(center.x() + arm, center.y() - arm),
                                 QPointF(center.x() - arm, center.y() + arm))
        painter.save()
        painter.translate(offset, 0)
        painter.fillRect(self.rect(), QColor(BG))
        painter.setPen(QPen(QColor("#35312C"), 1))
        painter.drawLine(QPointF(0, self.height() - 1), QPointF(self.width(), self.height() - 1))

        parts = self.entry.title.split()
        date_text = parts[0].rstrip(".") if parts else self.entry.title
        time_text = parts[1] if len(parts) > 1 else ""
        painter.setPen(QColor(FG))
        painter.setFont(QFont(fonts.EN_FONT, 18, QFont.Normal))
        painter.drawText(QRectF(34, 20, 125, 34), Qt.AlignLeft | Qt.AlignVCenter, date_text)
        painter.drawText(QRectF(168, 20, 95, 34), Qt.AlignLeft | Qt.AlignVCenter, time_text)
        painter.setPen(QColor("#8A847C"))
        painter.setFont(QFont(fonts.EN_FONT, 10, QFont.Normal))
        painter.drawText(
            QRectF(35, 54, 120, 24), Qt.AlignLeft | Qt.AlignVCenter,
            format_recording_time(self.entry.duration_seconds),
        )

        favorite_center = QPointF(self.width() - 200, self.height() / 2)
        draw_svg(
            painter,
            "icon_like.svg",
            QRectF(favorite_center.x() - 16, favorite_center.y() - 16, 32, 32),
            1.0 if self.entry.favorite else 0.28,
            FG,
        )

        play_center = QPointF(self.width() - 112, self.height() / 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(FG))
        if self.playing:
            painter.drawRect(QRectF(play_center.x() - 10, play_center.y() - 13, 7, 26))
            painter.drawRect(QRectF(play_center.x() + 4, play_center.y() - 13, 7, 26))
        else:
            painter.drawPolygon([
                QPointF(play_center.x() - 9, play_center.y() - 15),
                QPointF(play_center.x() - 9, play_center.y() + 15),
                QPointF(play_center.x() + 15, play_center.y()),
            ])
        select_center = QPointF(self.width() - 40, self.height() / 2)
        if self.entry.kept:
            draw_svg(
                painter,
                accent_icon_name(self.entry.color),
                QRectF(select_center.x() - 17, select_center.y() - 17, 34, 34),
                color=FG,
            )
        else:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(FG), 2))
            painter.drawEllipse(select_center, 16, 16)
        painter.restore()
        painter.end()
        return
        row_height = self.height() - 10
        reveal = min(150.0, abs(float(self.drag_dx))) if abs(self.drag_dx) > 8 else 0.0
        if self.drag_dx > 0:
            extension = QRectF(0, 5, reveal + 64, row_height)
            card = QRectF(reveal, 5, self.width() - reveal, row_height)
        elif self.drag_dx < 0:
            extension = QRectF(self.width() - reveal - 64, 5, reveal + 64, row_height)
            card = QRectF(0, 5, self.width() - reveal, row_height)
        else:
            extension = QRectF()
            card = QRectF(0, 5, self.width(), row_height)
        painter.setPen(Qt.NoPen)
        if reveal > 0:
            painter.setBrush(QColor("#1F1F1F"))
            painter.drawRoundedRect(extension, 64, 64)
        painter.setBrush(QColor("#BFDFFF"))
        painter.drawRoundedRect(card, 64, 64)
        painter.setPen(QColor("#201A15"))
        painter.setFont(QFont(fonts.EN_FONT, 20, QFont.Normal))
        painter.drawText(card.adjusted(46, 20, -130, -55), Qt.AlignLeft | Qt.AlignVCenter, self.entry.title)
        painter.setFont(QFont(fonts.EN_FONT, 12, QFont.Normal))
        painter.drawText(card.adjusted(46, 72, -130, -18), Qt.AlignLeft | Qt.AlignVCenter, f"{self.entry.duration_seconds:.0f} sec")
        center = QPointF(card.right() - 74, card.center().y())
        painter.setBrush(QColor("#201A15"))
        if self.playing:
            envelope_index = min(
                max(0, len(self.envelope) - 4),
                int((self.playback_position / self.playback_duration) * max(1, len(self.envelope) - 4)),
            )
            values = self.envelope[envelope_index : envelope_index + 4]
            for index, value in enumerate(values):
                height = 12 + 36 * value
                x = center.x() - 19 + index * 12
                painter.drawRoundedRect(QRectF(x, center.y() - height / 2, 4, height), 2, 2)
        else:
            painter.drawPolygon([
                QPointF(center.x() - 11, center.y() - 17),
                QPointF(center.x() - 11, center.y() + 17),
                QPointF(center.x() + 17, center.y()),
            ])

        if reveal > 0:
            strength = min(1.0, reveal / 90.0)
            painter.setOpacity(0.40 + strength * 0.60)
            painter.setPen(QColor(FG))
            painter.setFont(QFont(fonts.EN_FONT, 34))
            if self.drag_dx > 0:
                symbol = "♥" if self.drag_dx >= 75 else "♡"
                action_center = QPointF(reveal / 2, card.center().y())
            else:
                symbol = "×"
                action_center = QPointF(self.width() - reveal / 2, card.center().y())
            painter.drawText(
                QRectF(action_center.x() - 40, 5, 80, row_height),
                Qt.AlignCenter,
                symbol,
            )
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.press_pos = event.pos()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.press_pos is not None:
            self.drag_dx = event.pos().x() - self.press_pos.x()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.press_pos is None:
            return
        delta = event.pos() - self.press_pos
        self.press_pos = None
        self.drag_dx = 0
        if delta.x() < -75 and abs(delta.x()) > abs(delta.y()) * 1.25:
            self.deleteRequested.emit(self.entry)
        elif delta.x() > 75 and abs(delta.x()) > abs(delta.y()) * 1.25:
            self.favoriteRequested.emit(self.entry)
        elif abs(delta.x()) <= 25 and abs(delta.y()) <= 25:
            if event.pos().x() > self.width() - 75:
                self.analyzeRequested.emit(self.entry)
            elif event.pos().x() > self.width() - 155:
                self.playRequested.emit(self.entry)
            elif event.pos().x() > self.width() - 245:
                self.favoriteRequested.emit(self.entry)
        self.update()
        return
        self.drag_dx = 0
        if delta.x() < -75:
            self.deleteRequested.emit(self.entry)
        elif delta.x() > 75:
            self.favoriteRequested.emit(self.entry)
        elif event.pos().x() > self.width() - 125:
            self.playRequested.emit(self.entry)
        else:
            self.analyzeRequested.emit(self.entry)
        self.update()

    def set_playing(self, playing: bool) -> None:
        self.playing = playing
        self.update()

    def set_playback_position(self, position: float, duration: float) -> None:
        self.playback_position = max(0.0, position)
        self.playback_duration = max(0.01, duration)
        if self.playing:
            self.update()

    @staticmethod
    def _load_envelope(path: Path) -> list[float]:
        try:
            audio, _ = sf.read(str(path), always_2d=True, dtype="float32")
            mono = np.mean(np.abs(audio), axis=1)
            chunks = np.array_split(mono, 120)
            values = np.asarray([float(np.sqrt(np.mean(chunk * chunk))) if len(chunk) else 0.0 for chunk in chunks])
            peak = float(np.max(values)) if len(values) else 0.0
            if peak > 1e-8:
                values = values / peak
            return values.tolist()
        except Exception:
            return [0.25, 0.45, 0.7, 0.35] * 30


class BottomFade(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        gradient = QLinearGradient(0, self.height() * 0.45, 0, self.height())
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(0.72, QColor(0, 0, 0, 145))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(self.rect(), gradient)


class ArchiveStepHeader(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(112)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = min(self.width(), 720) / 720.0
        inset = 52 * scale
        StepHeader.draw(
            painter,
            QRectF(inset, 15, self.width() - inset * 2, 82),
            1,
            scale,
            1.25,
        )
        painter.end()


class ColorOverlay(QWidget):
    accepted = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.selected = ACCENTS[0]
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setMouseTracking(True)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
        panel = QRectF(self.width() * 0.15, self.height() * 0.20, self.width() * 0.70, self.height() * 0.60)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(164, 158, 149, 242))
        painter.drawRoundedRect(panel, 14, 14)
        painter.setPen(QColor("#FFFDF7"))
        painter.setFont(QFont(fonts.KO_FONT, 19))
        painter.drawText(
            QRectF(panel.left(), panel.top() + 35, panel.width(), 38),
            Qt.AlignCenter,
            "오늘의 Hum으로 남길까요?",
        )
        painter.setPen(QColor("#EEEAE3"))
        painter.setFont(QFont(fonts.KO_FONT, 11))
        painter.drawText(
            QRectF(panel.left(), panel.top() + 78, panel.width(), 28),
            Qt.AlignCenter,
            "이 소리에 가장 어울리는 감각을 선택해보세요.",
        )
        y = panel.top() + 170
        spacing = panel.width() / 6
        for index, color in enumerate(ACCENTS):
            center = QPointF(panel.left() + spacing * (index + 1), y)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(FG if color == self.selected else QColor(255, 255, 255, 0)), 3))
            painter.drawEllipse(center, 31, 31)
            draw_svg(painter, accent_icon_name(color), QRectF(center.x() - 25, center.y() - 25, 50, 50))
        painter.setPen(QColor("#FFFDF7"))
        painter.setFont(QFont(fonts.KO_FONT, 11))
        painter.drawText(
            QRectF(panel.left() + 38, panel.top() + 215, panel.width() - 76, 75),
            Qt.AlignCenter,
            "오늘 머물렀던 여러 감각 중\n하나를 선택해 기록으로 남겨보세요.\n저장하면 오늘의 다른 녹음은 바로 삭제됩니다.",
        )
        divider_y = panel.bottom() - 72
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1))
        painter.drawLine(QPointF(panel.left(), divider_y), QPointF(panel.right(), divider_y))
        painter.drawLine(QPointF(panel.center().x(), divider_y), QPointF(panel.center().x(), panel.bottom()))
        painter.setPen(QColor("#FFFDF7"))
        painter.drawText(QRectF(panel.left(), divider_y, panel.width() / 2, 72), Qt.AlignCenter, "닫기")
        painter.drawText(QRectF(panel.center().x(), divider_y, panel.width() / 2, 72), Qt.AlignCenter, "저장하기")
        painter.end()
        return
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
        panel = QRectF(self.width() * 0.15, self.height() * 0.20, self.width() * 0.70, self.height() * 0.60)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(205, 201, 195, 218))
        painter.drawRoundedRect(panel, 14, 14)
        painter.setPen(QColor(FG))
        painter.setFont(QFont(fonts.KO_FONT, 19))
        painter.drawText(panel.adjusted(20, 40, -20, -panel.height() + 90), Qt.AlignCenter, "오늘의 Hum으로 남길까요?")
        y = panel.top() + 170
        spacing = panel.width() / 6
        for index, color in enumerate(ACCENTS):
            center = QPointF(panel.left() + spacing * (index + 1), y)
            painter.setBrush(QColor(color))
            painter.setPen(QPen(QColor(FG if color == self.selected else QColor(255, 255, 255, 0)), 3))
            painter.drawEllipse(center, 27, 27)
        painter.setPen(QColor(FG))
        painter.setFont(QFont(fonts.KO_FONT, 12))
        painter.drawText(panel.adjusted(45, 225, -45, -105), Qt.AlignCenter,
                         "오늘 머물렀던 감각 중 하나를 선택해 기록으로 남겨보세요.\n선택한 색은 아트워크 위에 자연스럽게 더해집니다.")
        painter.setFont(QFont(fonts.KO_FONT, 12))
        painter.drawText(QRectF(panel.left() + 40, panel.bottom() - 70, 110, 40), Qt.AlignCenter, "닫기")
        painter.drawText(QRectF(panel.right() - 150, panel.bottom() - 70, 110, 40), Qt.AlignCenter, "저장하기")
        painter.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        panel = QRectF(self.width() * 0.15, self.height() * 0.20, self.width() * 0.70, self.height() * 0.60)
        y = panel.top() + 170
        spacing = panel.width() / 6
        for index, color in enumerate(ACCENTS):
            center = QPointF(panel.left() + spacing * (index + 1), y)
            if (QPointF(event.pos()) - center).manhattanLength() < 42:
                self.selected = color
                self.update()
                return
        if event.pos().y() > panel.bottom() - 90:
            if event.pos().x() < panel.center().x():
                self.cancelled.emit()
            else:
                self.accepted.emit(self.selected)


class ArchiveScreen(QWidget):
    backRequested = Signal()
    playRequested = Signal(object)
    favoriteRequested = Signal(object)
    deleteRequested = Signal(object)
    volumeChanged = Signal(float)
    analyzeRequested = Signal(object)
    previousRequested = Signal()
    nextRequested = Signal()
    colorAnalyzeRequested = Signal(object, str)
    sortRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[LibraryEntry] = []
        self.press_pos: QPoint | None = None
        self.pending_color_entry: LibraryEntry | None = None
        self.active_path: Path | None = None
        self.sort_mode = "time"
        self.setStyleSheet(f"background: {BG}; color: {FG};")

        header = ArchiveStepHeader()

        self.favorite_sort_button = QPushButton("FAVORITES")
        self.favorite_sort_button.setIcon(svg_icon("icon_like.svg", FG, 18))
        self.favorite_sort_button.setIconSize(QSize(18, 18))
        self.time_sort_button = QPushButton("TIME  ↓")
        sort_style = BUTTON_STYLE + """
        QPushButton:checked {
            color: #000000;
            background: #f4f4f4;
            border-color: #f4f4f4;
        }
        """
        for button in (self.favorite_sort_button, self.time_sort_button):
            button.setCheckable(True)
            button.setFont(QFont(fonts.EN_FONT, 9, QFont.Normal))
            button.setFixedHeight(38)
            button.setStyleSheet(sort_style)
        self.time_sort_button.setChecked(True)
        self.favorite_sort_button.clicked.connect(
            lambda checked=False: self.set_sort_mode("favorite", emit=True)
        )
        self.time_sort_button.clicked.connect(
            lambda checked=False: self.set_sort_mode("time", emit=True)
        )
        sort_layout = QHBoxLayout()
        sort_layout.setContentsMargins(0, 0, 0, 4)
        sort_layout.setSpacing(8)
        sort_layout.addWidget(self.favorite_sort_button)
        sort_layout.addWidget(self.time_sort_button)

        self.list_widget = QWidget()
        self.list_widget.setStyleSheet(f"background: {BG};")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background: {BG}; border: none;")
        scroll.setWidget(self.list_widget)
        scroll_layer = QWidget()
        scroll_stack = QStackedLayout(scroll_layer)
        scroll_stack.setContentsMargins(0, 0, 0, 0)
        scroll_stack.setStackingMode(QStackedLayout.StackAll)
        scroll_stack.addWidget(scroll)
        scroll_stack.addWidget(BottomFade())
        scroll_stack.setCurrentIndex(1)

        self.volume_box = QWidget()
        volume_layout = QHBoxLayout(self.volume_box)
        volume_layout.setContentsMargins(50, 0, 50, 0)
        label = QLabel("PLAYBACK VOLUME")
        label.setFont(QFont(fonts.EN_FONT, 8))
        label.setStyleSheet(f"color: {SOFT};")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setStyleSheet(SLIDER_STYLE)
        self.volume_slider.valueChanged.connect(
            lambda value: self.volumeChanged.emit(value / 100.0)
        )
        volume_layout.addWidget(label)
        volume_layout.addWidget(self.volume_slider, 1)
        self.volume_box.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 18)
        layout.setSpacing(6)
        layout.addWidget(header)
        layout.addLayout(sort_layout)
        layout.addWidget(scroll_layer, 1)
        layout.addWidget(self.volume_box)
        page_dots = QLabel("○  ○  ●  ○")
        page_dots.setAlignment(Qt.AlignCenter)
        page_dots.setFont(QFont(fonts.EN_FONT, 10))
        page_dots.setStyleSheet(f"color: {SOFT};")
        layout.addWidget(page_dots)
        self.color_overlay = ColorOverlay(self)
        self.color_overlay.cancelled.connect(self.color_overlay.hide)
        self.color_overlay.accepted.connect(self._accept_color)

    def set_sort_mode(self, mode: str, emit: bool = False) -> None:
        self.sort_mode = "favorite" if mode == "favorite" else "time"
        self.favorite_sort_button.setChecked(self.sort_mode == "favorite")
        self.time_sort_button.setChecked(self.sort_mode == "time")
        if emit:
            self.sortRequested.emit(self.sort_mode)

    def set_entries(self, entries: list[LibraryEntry]) -> None:
        self.entries = entries
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not entries:
            empty = QLabel("No sounds yet.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setFont(QFont(fonts.EN_FONT, 13, QFont.Normal))
            empty.setStyleSheet(f"color: {SOFT};")
            self.list_layout.addWidget(empty)
        else:
            for entry in entries:
                row = ArchiveRow(entry)
                row.playRequested.connect(self.playRequested.emit)
                row.favoriteRequested.connect(self.favoriteRequested.emit)
                row.deleteRequested.connect(self.deleteRequested.emit)
                row.analyzeRequested.connect(self._show_color_overlay)
                self.list_layout.addWidget(row)
        self.list_layout.addStretch(1)

    def set_player_state(self, state: str) -> None:
        self.volume_box.hide()
        for row in self.findChildren(ArchiveRow):
            row.set_playing(state == "playing" and row.entry.path == self.active_path)

    def set_active_entry(self, path: Path) -> None:
        self.active_path = path

    def set_playback_position(self, position: float, duration: float) -> None:
        for row in self.findChildren(ArchiveRow):
            if row.entry.path == self.active_path:
                row.set_playback_position(position, duration)

    def _show_color_overlay(self, entry: LibraryEntry) -> None:
        self.pending_color_entry = entry
        self.color_overlay.selected = entry.color
        self.color_overlay.setGeometry(self.rect())
        self.color_overlay.show()
        self.color_overlay.raise_()

    def _accept_color(self, color: str) -> None:
        self.color_overlay.hide()
        if self.pending_color_entry is not None:
            self.colorAnalyzeRequested.emit(self.pending_color_entry, color)
            self.pending_color_entry = None

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.color_overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.press_pos = event.pos()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.press_pos is None:
            return
        delta = event.pos() - self.press_pos
        self.press_pos = None
        if delta.x() < -85 and abs(delta.x()) > abs(delta.y()) * 1.25:
            self.nextRequested.emit()
        elif delta.x() > 85 and abs(delta.x()) > abs(delta.y()) * 1.25:
            self.previousRequested.emit()
