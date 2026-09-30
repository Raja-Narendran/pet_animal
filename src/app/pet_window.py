"""Main floating desktop companion window."""
import json
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QMenu,
    QSystemTrayIcon,
    QApplication,
)
from PyQt6.QtGui import QAction, QIcon, QCursor, QEnterEvent
from PyQt6.QtCore import Qt, QPoint, QTimer

from ..components.pet import PetWidget
from ..components.command_box import CommandBoxWidget
from ..components.response import ResponseBubbleWidget
from ..commands.parser import BaseCommandParser, RuleBasedCommandParser
from ..commands.executor import CommandExecutor
from ..commands.model import ActionType
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("pet_window")


class PetWindow(QWidget):
    """Frameless, transparent, always-on-top desktop companion window."""

    def __init__(
        self,
        parser: Optional[BaseCommandParser] = None,
        executor: Optional[CommandExecutor] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.parser = parser or RuleBasedCommandParser()
        self.executor = executor or CommandExecutor()

        self._init_window_flags()
        self._init_ui()
        self._init_tray_icon()
        self._load_position()
        self._yt_worker = None

        logger.info("Application started. Pet companion loaded successfully.")

    def _init_window_flags(self) -> None:
        """Sets window attributes for a transparent, frameless, always-on-top desktop companion."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _init_ui(self) -> None:
        """Initializes layouts and sub-components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 6, 12, 12)
        main_layout.setSpacing(6)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 1. Subtle top control bar (hidden until hovered)
        self.control_bar = QWidget(self)
        control_layout = QHBoxLayout(self.control_bar)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(6)
        control_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        # Minimize/hide button
        self.min_btn = QPushButton("−", self.control_bar)
        self.min_btn.setFixedSize(22, 22)
        self.min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_btn.setToolTip("Hide Pet (restore from system tray)")
        self.min_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 41, 59, 0.8);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 11px;
                font-size: 13px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: rgba(51, 65, 85, 0.9);
                color: #ffffff;
            }
        """)
        self.min_btn.clicked.connect(self.hide_to_tray)

        # Close button
        self.close_btn = QPushButton("×", self.control_bar)
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close Pet Animal")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 41, 59, 0.8);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 11px;
                font-size: 14px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: #ffffff;
                border-color: #ef4444;
            }
        """)
        self.close_btn.clicked.connect(self.close_application)

        control_layout.addWidget(self.min_btn)
        control_layout.addWidget(self.close_btn)
        self.control_bar.hide()  # Subtle: only show on hover

        main_layout.addWidget(self.control_bar, alignment=Qt.AlignmentFlag.AlignRight)

        # 2. Response speech bubble
        self.response_bubble = ResponseBubbleWidget(self)
        main_layout.addWidget(self.response_bubble, alignment=Qt.AlignmentFlag.AlignCenter)

        # 3. Interactive Pet Widget
        self.pet = PetWidget(parent=self)
        self.pet.pet_clicked.connect(self.toggle_command_box)
        self.pet.drag_finished.connect(self._on_drag_finished)
        main_layout.addWidget(self.pet, alignment=Qt.AlignmentFlag.AlignCenter)

        # 4. Command input box
        self.command_box = CommandBoxWidget(self)
        self.command_box.command_submitted.connect(self._on_command_submitted)
        self.command_box.voice_started.connect(self._on_voice_started)
        self.command_box.voice_error.connect(self._on_voice_error)
        main_layout.addWidget(self.command_box, alignment=Qt.AlignmentFlag.AlignCenter)

    def _init_tray_icon(self) -> None:
        """Initializes system tray icon for background companion management."""
        self.tray_icon = QSystemTrayIcon(self)
        
        # Use first idle frame as tray icon if available
        idle_frames = self.pet.sprite_manager.get_frames("idle")
        if idle_frames and not idle_frames[0].isNull():
            self.tray_icon.setIcon(QIcon(idle_frames[0]))
        
        self.tray_menu = QMenu(self)  # Must be stored as instance attr to prevent GC
        show_action = QAction("Show / Hide Pet", self)
        show_action.triggered.connect(self.toggle_visibility)
        self.tray_menu.addAction(show_action)

        help_action = QAction("Help (Commands)", self)
        help_action.triggered.connect(self.show_help)
        self.tray_menu.addAction(help_action)

        reset_pos_action = QAction("Reset Position", self)
        reset_pos_action.triggered.connect(self._reset_to_default_position)
        self.tray_menu.addAction(reset_pos_action)

        self.tray_menu.addSeparator()

        exit_action = QAction("Exit Pet Animal", self)
        exit_action.triggered.connect(self.close_application)
        self.tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle clicking system tray icon."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_visibility()

    def toggle_visibility(self) -> None:
        """Toggles window visibility."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def hide_to_tray(self) -> None:
        """Hides the desktop companion window to the system tray."""
        self.hide()
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                settings.APP_NAME,
                "Pet Animal is resting in the system tray. Click to wake up!",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def close_application(self) -> None:
        """Saves state and gracefully exits."""
        logger.info("Application closed.")
        self._save_position()
        QApplication.quit()

    def toggle_command_box(self) -> None:
        """Shows or hides the command input box."""
        if self.command_box.isVisible():
            self.command_box.hide()
        else:
            self.command_box.show()
            self.command_box.focus_input()
        self.adjustSize()

    def show_help(self) -> None:
        """Displays help commands via the executor."""
        cmd = self.parser.parse("help")
        result = self.executor.execute(cmd)
        self.response_bubble.show_message(result.message)
        self.pet.set_state(result.pet_state, temporary_ms=5000)
        self.adjustSize()

    def _on_command_submitted(self, text: str) -> None:
        """Handles submitted user command."""
        logger.info(f"Command received: '{text}'")
        
        # Set pet to thinking/working animation while executing
        self.pet.set_state("working")

        # Parse command
        command = self.parser.parse(text)
        logger.info(f"Command parsed: action={command.action.value}, target='{command.target}'")

        # Execute command
        if command.action == ActionType.PLAY_MUSIC and command.target.strip():
            self.pet.set_state("working")
            self.response_bubble.show_message(f"Finding '{command.target}' on YouTube...")
            self.adjustSize()

            from ..services.youtube_worker import YouTubePlayWorker
            self._yt_worker = YouTubePlayWorker(command.target.strip(), parent=self)
            self._yt_worker.playback_started.connect(self._on_youtube_playback_started)
            self._yt_worker.playback_failed.connect(self._on_youtube_playback_failed)
            self._yt_worker.start()
            return

        result = self.executor.execute(command)

        # Show response and update pet state
        self.response_bubble.show_message(result.message)
        self.pet.set_state(result.pet_state, temporary_ms=3000)
        self.adjustSize()

    def _on_youtube_playback_started(self, message: str) -> None:
        """Called when YouTube video is auto-clicked and starts playing."""
        self.response_bubble.show_message(message)
        self.pet.set_state("success", temporary_ms=4000)
        self.adjustSize()

    def _on_youtube_playback_failed(self, message: str) -> None:
        """Called when YouTube playback encounters an error."""
        self.response_bubble.show_message(message)
        self.pet.set_state("error", temporary_ms=3000)
        self.adjustSize()

    def _on_voice_started(self) -> None:
        """Called when microphone starts listening for voice input."""
        self.pet.set_state("thinking")
        self.response_bubble.show_message("Listening... speak your command!", timeout_ms=4000)
        self.adjustSize()

    def _on_voice_error(self, message: str) -> None:
        """Called when voice input encounters an error."""
        self.response_bubble.show_message(f"⚠ {message}", timeout_ms=4000)
        self.pet.set_state("error", temporary_ms=3000)
        self.adjustSize()

    def _show_context_menu(self, pos: QPoint) -> None:
        """Right-click contextual menu on the companion."""
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        toggle_cmd_action = QAction("Toggle Command Box", self)
        toggle_cmd_action.triggered.connect(self.toggle_command_box)
        menu.addAction(toggle_cmd_action)

        # Voice input shortcut in context menu
        from ..services.voice_input import SPEECH_AVAILABLE
        if SPEECH_AVAILABLE and settings.VOICE_ENABLED:
            voice_action = QAction("🎤 Voice Command", self)
            voice_action.triggered.connect(self._trigger_voice_from_menu)
            menu.addAction(voice_action)

        help_action = QAction("Help (Commands)", self)
        help_action.triggered.connect(self.show_help)
        menu.addAction(help_action)

        sleep_action = QAction("Sleep / Rest", self)
        sleep_action.triggered.connect(lambda: self.pet.set_state("sleeping"))
        menu.addAction(sleep_action)

        wake_action = QAction("Wake Up", self)
        wake_action.triggered.connect(lambda: self.pet.set_state("idle"))
        menu.addAction(wake_action)

        reset_pos_action = QAction("Reset Position", self)
        reset_pos_action.triggered.connect(self._reset_to_default_position)
        menu.addAction(reset_pos_action)

        menu.addSeparator()

        close_action = QAction("Exit Pet Animal", self)
        close_action.triggered.connect(self.close_application)
        menu.addAction(close_action)

        menu.exec(self.mapToGlobal(pos))

    # --- Hover effects for subtle control bar ---
    def enterEvent(self, event: QEnterEvent) -> None:
        """Show subtle window controls when mouse enters window region."""
        self.control_bar.show()
        super().enterEvent(event)

    def leaveEvent(self, event: QEnterEvent) -> None:
        """Hide subtle window controls when mouse leaves."""
        self.control_bar.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:
        """Keep controls on screen when the command box or bubble changes size."""
        super().resizeEvent(event)
        self._keep_on_screen()

    def showEvent(self, event) -> None:
        """Clamp the complete window after its initial layout is shown."""
        super().showEvent(event)
        self._keep_on_screen()

    def _keep_on_screen(self) -> None:
        """Fit the window within the available area of its current screen."""
        app = QApplication.instance()
        if not app:
            return
        screen = app.screenAt(self.frameGeometry().center()) or app.screenAt(self.pos()) or app.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        x = max(geom.left(), min(self.x(), geom.right() - self.width() + 1))
        y = max(geom.top(), min(self.y(), geom.bottom() - self.height() + 1))
        if self.pos() != QPoint(x, y):
            self.move(x, y)

    # --- Voice input from context menu ---
    def _trigger_voice_from_menu(self) -> None:
        """Starts voice input from the context menu."""
        if not self.command_box.isVisible():
            self.command_box.show()
            self.adjustSize()
        self.command_box._start_voice_input()

    # --- Position Persistence ---
    def _on_drag_finished(self, new_pos: QPoint) -> None:
        """Called when user completes dragging the companion."""
        self._save_position()

    def _save_position(self) -> None:
        """Saves current window position to user configuration state."""
        try:
            settings.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "x": self.x(),
                "y": self.y(),
                "command_box_visible": self.command_box.isVisible(),
            }
            with open(settings.STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            logger.debug(f"Saved window position: ({self.x()}, {self.y()})")
        except Exception as e:
            logger.warning(f"Could not save state file: {e}")

    def _load_position(self) -> None:
        """Loads saved position and command box visibility, falling back to sensible defaults."""
        state = self._read_saved_state()
        if state:
            x, y = state["x"], state["y"]
            if self._is_position_on_screen(x, y):
                self.move(x, y)
            else:
                self._reset_to_default_position()
            # Restore command box visibility
            if not state.get("command_box_visible", True):
                self.command_box.hide()
            self.adjustSize()
            self._keep_on_screen()
            return

        self._reset_to_default_position()

    def _read_saved_state(self) -> Optional[dict]:
        """Reads full state from state file if valid."""
        if settings.STATE_FILE.exists():
            try:
                with open(settings.STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Validate required keys exist and are numeric
                    return {
                        "x": int(data["x"]),
                        "y": int(data["y"]),
                        "command_box_visible": data.get("command_box_visible", True),
                    }
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                logger.warning(f"Could not read state file, ignoring: {e}")
        return None

    def _is_position_on_screen(self, x: int, y: int) -> bool:
        """Checks if the given coordinate is located on an active screen."""
        app = QApplication.instance()
        if not app:
            return True
        for screen in app.screens():
            if screen.geometry().contains(x + 50, y + 50):
                return True
        return False

    def _reset_to_default_position(self) -> None:
        """Places the companion in a sensible position: bottom-right above the taskbar."""
        app = QApplication.instance()
        if app and app.primaryScreen():
            geom = app.primaryScreen().availableGeometry()
            self.adjustSize()
            target_x = geom.right() - self.width() + 1 - 40
            target_y = geom.bottom() - self.height() + 1 - 40
            self.move(target_x, target_y)
            self._keep_on_screen()
            logger.info(f"Positioned pet at default location: ({target_x}, {target_y})")
        else:
            self.move(400, 300)
