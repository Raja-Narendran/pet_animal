"""Small composable native widgets shared by the seven Manager pages."""
from PyQt6.QtCore import Qt, QSize, QRect, QPoint, QRectF
from PyQt6.QtWidgets import QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QBoxLayout, QLayout, QSizePolicy, QStyle, QCheckBox, QStyleOptionButton, QComboBox, QSlider
from PyQt6.QtGui import QPainter, QColor, QPalette, QIcon
from .icons import icon

def label(value, role=''):
    item = QLabel(str(value))
    item.setWordWrap(True)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setObjectName(role)
    return item

def button(title, callback, primary=False, icon=None):
    item = QPushButton(title)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.setMinimumHeight(40)
    item.setObjectName('primary' if primary else '')
    glyphs = {
        'Edit memory': 'edit', 'Delete memory': 'delete', 'Reveal value': 'visibility',
        'Reveal encrypted value': 'visibility', 'Save preferences': 'save', 'Save search settings': 'save',
        'Add folder': 'folder_open', 'Choose es.exe': 'computer', 'Export configuration': 'download',
        'Import configuration': 'upload_file', 'Export memories': 'download',
        'Create database backup': 'lock', 'Restore database backup': 'history',
        'Clear command history': 'delete', 'Routine run details': 'description',
    }
    icon = icon or glyphs.get(title)
    if icon:
        item.setProperty('iconName', icon)
    if title.startswith('Delete ') or title.startswith('Clear '):
        item.setObjectName('danger')
    item.clicked.connect(callback)
    return item

def badge(value, tone='neutral'):
    item = label(value, 'badge')
    item.setProperty('tone', tone)
    item.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return item

def card(title=None):
    frame = QFrame()
    frame.setObjectName('card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    if title:
        layout.addWidget(label(title, 'subheading'))
    return frame, layout

class ResponsiveRow(QWidget):
    """Reflow the same widgets without destroying form state or signal bindings."""
    def __init__(self, manager, widgets=(), stretches=()):
        super().__init__()
        self.manager = manager
        self.box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(16)
        for i, widget in enumerate(widgets):
            self.box.addWidget(widget, stretches[i] if i < len(stretches) else 1, Qt.AlignmentFlag.AlignTop)
        self.set_compact(manager.width() < 1100)
        manager.responsive_rows.append(self)
    def set_compact(self, compact):
        self.box.setDirection(QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight)

class FlowLayout(QLayout):
    """Wrap action buttons at narrow widths, preserving keyboard order."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(8)
    def addItem(self, item): self.items.append(item)
    def count(self): return len(self.items)
    def itemAt(self, index): return self.items[index] if 0 <= index < len(self.items) else None
    def takeAt(self, index): return self.items.pop(index) if 0 <= index < len(self.items) else None
    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self.arrange(QRect(0, 0, width, 0), True)
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.arrange(rect, False)
    def sizeHint(self):
        hints = [item.sizeHint() for item in self.items]
        width = sum(hint.width() for hint in hints) + self.spacing() * max(0, len(hints) - 1)
        return QSize(width, max((hint.height() for hint in hints), default=0))
    def minimumSize(self):
        size = QSize()
        for item in self.items: size = size.expandedTo(item.minimumSize())
        return size
    def arrange(self, rect, test):
        x, y, height = rect.x(), rect.y(), 0
        for item in self.items:
            hint = item.sizeHint()
            if x > rect.x() and x + hint.width() > rect.right() + 1:
                x, y, height = rect.x(), y + height + self.spacing(), 0
            if not test: item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.spacing()
            height = max(height, hint.height())
        return y + height - rect.y()

def actions(items):
    widget = QWidget()
    layout = FlowLayout(widget)
    for item in items: layout.addWidget(item)
    return widget

def heading(manager, title, subtitle, controls=()):
    copy = QWidget()
    layout = QVBoxLayout(copy)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    layout.addWidget(label(title, 'heading'))
    layout.addWidget(label(subtitle, 'muted'))
    control_area = QWidget()
    control_layout = QHBoxLayout(control_area)
    control_layout.setContentsMargins(0, 0, 0, 0)
    control_layout.addStretch()
    control_layout.addWidget(actions(controls), 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    row = ResponsiveRow(manager, (copy, control_area), (2, 1))
    manager.content_layout.addWidget(row)

class Toggle(QCheckBox):
    """A switch presentation retaining QCheckBox input and accessibility semantics."""
    def __init__(self, text=''):
        super().__init__(text)
        self.setProperty('role', 'toggle')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.property('switchOn') or '#3368A0') if self.isChecked() else QColor(self.property('switchOff') or '#E2E8F0')
        if not self.isEnabled(): color.setAlpha(110)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 9, 9)
        painter.setBrush(QColor('#FFFFFF'))
        x = rect.right() - 8 if self.isChecked() else rect.left() + 8
        painter.drawEllipse(QPoint(x, rect.center().y()), 6, 6)
        painter.end()

class ComboBox(QComboBox):
    """Draw the dropdown glyph in the active palette without duplicate SVG variants."""
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = self.palette().color(QPalette.ColorRole.Text).name()
        icon('expand_more', color, 16, self.devicePixelRatioF()).paint(painter, self.width() - 24, (self.height() - 16) // 2, 16, 16)
        painter.end()

class NoScrollSlider(QSlider):
    """QSlider that ignores mouse wheel events to prevent accidental value changes while scrolling."""
    def wheelEvent(self, event):
        event.ignore()


class SegmentedControl(QComboBox):
    """A two-way segmented toggle presenting choices as pill segments while keeping QComboBox API."""
    def __init__(self, parent=None, is_dark=True):
        super().__init__(parent)
        self.is_dark = is_dark
        self._buttons = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self._layout.setSpacing(4)
        self.setFixedHeight(44)
        self._sync_styles()
        self.currentIndexChanged.connect(self._sync_buttons)

    def showPopup(self):
        pass

    def hidePopup(self):
        pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border_col = QColor("#1e2638" if self.is_dark else "#e2e8f0")
        bg_col = QColor("#090e1a" if self.is_dark else "#f1f5f9")
        painter.setPen(border_col)
        painter.setBrush(bg_col)
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 10, 10)
        painter.end()

    def set_theme(self, is_dark):
        self.is_dark = is_dark
        self._sync_styles()
        self._sync_buttons(self.currentIndex())
        self.update()

    def _sync_styles(self):
        active_bg = "#2563eb"
        active_fg = "#ffffff"
        inactive_fg = "#94a3b8" if self.is_dark else "#64748b"
        hover_bg = "#1e293b" if self.is_dark else "#e2e8f0"
        hover_fg = "#f1f5f9" if self.is_dark else "#1f2937"
        self.setStyleSheet(f"""
            QComboBox {{ background: transparent; border: none; }}
            QPushButton[segment="active"] {{
                background-color: {active_bg};
                color: {active_fg};
                border: none;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
                padding: 0px 14px;
            }}
            QPushButton[segment="inactive"] {{
                background-color: transparent;
                color: {inactive_fg};
                border: none;
                border-radius: 8px;
                font-weight: 500;
                font-size: 13px;
                padding: 0px 14px;
            }}
            QPushButton[segment="inactive"]:hover {{
                background-color: {hover_bg};
                color: {hover_fg};
            }}
        """)

    def addItem(self, *args, icon=None, display_text=None, icon_active=None, icon_inactive=None):
        if args and isinstance(args[0], QIcon):
            btn_icon = args[0]
            text = args[1] if len(args) > 1 else ""
            data = args[2] if len(args) > 2 else None
            super().addItem(btn_icon, text, data)
        else:
            text = args[0] if len(args) > 0 else ""
            data = args[1] if len(args) > 1 else None
            btn_icon = icon
            super().addItem(text, data)
        idx = self.count() - 1
        btn = QPushButton(display_text or text)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn._icon_active = icon_active or btn_icon
        btn._icon_inactive = icon_inactive or btn_icon
        btn.clicked.connect(lambda _, i=idx: self.setCurrentIndex(i))
        self._buttons.append(btn)
        self._layout.addWidget(btn, 1)
        self._sync_buttons(self.currentIndex())

    def addItems(self, texts):
        for t in texts:
            self.addItem(t)

    def _sync_buttons(self, index):
        for i, btn in enumerate(self._buttons):
            is_active = (i == index)
            btn.setProperty("segment", "active" if is_active else "inactive")
            curr_icon = btn._icon_active if is_active else btn._icon_inactive
            if curr_icon:
                btn.setIcon(curr_icon)
                btn.setIconSize(QSize(18, 18))
            else:
                btn.setIcon(QIcon())
            btn.style().unpolish(btn)
            btn.style().polish(btn)

