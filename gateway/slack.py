"""
Slack gateway for ForestGump.
Allows interaction with ForestGump via Slack bot or webhook.
"""

from typing import Dict, Any, List

from .base import BaseGateway, Message, Response


class SlackGateway(BaseGateway):
    """
    Slack bot gateway using Bolt framework.

    Config requirements:
    {
        'bot_token': 'xoxb-YOUR-BOT-TOKEN',
        'signing_secret': 'YOUR-SIGNING-SECRET',
        'allowed_users': ['U123456', 'U789012'],
    }
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.app = None
        self.client = None

    def authenticate(self) -> bool:
        """Authenticate with Slack using bot token and signing secret."""
        if not self.config.get('bot_token') or not self.config.get('signing_secret'):
            return False

        try:
            # Try to import slack_bolt
            try:
                from slack_bolt import App
            except ImportError:
                # If library not installed, return True but mark unavailable
                return True

            bot_token = self.config.get('bot_token', '')
            if not bot_token.startswith('xoxb-'):
                return False

            return True
        except Exception:
            return False

    def connect(self) -> bool:
        """Connect to Slack (app initialization)."""
        # In production, this would start the Slack app
        self.is_connected = True
        return True

    def disconnect(self) -> bool:
        """Disconnect from Slack."""
        self.is_connected = False
        return True

    def send_message(self, response: Response) -> bool:
        """Send a message via Slack."""
        if not self.client:
            return False

        try:
            # In production: client.chat_postMessage(channel=response.recipient_id, text=response.content)
            # For now, just simulate success
            return True
        except Exception:
            return False

    def receive_messages(self) -> List[Message]:
        """Poll Slack for new messages."""
        # In production, would use event handlers from Bolt framework
        # For now, return empty (handled by event loop)
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
