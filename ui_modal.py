#!/usr/bin/env python3
"""
Terminal Modal UI for ForestGump
Floating windows + status bar using rich library + ANSI codes
"""

import sys
import os
import termios
import tty
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.align import Align
except ImportError:
    print("ERROR: rich library required. Install: pip install rich")
    sys.exit(1)


_ORG = '\033[38;5;208m'   # Claude Code orange
_DIM = '\033[2m'
_RST = '\033[0m'
_BLD = '\033[1m'


class RichModalUI:
    """Terminal modal UI with floating windows and persistent status bar."""

    def __init__(self):
        self.console = Console()
        self.width = os.get_terminal_size().columns
        self.height = os.get_terminal_size().lines
        self._setup_scroll_region()

    def _setup_scroll_region(self):
        """Reserve bottom 2 lines for status bar using DECSTBM."""
        rows = self.height
        sys.stdout.write(f'\033[1;{rows-2}r')  # Scroll region: lines 1 to (rows-2)
        sys.stdout.flush()

    def _teardown_scroll_region(self):
        """Restore full scroll region."""
        sys.stdout.write(f'\033[1;{self.height}r')
        sys.stdout.flush()

    def show_modal(self, title: str, content: str, width: Optional[int] = None) -> None:
        """Display a centered floating modal window."""
        width = width or min(70, self.width - 4)

        panel = Panel(
            content,
            title=f' {_ORG}{title}{_RST} ',
            expand=False,
            border_style=f'color({_ORG})',
        )

        # Center the panel
        centered = Align.center(panel)
        self.console.print(centered)

    def show_prompt(self, prompt_text: str, default: str = '') -> str:
        """Show prompt in a modal and get user input."""
        sys.stdout.write(f'\r\033[K')
        sys.stdout.flush()

        # Simple modal prompt
        self.console.print(f'\n {_ORG}›{_RST} {prompt_text}', end='', highlight=False)

        try:
            return input().strip()
        except KeyboardInterrupt:
            return ''

    def show_status(self, mode: str, turn: int, tokens: int) -> None:
        """Display persistent status bar at bottom."""
        mode_fmt = f'{_ORG}auto{_RST}' if mode == 'auto' else f'{_DIM}manual{_RST}'
        status_line = f'  {mode_fmt}  •  {turn}t  •  {tokens}🪙'

        # Position at bottom row using cursor control
        rows = self.height
        sys.stdout.write(f'\033[s')  # Save cursor
        sys.stdout.write(f'\033[{rows}H')  # Move to bottom row
        sys.stdout.write(f'\033[K')  # Clear line
        sys.stdout.write(status_line)
        sys.stdout.write(f'\033[u')  # Restore cursor
        sys.stdout.flush()

    def show_command_prompt(self, cmd: str, options: list) -> str:
        """Show command execution prompt with options.

        options: list of tuples (key, label)
        Returns: pressed key or empty string
        """
        opt_str = '  '.join([f'[{k}]={l}' for k, l in options])
        prompt_line = f'  {_DIM}{opt_str}{_RST}'

        sys.stdout.write(f'\r\033[K')
        sys.stdout.write(prompt_line)
        sys.stdout.flush()

        return self._getch()

    def show_steer_window(self, timeout_s: float = 1.5) -> str:
        """Show brief steer window in auto mode. Returns key pressed or empty."""
        opt_str = f'  {_DIM}[t]=steer  [q]=quit  auto…{_RST}'
        sys.stdout.write(f'\r\033[K{opt_str}')
        sys.stdout.flush()

        import select
        fd = sys.stdin.fileno()
        old_term = termios.tcgetattr(fd)
        ch = ''
        try:
            tty.setraw(fd)
            rlist, _, _ = select.select([sys.stdin], [], [], timeout_s)
            if rlist:
                ch = sys.stdin.read(1)
        except Exception:
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_term)

        sys.stdout.write('\r\033[K')
        sys.stdout.flush()
        return ch

    def _getch(self) -> str:
        """Read single character from terminal."""
        fd = sys.stdin.fileno()
        old_term = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
        return ch

    def clear(self) -> None:
        """Clear screen."""
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()

    def cleanup(self) -> None:
        """Restore terminal state."""
        self._teardown_scroll_region()
        self.clear()


# Global UI instance
_ui: Optional[RichModalUI] = None


def init_ui() -> RichModalUI:
    """Initialize global UI."""
    global _ui
    _ui = RichModalUI()
    return _ui


def get_ui() -> RichModalUI:
    """Get global UI instance."""
    global _ui
    if _ui is None:
        _ui = RichModalUI()
    return _ui
