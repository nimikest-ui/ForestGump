"""Terminal UI menu system with arrow key navigation and command history."""

from typing import List
from src.forestgump.ui.colors import GREEN, RESET, BOLD, colorize


class MenuSystem:
    """Terminal menu system with color support and command history."""

    def __init__(self):
        """Initialize MenuSystem with default provider and models."""
        self._provider = "ollama"
        self._model = "llama3.2:latest"
        self._history: List[str] = []
        self.no_confirm = False

        # Menu options
        self._menu_options = [
            "Change Model",
            "Plan Attack",
            "Ask Question",
            "Continue",
            "Clear Memory",
            "Show Current Model",
            "Exit",
        ]

        # Provider list
        self._providers = ["ollama", "claude", "anthropic", "copilot"]

        # Local models (15+)
        self._local_models = [
            "llama3.2:latest",
            "llama3.2:8b",
            "llama3.2:11b",
            "llama3.1:latest",
            "llama3.1:8b",
            "llama3.1:70b",
            "mistral:latest",
            "mistral:7b",
            "gemma:2b",
            "gemma:7b",
            "qwen:7b",
            "qwen:14b",
            "qwen2.5:7b",
            "tinyllama:latest",
            "deepseek-r1:1.5b",
        ]

        # Cloud models (25+) via ollama.com
        self._cloud_models = [
            # GLM
            "glm-5-latest",
            "glm-5.1",
            "glm-5",
            "glm-4-flash",
            # Kimi
            "kimi-k2.6",
            "kimi-k2.5",
            # MiniMax
            "minimax-m2.7",
            "minimax-m2.5",
            # DeepSeek
            "deepseek-v3",
            "deepseek-v2.5",
            "deepseek-r1",
            "deepseek-chat",
            # Mistral
            "mistral-small",
            "mistral-medium",
            "mistral-large",
            # Gemma
            "gemma-2b-cloud",
            "gemma-7b-cloud",
            # Nemotron
            "nemotron-4-340b-instruct",
            # Others
            "qwen-32b",
            "code-llama",
            "llava:13b",
            "neural-chat:7b",
            "orca-mini:7b",
            "starling-lm:7b",
            "openchat:7b",
        ]

    def get_menu_options(self) -> List[str]:
        """Get list of menu options.
        
        Returns:
            List of 7 menu option strings
        """
        return self._menu_options.copy()

    def get_providers(self) -> List[str]:
        """Get list of available providers.
        
        Returns:
            List of provider names
        """
        return self._providers.copy()

    def get_ollama_models(self) -> List[str]:
        """Get list of available Ollama models (local + cloud).
        
        Returns:
            Combined list of local and cloud models
        """
        return self._local_models + self._cloud_models

    def set_provider(self, provider: str) -> None:
        """Set current provider.
        
        Args:
            provider: Provider name
        """
        if provider in self._providers:
            self._provider = provider

    def get_provider(self) -> str:
        """Get current provider.
        
        Returns:
            Current provider name
        """
        return self._provider

    def set_model(self, model: str) -> None:
        """Set current model.
        
        Args:
            model: Model name
        """
        self._model = model

    def get_model(self) -> str:
        """Get current model.
        
        Returns:
            Current model name
        """
        return self._model

    def set_no_confirm(self, value: bool) -> None:
        """Set no-confirmation mode.
        
        Args:
            value: True to enable no-confirm mode, False to disable
        """
        self.no_confirm = value

    def add_to_history(self, task: str) -> None:
        """Add task to command history (max 20 entries).
        
        Args:
            task: Task description to add to history
        """
        self._history.append(task)
        # Keep only last 20 entries
        if len(self._history) > 20:
            self._history = self._history[-20:]

    def get_history(self) -> List[str]:
        """Get command history.
        
        Returns:
            List of tasks in history
        """
        return self._history.copy()

    def format_option(self, index: int, text: str, is_selected: bool) -> str:
        """Format menu option with color and selection indicator.
        
        Args:
            index: Option index
            text: Option text
            is_selected: Whether this option is selected
        
        Returns:
            Formatted option string
        """
        if is_selected:
            # Selected: show with green color and indicator
            indicator = "> "
            return f"{GREEN}{BOLD}{indicator}{text}{RESET}"
        else:
            # Not selected: normal formatting
            return f"  {text}"

    def display_menu(self) -> str:
        """Display formatted menu.
        
        Returns:
            Formatted menu as string
        """
        lines = []
        for i, option in enumerate(self._menu_options, 1):
            lines.append(f"{i}. {option}")
        return "\n".join(lines)
