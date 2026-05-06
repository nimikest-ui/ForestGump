#!/usr/bin/env python3
"""
Hermes-compatible theme system for ForestGump.
Defines color palette and styling constants.
"""

import os

# Enable color output via COLOR=1 env var
_USE_COLOR = os.environ.get('COLOR', '1') == '1'

# ANSI escape codes for Hermes gold/amber/bronze theme
class Colors:
    """Color palette matching Hermes aesthetic."""

    # Basic colors
    RESET = '\033[0m' if _USE_COLOR else ''
    BOLD = '\033[1m' if _USE_COLOR else ''
    DIM = '\033[2m' if _USE_COLOR else ''

    # Primary theme colors (Hermes)
    GOLD = '\033[1;38;2;255;215;0m' if _USE_COLOR else ''      # #FFD700
    AMBER = '\033[38;2;255;191;0m' if _USE_COLOR else ''       # #FFBF00
    BRONZE = '\033[38;2;205;127;50m' if _USE_COLOR else ''     # #CD7F32

    # Status colors
    GREEN = '\033[32m' if _USE_COLOR else ''                   # Success
    RED = '\033[31m' if _USE_COLOR else ''                     # Error
    YELLOW = '\033[33m' if _USE_COLOR else ''                  # Warning
    CYAN = '\033[36m' if _USE_COLOR else ''                    # Info
    GRAY = '\033[90m' if _USE_COLOR else ''                    # Muted

    # Semantic colors
    SUCCESS = GREEN
    ERROR = RED
    WARNING = YELLOW
    INFO = CYAN
    MUTED = GRAY
    PRIMARY = GOLD
    SECONDARY = AMBER
    ACCENT = BRONZE


class Symbols:
    """Terminal-friendly symbols."""

    CHECK = '✓'
    CROSS = '✗'
    ARROW = '→'
    BULLET = '•'
    STAR = '★'
    CIRCLE = '●'
    SQUARE = '■'
    DIAMOND = '◆'


def fmt(text: str, color: str = '', bold: bool = False, dim: bool = False) -> str:
    """
    Format text with color and style.

    Args:
        text: Text to format
        color: Color code (from Colors class)
        bold: Make text bold
        dim: Make text dim

    Returns:
        Formatted text with ANSI codes
    """
    if not _USE_COLOR:
        return text

    codes = []
    if dim:
        codes.append(Colors.DIM)
    if bold:
        codes.append(Colors.BOLD)
    if color:
        codes.append(color)

    if codes:
        return ''.join(codes) + text + Colors.RESET
    return text


def banner(text: str) -> str:
    """Format a section banner."""
    return fmt(text, Colors.GOLD, bold=True)


def success(text: str) -> str:
    """Format success message."""
    return fmt(text, Colors.GREEN)


def error(text: str) -> str:
    """Format error message."""
    return fmt(text, Colors.RED)


def warning(text: str) -> str:
    """Format warning message."""
    return fmt(text, Colors.YELLOW)


def info(text: str) -> str:
    """Format info message."""
    return fmt(text, Colors.CYAN)


def muted(text: str) -> str:
    """Format muted text."""
    return fmt(text, Colors.GRAY, dim=True)
