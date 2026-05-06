"""
Multi-channel gateway module for ForestGump.
Provides integration with Telegram, Discord, Slack, and other messaging platforms.
"""

from .base import BaseGateway
from .telegram import TelegramGateway
from .discord import DiscordGateway
from .slack import SlackGateway

__all__ = [
    'BaseGateway',
    'TelegramGateway',
    'DiscordGateway',
    'SlackGateway',
]

# Gateway registry
GATEWAYS = {
    'telegram': TelegramGateway,
    'discord': DiscordGateway,
    'slack': SlackGateway,
}


def get_gateway(name: str) -> type:
    """Get a gateway class by name."""
    return GATEWAYS.get(name)


def list_gateways():
    """List available gateways."""
    return list(GATEWAYS.keys())
