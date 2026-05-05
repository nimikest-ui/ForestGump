"""ForestGump — Hermes-inspired modular AI agent framework."""

__version__ = "0.1.0"

# Core imports
try:
    from forestgump.core.agent import Agent
    from forestgump.core.session import Session
except ImportError:
    Agent = None
    Session = None

# Tool imports
try:
    from forestgump.tools.shell import ShellTool
    from forestgump.tools.safety import SafetyChecker
except ImportError:
    ShellTool = None
    SafetyChecker = None

# Memory imports
from forestgump.memory.types import MemoryEntry
from forestgump.memory.system import MemorySystem
from forestgump.memory.manager import MemoryManager

# Skills imports
try:
    from forestgump.skills.database import SkillsDatabase
    from forestgump.skills.extractor import SkillExtractor
except ImportError:
    SkillsDatabase = None
    SkillExtractor = None

# UI imports
try:
    from forestgump.ui.menu import MenuSystem
    from forestgump.ui import colors
except ImportError:
    MenuSystem = None
    colors = None

# Provider imports
try:
    from forestgump.providers.base import BaseProvider
    from forestgump.providers.claude import ClaudeProvider
    from forestgump.providers.ollama import OllamaProvider
    from forestgump.providers.anthropic import AnthropicProvider
    from forestgump.providers.copilot import CopilotProvider
except ImportError:
    BaseProvider = None
    ClaudeProvider = None
    OllamaProvider = None
    AnthropicProvider = None
    CopilotProvider = None

__all__ = [
    "Agent",
    "Session",
    "ShellTool",
    "SafetyChecker",
    "MemoryEntry",
    "MemorySystem",
    "MemoryManager",
    "SkillsDatabase",
    "SkillExtractor",
    "MenuSystem",
    "colors",
    "BaseProvider",
    "ClaudeProvider",
    "OllamaProvider",
    "AnthropicProvider",
    "CopilotProvider",
]

