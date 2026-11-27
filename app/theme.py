import ctypes
import sys

from PySide6.QtWidgets import QMainWindow


def enable_windows_dark_titlebar(window: QMainWindow) -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0f0f12;
    color: #f4f4f6;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QFrame#sidebar {
    background-color: #151519;
    border-right: 1px solid #24242b;
}
QLabel#brandTitle {
    font-size: 19px;
    font-weight: 700;
    color: #ffffff;
    background-color:transparent;
}
QLabel#sectionLabel {
    font-size: 11px;
    font-weight: 600;
    color: #6b6b78;
    padding:6px;
}
QLabel#mutedLabel {
    font-size: 11.5px;
    color: #8c8c9a;
    padding:2px;
}
QLabel#privacyLabel {
    font-size: 11px;
    font-weight: 600;
    color: #22c55e;
    padding: 4px 0;
}
QFrame#hwBox {
    background-color: #1b1b21;
    border: 1px solid #26262f;
    border-radius: 10px;
}
QLabel#hwTitle {
    font-size: 12px;
    font-weight: 600;
    color: #f4f4f6;
    padding:2px;
}
QListWidget#historyList {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget#historyList::item {
    padding: 9px 10px;
    border-radius: 8px;
    margin-bottom: 3px;
    color: #e4e4ea;
}
QListWidget#historyList::item:hover {
    background-color: #202028;
}
QListWidget#historyList::item:selected {
    background-color: rgba(59, 130, 246, 0.18);
    border: 1px solid rgba(59, 130, 246, 0.45);
    color: #ffffff;
}
QPushButton#primaryBtn {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    border-radius: 9px;
    padding: 0 16px;
    font-weight: 600;
}
QPushButton#primaryBtn:hover { background-color: #2563eb; }
QPushButton#primaryBtn:disabled { background-color: #26262f; color: #6b6b78; }

QFrame#dropCard {
    background-color: #16161c;
    border: 2px dashed #2e2e3a;
    border-radius: 22px;
}
QFrame#dropCard[dragging="true"] {
    border-color: #3b82f6;
    background-color: rgba(59, 130, 246, 0.10);
}
QLabel#dropTitle {
    font-size: 21px;
    font-weight: 700;
    color: #ffffff;
    padding-bottom:2px;
}
QLabel#dropSub {
    font-size: 13.5px;
    color: #9c9ca8;
    line-height: 1.5;
    padding:6px;
}
QLabel#pillLabel,QCheckBox {
    background-color: #0f0f12;
    border: 1px solid #282832;
    border-radius: 12px;
    padding: 4px 12px 5px 12px;
    font-size: 12px;
    color: #b4b4c0;
}
QFrame#topbar {
    background-color: #0f0f12;
    border-bottom: 1px solid #222229;
}
QLineEdit#docTitle {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    font-size: 17px;
    font-weight: 700;
    color: #ffffff;
    padding: 2px 6px;
}
QLineEdit#docTitle:hover { border-color: #2a2a34; }
QLineEdit#docTitle:focus { border-color: #3b82f6; background-color: #18181f; }

QLineEdit#searchInput {
    background-color: #18181f;
    border: 1px solid #282832;
    border-radius: 8px;
    padding: 6px 10px;
    color: #f4f4f6;
}
QLineEdit#searchInput:focus { border-color: #3b82f6; }

QFrame#progressBanner {
    background-color: #18181f;
    border: 1px solid rgba(59, 130, 246, 0.4);
    border-radius: 12px;
}
QLabel#statusLabel { font-weight: 600; color: #f4f4f6; }
QProgressBar {
    background-color: #0f0f12;
    border: none;
    border-radius: 3px;
}
QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 3px;
}
QPushButton#cancelBtn {
    background: transparent;
    border: 1px solid #353542;
    border-radius: 7px;
    padding: 0 12px;
    color: #b4b4c0;
}
QPushButton#cancelBtn:hover { border-color: #ef4444; color: #ef4444; }

QFrame#segmentRow {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 11px;
}
QFrame#segmentRow:hover { background-color: #17171d; }
QFrame#segmentRow[active="true"] {
    background-color: rgba(59, 130, 246, 0.13);
    border: 1px solid rgba(59, 130, 246, 0.35);
}
QPushButton#timestampBtn {
    background-color: #1b1b22;
    border: 1px solid #282832;
    border-radius: 6px;
    padding: 4px 6px;
    font-family: "Consolas", monospace;
    font-size: 12px;
    color: #9c9ca8;
}
QPushButton#timestampBtn:hover { border-color: #3b82f6; color: #3b82f6; }

QLabel#segPrimary {
    font-size: 14.5px;
    color: #f4f4f6;
    background: transparent;
}
QFrame#playerBar {
    background-color: #15151a;
    border-top: 1px solid #24242b;
}
QPushButton#playBtn {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    border-radius: 18px;
    font-size: 14px;
    font-weight: 700;
}
QPushButton#playBtn:hover { background-color: #2563eb; }
QPushButton#miniBtn {
    background-color: #1d1d24;
    border: 1px solid #2c2c36;
    border-radius: 7px;
    padding: 5px 9px;
    color: #b4b4c0;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#miniBtn:hover { color: #ffffff; border-color: #3b82f6; }
QLabel#timeLabel {
    font-family: "Consolas", monospace;
    font-size: 12px;
    color: #9c9ca8;
    min-width: 44px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #2a2a34;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 12px;
    height: 12px;
    margin: -4px 0;
    background: #ffffff;
    border-radius: 6px;
}
QMenu {
    background-color: #1b1b22;
    border: 1px solid #2e2e3a;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 7px 14px;
    border-radius: 5px;
}
QMenu::item:selected { background-color: #3b82f6; color: #ffffff; }
QTextEdit {
    background-color: #18181f;
    border: 1px solid #2e2e3a;
    border-radius: 8px;
    padding: 6px;
    color: #f4f4f6;
}
QScrollBar:vertical {
    background: transparent;
    width: 7px;
}
QScrollBar::handle:vertical {
    background: #2e2e3a;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""
