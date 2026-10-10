"""Render bundled SVG icons in theme colors. Never retrieves remote resources."""
from functools import lru_cache
from PyQt6.QtCore import Qt, QSize, QRectF
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QPushButton, QLabel, QCheckBox
from ...config.settings import settings
from .theme import PALETTES
ALIASES = {'brain': 'psychology', 'zap': 'terminal', 'arrow-right': 'arrow_forward'}
NAV_ICONS = ('dashboard', 'psychology', 'terminal', 'account_tree', 'palette', 'history', 'tune')

@lru_cache(maxsize=256)
def icon(name, color='#115086', size=20, dpr=1.0):
    name = ALIASES.get(name, name)
    path = settings.BASE_DIR / 'assets/ui/stitch' / (name + '.svg')
    if not path.is_file():
        path = settings.BASE_DIR / 'assets/ui' / (name + '.svg')
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(round(size * dpr), round(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    # Use logical bounds rather than physical device pixels at high DPI.
    bounds = QRectF(0, 0, size, size)
    renderer.render(painter, bounds)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(bounds, QColor(color))
    painter.end()
    return QIcon(pixmap)

def apply_icons(root, theme):
    colors = PALETTES[theme]
    for item in root.findChildren(QPushButton):
        name = item.property('iconName')
        if name:
            color = '#FFFFFF' if item.objectName() == 'primary' else colors['danger'] if item.objectName() == 'danger' else colors['accent']
            item.setIcon(icon(name, color, 16, root.devicePixelRatioF()))
            item.setIconSize(QSize(16, 16))

    for item in root.findChildren(QLabel):
        name = item.property('iconName')
        if name:
            size = item.property('iconSize') or 24
            item.setPixmap(icon(name, colors['accent'], size, root.devicePixelRatioF()).pixmap(size, size))
    for item in root.findChildren(QCheckBox):
        if item.property('role') == 'toggle':
            item.setProperty('switchOn', '#3368A0')
            item.setProperty('switchOff', colors['border'])
            item.update()


@lru_cache(maxsize=128)
def inline_svg_icon(svg_str, size=20, dpr=1.0):
    from PyQt6.QtCore import QByteArray
    renderer = QSvgRenderer(QByteArray(svg_str.strip().encode('utf-8')))
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(round(size * dpr), round(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    bounds = QRectF(0, 0, size, size)
    renderer.render(painter, bounds)
    painter.end()
    return QIcon(pixmap)


GEAR_SVG = """<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"/>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
</svg>"""

MOON_SVG = """<svg viewBox="0 0 24 24" fill="{color}">
  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
</svg>"""

SUN_SVG = """<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="5"/>
  <line x1="12" y1="1" x2="12" y2="3"/>
  <line x1="12" y1="21" x2="12" y2="23"/>
  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
  <line x1="1" y1="12" x2="3" y2="12"/>
  <line x1="21" y1="12" x2="23" y2="12"/>
  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
</svg>"""

SPOTIFY_SVG = """<svg viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="11" fill="#1ED760"/>
  <path d="M6.5 9.8c3.8-1.2 8.3-.9 11.5.9" stroke="#121212" stroke-width="2" stroke-linecap="round" fill="none"/>
  <path d="M7.4 12.8c3.2-1 6.9-.7 9.6.8" stroke="#121212" stroke-width="1.8" stroke-linecap="round" fill="none"/>
  <path d="M8.2 15.6c2.5-.8 5.4-.5 7.6.7" stroke="#121212" stroke-width="1.6" stroke-linecap="round" fill="none"/>
</svg>"""

YOUTUBE_SVG = """<svg viewBox="0 0 24 24">
  <rect x="2" y="5" width="20" height="14" rx="4" fill="#FF0000"/>
  <polygon points="10,8.5 16,12 10,15.5" fill="#FFFFFF"/>
</svg>"""

LIGHTNING_SVG = """<svg viewBox="0 0 24 24" fill="{color}" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
</svg>"""

GLOBE_SVG = """<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <line x1="2" y1="12" x2="22" y2="12"/>
  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
</svg>"""

DOT_SVG = """<svg viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="5" fill="{color}"/>
</svg>"""

INFO_SVG = """<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <line x1="12" y1="16" x2="12" y2="12"/>
  <circle cx="12" cy="8" r="1.2" fill="{color}"/>
</svg>"""

SAVE_TRAY_SVG = """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>
  <polyline points="7 11 12 16 17 11"/>
  <line x1="12" y1="4" x2="12" y2="16"/>
</svg>"""

