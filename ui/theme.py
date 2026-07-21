BG = "#000000"
FG = "#F4F4F4"
MUTED = "#858585"
SOFT = "#BDBDBD"
PANEL = "#D8D8D8"
INK = "#111111"
ACCENTS = ["#90B8DC", "#B7DCE1", "#CFEDBD", "#FFE9B8", "#F4F4F4"]

BUTTON_STYLE = """
QPushButton {
    color: #f4f4f4;
    background: transparent;
    border: 1px solid #737373;
    border-radius: 0px;
    padding: 10px 14px;
}
QPushButton:pressed {
    color: #000000;
    background: #f4f4f4;
}
QPushButton:disabled {
    color: #5e5e5e;
    border-color: #3d3d3d;
}
"""

ICON_BUTTON_STYLE = """
QPushButton {
    color: #f4f4f4;
    background: transparent;
    border: none;
    padding: 7px;
}
QPushButton:pressed {
    color: #9a9a9a;
}
"""

SLIDER_STYLE = """
QSlider::groove:horizontal {
    height: 2px;
    background: #555555;
}
QSlider::sub-page:horizontal {
    background: #f4f4f4;
}
QSlider::handle:horizontal {
    background: #f4f4f4;
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}
"""
