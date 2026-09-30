"""Unit tests for RuleBasedCommandParser."""
import pytest
from src.commands.parser import RuleBasedCommandParser
from src.commands.model import ActionType


@pytest.fixture
def parser():
    return RuleBasedCommandParser()


class TestCommandParserChrome:
    """Test all variations of opening Chrome."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "open chrome",
            "Open Chrome",
            "OPEN CHROME",
            "open   chrome",
            "launch chrome",
            "Launch Chrome",
            "start chrome",
            "Start Chrome",
            "open google chrome",
            "Open Google Chrome",
            "launch google chrome",
            "chrome",
        ],
    )
    def test_chrome_variations(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.OPEN_APPLICATION
        assert cmd.target == "chrome"


class TestCommandParserApplications:
    """Test opening notepad, calculator, explorer, and vscode."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "open notepad",
            "launch notepad",
            "start notepad",
            "notepad",
        ],
    )
    def test_notepad(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.OPEN_APPLICATION
        assert cmd.target == "notepad"

    @pytest.mark.parametrize(
        "phrase",
        [
            "open calculator",
            "launch calculator",
            "start calculator",
            "open calc",
            "calculator",
            "calc",
        ],
    )
    def test_calculator(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.OPEN_APPLICATION
        assert cmd.target == "calculator"

    @pytest.mark.parametrize(
        "phrase",
        [
            "open explorer",
            "open file explorer",
            "launch explorer",
            "start explorer",
            "open windows explorer",
            "explorer",
        ],
    )
    def test_explorer(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.OPEN_APPLICATION
        assert cmd.target == "explorer"

    @pytest.mark.parametrize(
        "phrase",
        [
            "open vscode",
            "open vs code",
            "launch vscode",
            "start vscode",
            "open visual studio code",
            "vscode",
        ],
    )
    def test_vscode(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.OPEN_APPLICATION
        assert cmd.target == "vscode"


class TestCommandParserUrls:
    """Test opening YouTube and Google."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "open youtube",
            "launch youtube",
            "start youtube",
            "youtube",
        ],
    )
    def test_youtube(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.OPEN_URL
        assert cmd.target == "https://www.youtube.com"

    @pytest.mark.parametrize(
        "phrase",
        [
            "open google",
            "launch google",
            "start google",
            "google",
        ],
    )
    def test_google(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.OPEN_URL
        assert cmd.target == "https://www.google.com"


class TestCommandParserHelpAndEmpty:
    """Test help commands and empty inputs."""

    @pytest.mark.parametrize("phrase", ["help", "Help", "HELP", "commands", "?", "show help"])
    def test_help(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.SHOW_HELP

    @pytest.mark.parametrize("phrase", ["", "   ", "\t", "\n"])
    def test_empty_input(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.EMPTY


class TestCommandParserUnsupportedAndSecurity:
    """Ensure unsupported commands and potentially malicious strings do NOT resolve to arbitrary actions."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "open photoshop",
            "do something",
            "hello",
            "delete files",
            "rm -rf /",
            "powershell Remove-Item -Recurse",
            "cmd /c calc.exe",
            "open evilapp",
            "run format c:",
        ],
    )
    def test_unsupported_commands(self, parser, phrase):
        cmd = parser.parse(phrase)
        assert cmd.action == ActionType.UNKNOWN
        # Must not be an executable action
        assert cmd.action != ActionType.OPEN_APPLICATION
        assert cmd.action != ActionType.OPEN_URL
