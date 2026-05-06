#!/usr/bin/env python3
"""
Terminal UI components for ForestGump.
Provides status bar, progress display, and formatting utilities.
"""

import time
import os
from typing import Optional, Tuple
from datetime import datetime

import theme


class StatusBar:
    """
    Live status bar for agent execution.

    Displays:
    - Turn count (current/max)
    - Elapsed time
    - Model provider/name
    - Token usage
    - Connection status
    """

    def __init__(self, task: str, provider: str, model: str, max_turns: int = 50):
        """Initialize status bar."""
        self.task = task
        self.provider = provider
        self.model = model
        self.max_turns = max_turns
        self.current_turn = 0
        self.start_time = time.time()
        self.tokens_used = 0
        self.tokens_estimated_max = 0
        self.is_connected = True
        self.current_action = ''

    def update(
        self,
        turn: Optional[int] = None,
        tokens: Optional[int] = None,
        action: Optional[str] = None,
        connected: Optional[bool] = None,
    ) -> None:
        """Update status bar values."""
        if turn is not None:
            self.current_turn = turn
        if tokens is not None:
            self.tokens_used = tokens
        if action is not None:
            self.current_action = action
        if connected is not None:
            self.is_connected = connected

    def render(self, width: Optional[int] = None) -> str:
        """
        Render the status bar.

        Args:
            width: Terminal width (auto-detect if None)

        Returns:
            Formatted status bar string
        """
        if width is None:
            width = os.get_terminal_size((80, 24)).columns

        elapsed = time.time() - self.start_time
        elapsed_str = self._format_duration(elapsed)

        # Connection indicator
        conn_icon = theme.Colors.GREEN + '●' if self.is_connected else theme.Colors.RED + '●'

        # Token usage
        if self.tokens_estimated_max > 0:
            token_str = f'{self.tokens_used}/{self.tokens_estimated_max} tok'
        else:
            token_str = f'{self.tokens_used} tok'

        # Build status
        parts = [
            f'{conn_icon}{theme.Colors.RESET}',
            f'Turn {self.current_turn}/{self.max_turns}',
            f'{elapsed_str}',
            f'{self.provider}/{self.model}',
            token_str,
        ]

        if self.current_action:
            action_short = self.current_action[:20] + '...' if len(self.current_action) > 20 else self.current_action
            parts.append(f'{theme.Colors.AMBER}{action_short}{theme.Colors.RESET}')

        status = ' | '.join(parts)

        # Truncate if too long
        if len(status) > width - 2:
            status = status[:width - 5] + '...'

        return f' {status} '

    def _format_duration(self, seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f'{hours}:{minutes:02d}:{secs:02d}'
        elif minutes > 0:
            return f'{minutes}:{secs:02d}'
        else:
            return f'{secs}s'


class ProgressBar:
    """Simple progress bar for long-running operations."""

    def __init__(self, total: int, width: int = 40):
        """Initialize progress bar."""
        self.total = max(1, total)
        self.width = width
        self.current = 0

    def update(self, current: int) -> None:
        """Update progress."""
        self.current = min(current, self.total)

    def render(self) -> str:
        """Render progress bar."""
        if self.total == 0:
            return '[' + '=' * self.width + ']'

        progress = self.current / self.total
        filled = int(progress * self.width)

        bar = '[' + '=' * filled + ' ' * (self.width - filled) + ']'
        percentage = f' {progress * 100:.0f}%'

        return bar + percentage


class Panel:
    """Formatted panel for displaying content."""

    def __init__(self, title: str = '', border: bool = True, color: str = theme.Colors.GOLD):
        """Initialize panel."""
        self.title = title
        self.border = border
        self.color = color
        self.lines = []

    def add_line(self, text: str) -> None:
        """Add a line to the panel."""
        self.lines.append(text)

    def add_lines(self, lines: list[str]) -> None:
        """Add multiple lines."""
        self.lines.extend(lines)

    def render(self, width: int = 80) -> str:
        """Render the panel."""
        if not self.border:
            return '\n'.join(self.lines)

        # Simple border with title
        if self.title:
            title_str = f' {self.title} '
            border_width = width - len(title_str) - 2
            top = self.color + '┌' + title_str + '─' * max(0, border_width) + '┐' + theme.Colors.RESET
        else:
            top = self.color + '┌' + '─' * (width - 2) + '┐' + theme.Colors.RESET

        bottom = self.color + '└' + '─' * (width - 2) + '┘' + theme.Colors.RESET

        content = []
        for line in self.lines:
            # Truncate long lines
            if len(line) > width - 4:
                line = line[:width - 7] + '...'
            content.append(self.color + '│ ' + theme.Colors.RESET + line.ljust(width - 4) + ' ' + self.color + '│' + theme.Colors.RESET)

        return top + '\n' + '\n'.join(content) + '\n' + bottom


def print_table(headers: list[str], rows: list[list[str]], width: int = 80) -> str:
    """
    Format data as an ASCII table.

    Args:
        headers: Column headers
        rows: List of rows (each row is a list of strings)
        width: Terminal width

    Returns:
        Formatted table string
    """
    if not headers or not rows:
        return ''

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Build separator
    separator = '  '.join(['─' * w for w in col_widths])

    # Build header
    header_cells = []
    for h, w in zip(headers, col_widths):
        header_cells.append(theme.fmt(h.ljust(w), theme.Colors.GOLD, bold=True))
    header_row = '  '.join(header_cells)

    # Build data rows
    data_rows = []
    for row in rows:
        cells = [str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)]
        data_rows.append('  '.join(cells))

    return header_row + '\n' + separator + '\n' + '\n'.join(data_rows)
