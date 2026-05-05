"""ForestGump — Hermes-inspired modular AI agent framework."""

__version__ = "0.1.0"

# Core imports
from src.forestgump.core.agent import Agent
from src.forestgump.core.session import Session

# Tool imports
from src.forestgump.tools.shell import ShellTool
from src.forestgump.tools.safety import SafetyChecker

# Memory imports
from src.forestgump.memory.types import MemoryEntry
from src.forestgump.memory.system import MemorySystem

# Skills imports
from src.forestgump.skills.database import SkillsDatabase
from src.forestgump.skills.extractor import SkillExtractor

# UI imports
from src.forestgump.ui.menu import MenuSystem
from src.forestgump.ui import colors

# Provider imports
from src.forestgump.providers.base import BaseProvider
from src.forestgump.providers.claude import ClaudeProvider
from src.forestgump.providers.ollama import OllamaProvider
from src.forestgump.providers.anthropic import AnthropicProvider
from src.forestgump.providers.copilot import CopilotProvider

__all__ = [
    "Agent",
    "Session",
    "ShellTool",
    "SafetyChecker",
    "MemoryEntry",
    "MemorySystem",
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
