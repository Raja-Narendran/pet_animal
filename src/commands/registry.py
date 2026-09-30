"""Registry of executable command handlers."""
from typing import Dict, Optional
from .model import ActionType
from .actions.base import BaseCommandHandler
from .actions.open_application import OpenApplicationHandler
from .actions.open_url import OpenUrlHandler
from .actions.help import HelpHandler
from ..services.windows_launcher import BaseLauncher, WindowsLauncher
from ..utils.logger import get_logger

logger = get_logger("registry")


class CommandRegistry:
    """Registry maintaining handlers for different ActionTypes."""

    def __init__(self, launcher: Optional[BaseLauncher] = None):
        self.launcher = launcher or WindowsLauncher()
        self._handlers: Dict[ActionType, BaseCommandHandler] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register the built-in action handlers."""
        self.register(ActionType.OPEN_APPLICATION, OpenApplicationHandler(self.launcher))
        self.register(ActionType.OPEN_URL, OpenUrlHandler(self.launcher))
        self.register(ActionType.SHOW_HELP, HelpHandler())

    def register(self, action_type: ActionType, handler: BaseCommandHandler) -> None:
        """Register a handler for a given ActionType."""
        self._handlers[action_type] = handler
        logger.debug(f"Registered handler for {action_type.value}")

    def get_handler(self, action_type: ActionType) -> Optional[BaseCommandHandler]:
        """Retrieve handler registered for an ActionType."""
        return self._handlers.get(action_type)
