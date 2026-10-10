"""Shared Fluent Companion tokens and Manager-only Qt styling."""
from PyQt6.QtGui import QFontDatabase
from ...config.settings import settings

PALETTES = {
 'light': dict(background='#F7F9FC', surface='#FFFFFF', subtle='#F1F5F9', text='#1F2937', muted='#64748B', border='#E2E8F0', selection='#E0E7FF', accent='#115086', hover='#3368A0', success='#16803C', success_bg='#DCFCE7', warning='#A16207', warning_bg='#FEF3C7', danger='#DC2626', danger_bg='#FEE2E2', secure='#7C3AED', secure_bg='#EDE9FE'),
 'dark': dict(background='#111827', surface='#1F2937', subtle='#253349', text='#F7F9FC', muted='#A6B5C9', border='#374151', selection='#2C4668', accent='#87BFFF', hover='#A0C9FF', success='#86EFAC', success_bg='#163E30', warning='#FCD34D', warning_bg='#49391B', danger='#FCA5A5', danger_bg='#492930', secure='#C4B5FD', secure_bg='#352953'),
}
_font_family = None

def load_font():
    global _font_family
    if _font_family is None:
        result = QFontDatabase.addApplicationFont(str(settings.BASE_DIR / 'assets/fonts/InterVariable.ttf'))
        families = QFontDatabase.applicationFontFamilies(result) if result >= 0 else []
        _font_family = families[0] if families else 'Segoe UI'
    return _font_family

def stylesheet(theme):
    pref_bg = '#0e1424' if theme == 'dark' else PALETTES[theme]['surface']
    pref_border = '#1e293b' if theme == 'dark' else PALETTES[theme]['border']
    colors = dict(PALETTES[theme], font=load_font(), pref_bg=pref_bg, pref_border=pref_border)
    return """
    QWidget { background: transparent; color: %(text)s; font-family: '%(font)s'; font-size: 13px; }
    QWidget#managerBackground, QWidget#managerContent, QScrollArea { background: %(background)s; }
    QFrame#sidebar { background: %(surface)s; border-right: 1px solid %(border)s; }
    QFrame#card { background: %(surface)s; border: 1px solid %(border)s; border-radius: 16px; }
    QFrame#preferencesCard { background: %(pref_bg)s; border: 1px solid %(pref_border)s; border-radius: 16px; }
    QPushButton#savePreferencesBtn {
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a68ff, stop:1 #0080ff);
        color: #ffffff;
        border: 1px solid rgba(59, 130, 246, 0.5);
        border-radius: 12px;
        font-size: 14px;
        font-weight: 600;
        padding: 10px 20px;
        min-height: 24px;
    }
    QPushButton#savePreferencesBtn:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2575fc, stop:1 #0ea5e9);
        border-color: rgba(96, 165, 250, 0.8);
    }
    QPushButton#savePreferencesBtn:pressed {
        background-color: #1d4ed8;
    }
    QFrame#inset { background: %(subtle)s; border: 1px solid %(border)s; border-radius: 10px; }
    QLabel#brand { font-size: 19px; font-weight: 700; }
    QLabel#heading { font-size: 28px; font-weight: 700; }
    QLabel#subheading { font-size: 17px; font-weight: 600; }
    QLabel#metric { font-size: 32px; font-weight: 700; }
    QLabel#muted { color: %(muted)s; font-size: 12px; }
    QLabel#eyebrow { color: %(muted)s; font-size: 11px; font-weight: 600; }
    QLabel#mono { font-family: 'Consolas'; font-size: 12px; }
    QLabel#notice { background: %(subtle)s; border-radius: 8px; padding: 10px; }
    QLabel#notice[error="true"] { color: %(danger)s; background: %(danger_bg)s; }
    QLabel#badge { background: %(subtle)s; color: %(muted)s; border-radius: 6px; padding: 4px 8px; font-size: 12px; font-weight: 500; }
    QLabel#badge[tone="success"] { color: %(success)s; background: %(success_bg)s; }
    QLabel#badge[tone="warning"] { color: %(warning)s; background: %(warning_bg)s; }
    QLabel#badge[tone="danger"] { color: %(danger)s; background: %(danger_bg)s; }
    QLabel#badge[tone="secure"] { color: %(secure)s; background: %(secure_bg)s; }
    QPushButton { background: %(surface)s; border: 1px solid %(border)s; border-radius: 8px; padding: 8px 12px; font-weight: 600; }
    QPushButton:hover { background: %(subtle)s; border-color: %(accent)s; }
    QPushButton:pressed { background: %(selection)s; }
    QPushButton:focus { border: 2px solid %(accent)s; }
    QPushButton:disabled { color: %(muted)s; background: %(subtle)s; }
    QPushButton#primary { background: #115086; color: white; border-color: #115086; }
    QPushButton#primary:hover { background: #3368A0; border-color: #3368A0; }
    QPushButton#primary:pressed { background: #255282; }
    QPushButton#primary:disabled { background: %(border)s; color: %(muted)s; border-color: %(border)s; }
    QPushButton#danger { color: %(danger)s; background: %(danger_bg)s; border-color: %(danger_bg)s; }
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: %(surface)s; border: 1px solid %(border)s; border-radius: 8px; padding: 8px; selection-background-color: %(selection)s; selection-color: %(text)s; }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: %(accent)s; }
    QComboBox::drop-down { border: none; width: 22px; }
    QComboBox QAbstractItemView { background: %(surface)s; color: %(text)s; selection-background-color: %(selection)s; }
    QListWidget { background: transparent; border: 0; outline: 0; }
    QListWidget::item { padding: 10px; border-radius: 8px; margin: 3px 0; }
    QListWidget::item:hover { background: %(subtle)s; }
    QListWidget::item:selected { background: %(selection)s; color: %(accent)s; }
    QListWidget#managerNavigation::item { padding: 12px 10px; margin: 4px 0; }
    QListWidget#managerNavigation::item:selected { font-weight: 600; }
    QListWidget#workflowCanvas::item { background: %(subtle)s; border: 1px solid %(border)s; padding: 14px; margin: 8px 0; }
    QListWidget#workflowCanvas::item:selected { background: %(selection)s; border-color: %(accent)s; }
    QTableWidget { background: %(surface)s; border: 1px solid %(border)s; border-radius: 12px; gridline-color: %(border)s; outline: 0; selection-background-color: %(selection)s; selection-color: %(text)s; }
    QTableWidget::item { padding: 6px; border-bottom: 1px solid %(border)s; }
    QTableWidget::item:selected, QTableWidget::item:selected:!active { background: %(selection)s; color: %(text)s; }
    QHeaderView::section { background: %(subtle)s; color: %(muted)s; border: 0; padding: 10px 8px; font-weight: 600; font-size: 11px; }
    QTableCornerButton::section { background: %(subtle)s; border: 0; }
    QProgressBar { background: %(border)s; border: 0; border-radius: 3px; height: 6px; }
    QProgressBar::chunk { background: #3368A0; border-radius: 3px; }
    QProgressBar[secure="true"]::chunk { background: %(secure)s; }
    QSlider::groove:horizontal { height: 6px; background: %(border)s; border-radius: 3px; }
    QSlider::sub-page:horizontal { background: #3368A0; border-radius: 3px; }
    QSlider::handle:horizontal { background: #3368A0; border: 2px solid %(surface)s; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
    QSlider::handle:horizontal:hover { background: #66A3BF; }
    QCheckBox { spacing: 8px; }
    QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid %(border)s; border-radius: 5px; background: %(surface)s; }
    QCheckBox::indicator:checked { background: #3368A0; border: 1px solid #3368A0; }
    QCheckBox:focus { color: %(accent)s; }
    QCheckBox[role="toggle"]::indicator { width: 30px; height: 18px; background: transparent; border: 0; }
    QTabWidget::pane { border: 0; }
    QTabBar::tab { background: %(subtle)s; border: 1px solid %(border)s; border-radius: 6px; padding: 8px; margin-right: 4px; }
    QTabBar::tab:selected { background: %(selection)s; color: %(accent)s; }
    QSplitter::handle { background: transparent; }
    QScrollBar:vertical { background: %(background)s; width: 10px; margin: 0; }
    QScrollBar::handle:vertical { background: %(border)s; min-height: 28px; border-radius: 5px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QDialog, QMessageBox { background: %(surface)s; }
    QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 6px; }
    """ % colors

def notice_style(theme, error):
    return "color: " + PALETTES[theme]["danger"] + "; font-weight: 600;" if error else ""
