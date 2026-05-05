"""Color utilities for terminal output with ANSI color codes."""

import re

# ANSI Color Constants
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"
BLACK = "\033[90m"
RESET = "\033[0m"
BOLD = "\033[1m"


def get_color_code(color_name: str) -> str:
    """Get ANSI color code from color name.
    
    Args:
        color_name: Name of color (e.g., 'red', 'green', 'blue')
    
    Returns:
        ANSI color code string
    """
    color_map = {
        "red": RED,
        "green": GREEN,
        "yellow": YELLOW,
        "blue": BLUE,
        "cyan": CYAN,
        "magenta": MAGENTA,
        "white": WHITE,
        "black": BLACK,
    }
    return color_map.get(color_name.lower(), "")


def colorize(text: str, color: str) -> str:
    """Colorize text with ANSI color code.
    
    Args:
        text: Text to colorize
        color: Color name (e.g., 'red', 'green', 'blue')
    
    Returns:
        Colorized text with ANSI codes
    """
    color_code = get_color_code(color)
    if not color_code:
        return text
    return f"{color_code}{text}{RESET}"


def strip_colors(text: str) -> str:
    """Remove ANSI color codes from text.
    
    Args:
        text: Text potentially containing ANSI codes
    
    Returns:
        Text with ANSI codes removed
    """
    # Pattern to match ANSI escape sequences
    ansi_pattern = r"\033\[[0-9;]*m"
    return re.sub(ansi_pattern, "", text)
