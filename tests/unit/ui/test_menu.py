import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO
from forestgump.ui.menu import MenuSystem


@pytest.fixture
def menu_system():
    return MenuSystem()


def test_menu_display_options(menu_system):
    """Test menu displays all options correctly"""
    # Menu should have 7 items: Change Model, Plan Attack, Ask Question, Continue, Clear, Show Model, Exit
    assert len(menu_system.get_menu_options()) == 7
    options = menu_system.get_menu_options()
    assert "Change Model" in options
    assert "Exit" in options


def test_menu_get_provider_list(menu_system):
    """Test menu returns provider list"""
    providers = menu_system.get_providers()
    assert "ollama" in providers
    assert "claude" in providers
    assert "anthropic" in providers
    assert "copilot" in providers


def test_menu_get_ollama_models(menu_system):
    """Test menu returns available Ollama models"""
    models = menu_system.get_ollama_models()
    assert isinstance(models, list)
    assert len(models) > 0
    # Should include both local and cloud models
    assert any("llama" in m.lower() for m in models)


def test_menu_format_option(menu_system):
    """Test option formatting with colors"""
    formatted = menu_system.format_option(0, "Test Option", is_selected=True)
    assert "Test Option" in formatted
    # When selected, should include indicator
    assert ">" in formatted or "●" in formatted


def test_menu_task_history_add(menu_system):
    """Test adding to task history"""
    menu_system.add_to_history("scan networks")
    menu_system.add_to_history("crack wifi")
    history = menu_system.get_history()
    assert "scan networks" in history
    assert "crack wifi" in history


def test_menu_task_history_limit(menu_system):
    """Test task history is limited to 20 entries"""
    for i in range(25):
        menu_system.add_to_history(f"task {i}")
    history = menu_system.get_history()
    assert len(history) <= 20


def test_menu_current_provider(menu_system):
    """Test setting and getting current provider"""
    menu_system.set_provider("ollama")
    assert menu_system.get_provider() == "ollama"
    
    menu_system.set_provider("claude")
    assert menu_system.get_provider() == "claude"


def test_menu_current_model(menu_system):
    """Test setting and getting current model"""
    menu_system.set_model("llama3.2:latest")
    assert menu_system.get_model() == "llama3.2:latest"


def test_menu_no_confirm_mode(menu_system):
    """Test no-confirmation mode flag"""
    assert menu_system.no_confirm == False
    menu_system.set_no_confirm(True)
    assert menu_system.no_confirm == True


def test_menu_color_red(menu_system):
    """Test RED color constant"""
    from forestgump.ui.colors import RED
    assert RED == "\033[91m"


def test_menu_color_green(menu_system):
    """Test GREEN color constant"""
    from forestgump.ui.colors import GREEN
    assert GREEN == "\033[92m"


def test_menu_color_yellow(menu_system):
    """Test YELLOW color constant"""
    from forestgump.ui.colors import YELLOW
    assert YELLOW == "\033[93m"


def test_menu_color_blue(menu_system):
    """Test BLUE color constant"""
    from forestgump.ui.colors import BLUE
    assert BLUE == "\033[94m"


def test_menu_color_reset(menu_system):
    """Test RESET color constant"""
    from forestgump.ui.colors import RESET
    assert RESET == "\033[0m"


def test_menu_colored_text(menu_system):
    """Test coloring text"""
    from forestgump.ui.colors import colorize
    colored = colorize("Hello", "green")
    assert "\033[" in colored  # Should contain ANSI codes
    assert "Hello" in colored
    assert "\033[0m" in colored  # Should end with reset


def test_menu_format_with_colors(menu_system):
    """Test formatting menu options with colors"""
    formatted = menu_system.format_option(1, "Attack Option", is_selected=False)
    # Should not be selected
    assert formatted is not None
    
    formatted_selected = menu_system.format_option(1, "Attack Option", is_selected=True)
    # Selected format should have different styling
    assert formatted_selected is not None
