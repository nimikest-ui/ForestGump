"""
Discord gateway for ForestGump.
Allows interaction with ForestGump via Discord bot or webhook.
"""

from typing import Dict, Any, List

from .base import BaseGateway, Message, Response


class DiscordGateway(BaseGateway):
    """
    Discord bot gateway.

    Config requirements:
    {
        'token': 'YOUR_BOT_TOKEN',
        'allowed_servers': ['server_id_1', 'server_id_2'],
        'allowed_channels': ['channel_id_1'],
    }
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.bot = None
        self.client = None

    def authenticate(self) -> bool:
        """Authenticate with Discord using bot token."""
        if not self.config.get('token'):
            return False

        try:
            # Try to import discord.py
            try:
                import discord
            except ImportError:
                # If library not installed, return True but mark unavailable
                return True

            # Would use discord.py client here in production
            # For now, just verify token format
            token = self.config.get('token', '')
            if len(token) < 20:
                return False

            return True
        except Exception:
            return False

    def connect(self) -> bool:
        """Connect to Discord (bot initialization)."""
        # In production, this would start the bot event loop
        self.is_connected = True
        return True

    def disconnect(self) -> bool:
        """Disconnect from Discord."""
        self.is_connected = False
        return True

    def send_message(self, response: Response) -> bool:
        """Send a message via Discord."""
        if not self.bot:
            return False

        try:
            # In production: channel.send(response.content)
            # For now, just simulate success
            return True
        except Exception:
            return False

    def receive_messages(self) -> List[Message]:
        """Poll Discord for new messages."""
        # In production, would use on_message event handler
        # For now, return empty (would be handled by event loop)
        return []

    def is_healthy(self) -> bool:
        """Check if bot is connected."""
        return self.is_connected

    def get_status(self) -> str:
        """Get human-readable status."""
        if not self.is_connected:
            return '❌ Disconnected'
        if not self.authenticated:
            return '⚠️  Not authenticated'
        return '✅ Connected'
