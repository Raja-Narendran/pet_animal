"""Speech bubble widget for displaying pet command responses."""
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtSignal, QPoint, QSize
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("response_bubble")


class ResponseBubbleWidget(QWidget):
    """Floating speech/response bubble above the pet.
    
    Note: Uses manual paintEvent instead of QGraphicsDropShadowEffect
    because drop shadow effects cause ghost-rendering artifacts on
    transparent frameless windows (WA_TranslucentBackground).
    """

    bubble_shown = pyqtSignal()
    bubble_hidden = pyqtSignal()
    application_selected = pyqtSignal(str)

    BORDER_RADIUS = 12
    SHADOW_OFFSET_Y = 3
    SHADOW_PADDING = 6

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._owner = parent
        self.suggestion_mode = False
        self._init_ui()

        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.hide)

    def _init_ui(self) -> None:
        self.setMinimumWidth(180 + self.SHADOW_PADDING * 2)
        self.setMaximumWidth(280 + self.SHADOW_PADDING * 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            14 + self.SHADOW_PADDING,
            10 + self.SHADOW_PADDING,
            14 + self.SHADOW_PADDING,
            10 + self.SHADOW_PADDING,
        )
        layout.setSpacing(4)

        self.label = QLabel("", self)
        self.label.setFont(QFont("Segoe UI", 9))
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                color: #f8fafc;
                background: transparent;
                line-height: 1.3;
            }
        """)
        layout.addWidget(self.label)

        self.suggestion_list = QListWidget(self)
        self.suggestion_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.suggestion_list.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.suggestion_list.setAccessibleName('Application suggestions')
        self.suggestion_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.suggestion_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.suggestion_list.setUniformItemSizes(True)
        self.suggestion_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.suggestion_list.setStyleSheet('''
            QListWidget { color: #f8fafc; background: transparent; border: none; font: 12px "Segoe UI"; }
            QListWidget::item { border-radius: 6px; padding-left: 8px; }
            QListWidget::item:selected { color: #ffffff; background: #2563eb; }
            QListWidget::item:hover:!selected { background: #334155; }
        ''')
        self.suggestion_list.itemClicked.connect(
            lambda item: self.application_selected.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.suggestion_list.hide()
        layout.addWidget(self.suggestion_list)

        self.hide()

    def update_position(self, owner: Optional[QWidget] = None) -> None:
        """Positions the floating bubble directly above the companion pet."""
        target_win = owner or self._owner
        if not target_win or not target_win.isVisible():
            return

        pet_widget = getattr(target_win, "pet", None)
        if pet_widget and pet_widget.isVisible():
            pet_pos = pet_widget.mapToGlobal(QPoint(0, 0))
            center_x = pet_pos.x() + (pet_widget.width() - self.width()) // 2
            target_y = pet_pos.y() - self.height() - 6
        else:
            anchor = getattr(target_win, 'command_box', target_win)
            win_pos = anchor.mapToGlobal(QPoint(0, 0))
            center_x = win_pos.x() + (anchor.width() - self.width()) // 2
            target_y = win_pos.y() - self.height() - 6

        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            screen = app.screenAt(QPoint(center_x, target_y)) or app.screenAt(target_win.pos()) or app.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                center_x = max(geom.left() + 4, min(center_x, geom.right() - self.width() + 1 - 4))
                target_y = max(geom.top() + 4, min(target_y, geom.bottom() - self.height() + 1 - 4))

        self.move(center_x, target_y)

    def paintEvent(self, event) -> None:
        """Manually paints the rounded dark background and subtle shadow.
        
        This replaces QGraphicsDropShadowEffect which causes ghost-rendering
        on transparent frameless windows.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pad = self.SHADOW_PADDING
        box_rect = QRectF(
            pad, pad,
            self.width() - pad * 2,
            self.height() - pad * 2,
        )

        # Draw subtle shadow
        shadow_rect = box_rect.adjusted(-1, 0, 1, self.SHADOW_OFFSET_Y)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 55))

        # Draw main background
        bg_path = QPainterPath()
        bg_path.addRoundedRect(box_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)
        painter.fillPath(bg_path, QColor(15, 23, 42, 240))

        # Draw border
        painter.setPen(QPen(QColor(255, 255, 255, 51), 1.0))
        painter.drawRoundedRect(box_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)

        painter.end()

    def show_message(self, message: str, timeout_ms: int = settings.BUBBLE_TIMEOUT_MS) -> None:
        """Displays a message and schedules auto-hiding."""
        self.suggestion_mode = False
        self.suggestion_list.hide()
        self.suggestion_list.clear()
        self.label.setText(message)
        self.adjustSize()
        self.update_position()
        self.show()
        self.raise_()
        self.bubble_shown.emit()
        logger.debug("Response bubble displayed")

        if self.auto_hide_timer.isActive():
            self.auto_hide_timer.stop()

        if timeout_ms > 0:
            self.auto_hide_timer.start(timeout_ms)

    @property
    def selected_application(self):
        item = self.suggestion_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def show_suggestions(self, entries, selected_target=None):
        """Show clickable, scrollable choices without taking focus from the input."""
        self.auto_hide_timer.stop()
        self.suggestion_mode = True
        self.label.setText('Open an app · ↑ ↓ to choose' if entries else 'No matching apps. Add apps in Commands.')
        self.suggestion_list.clear()
        names = [entry.display_name.casefold() for entry in entries]
        selected_row = 0
        for index, entry in enumerate(entries):
            name = entry.display_name
            if names.count(name.casefold()) > 1 and entry.aliases:
                name += ' · @' + entry.aliases[0]
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, entry.target)
            item.setToolTip(entry.display_name + '\n' + ', '.join(entry.aliases))
            item.setSizeHint(QSize(0, 32))
            self.suggestion_list.addItem(item)
            if entry.target == selected_target:
                selected_row = index
        self.suggestion_list.setFixedHeight(min(6, len(entries)) * 32 + 2)
        self.suggestion_list.setVisible(bool(entries))
        if entries:
            self.suggestion_list.setCurrentRow(selected_row)
            self.suggestion_list.scrollToItem(self.suggestion_list.currentItem())
        self.adjustSize()
        self.update_position()
        self.show()
        self.raise_()
        self.bubble_shown.emit()

    def move_selection(self, step):
        count = self.suggestion_list.count()
        if count:
            self.suggestion_list.setCurrentRow(max(0, min(count - 1, self.suggestion_list.currentRow() + step)))
            self.suggestion_list.scrollToItem(self.suggestion_list.currentItem())

    def dismiss_suggestions(self):
        if self.suggestion_mode:
            self.suggestion_mode = False
            self.hide()

    def hideEvent(self, event) -> None:
        self.auto_hide_timer.stop()
        self.suggestion_mode = False
        super().hideEvent(event)
        self.bubble_hidden.emit()
