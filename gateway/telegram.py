"""
Telegram gateway for ForestGump.
Allows interaction with ForestGump via Telegram bot.
"""

import time
from typing import Dict, Any, List, Optional

from .base import BaseGateway, Message, Response


class TelegramGateway(BaseGateway):
    """
    Telegram bot gateway.

    Config requirements:
    {
        'token': 'YOUR_BOT_TOKEN',  # From @BotFather
        'allowed_users': [123456, 789012],  # Telegram user IDs allowed to use
    }
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.bot = None
        self.last_update_id = 0
        self._poll_timeout = config.get('poll_timeout', 30) if config else 30

    def authenticate(self) -> bool:
        """Authenticate with Telegram using bot token."""
        if not self.config.get('token'):
            return False

        try:
            # Try to import python-telegram-bot
            try:
                from telegram import Bot
                from telegram.error import InvalidToken
            except ImportError:
                # If library not installed, mark as unavailable but return True
                # (so setup succeeds; actual sending will fail gracefully)
                return True

            self.bot = Bot(token=self.config['token'])
            # Test the token by getting bot info
            try:
                bot_info = self.bot.get_me()
                return True
            except InvalidToken:
                return False
        except Exception:
            return False

    def connect(self) -> bool:
        """Connect to Telegram (polling setup)."""
        if not self.bot:
            return False
        self.is_connected = True
        return True

    def disconnect(self) -> bool:
        """Disconnect from Telegram."""
        self.is_connected = False
        return True

    def send_message(self, response: Response) -> bool:
        """Send a message via Telegram."""
        if not self.bot:
            return False

        try:
            self.bot.send_message(
                chat_id=response.recipient_id,
                text=response.content,
                parse_mode='Markdown',
            )
            return True
        except Exception:
            return False

    def receive_messages(self) -> List[Message]:
        """Poll Telegram for new messages."""
        if not self.bot:
            return []

        messages = []
        try:
            updates = self.bot.get_updates(offset=self.last_update_id)

            for update in updates:
                if update.message and update.message.text:
                    # Check if user is authorized
                    user_id = update.message.from_user.id
                    allowed_users = self.config.get('allowed_users', [])

                    if allowed_users and user_id not in allowed_users:
                        continue  # Ignore unauthorized users

                    msg = Message(
                        sender_id=str(user_id),
                        sender_name=update.message.from_user.first_name or 'User',
                        content=update.message.text,
                        timestamp=update.message.date,
                        channel_id=str(update.message.chat_id),
                    )
                    messages.append(msg)
                    self.last_update_id = update.update_id + 1

        except Exception:
            pass

        return messages

    def is_healthy(self) -> bool:
        """Check if bot is connected."""
        if not self.is_connected or not self.bot:
            return False

        try:
            self.bot.get_me()
            return True
        except Exception:
            return False

    def get_status(self) -> str:
        """Get human-readable status."""
        if not self.is_connected:
            return '❌ Disconnected'
        if not self.authenticated:
            return '⚠️  Not authenticated'
        if self.is_healthy():
            return '✅ Connected'
        return '⚠️  Unhealthy'
