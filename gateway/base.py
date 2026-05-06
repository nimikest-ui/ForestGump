"""
Base gateway class for multi-channel integration.
Each gateway implementation handles one messaging platform.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class Message:
    """Represents a message from a user via a gateway."""

    sender_id: str
    sender_name: str
    content: str
    timestamp: float
    channel_id: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class Response:
    """Represents a response to send back via a gateway."""

    recipient_id: str
    content: str
    thread_id: Optional[str] = None
    metadata: Dict[str, Any] = None


class BaseGateway(ABC):
    """
    Abstract base class for messaging gateways.

    Each gateway implementation must provide:
    - Authentication/connection management
    - Message reception
    - Message sending
    - Status reporting
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize gateway with config.

        Args:
            config: Gateway-specific configuration dict
        """
        self.config = config or {}
        self.is_connected = False
        self.authenticated = False

    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to the messaging service.

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from the messaging service.

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with credentials from config.

        Returns:
            True if authenticated, False otherwise
        """
        pass

    @abstractmethod
    def send_message(self, response: Response) -> bool:
        """
        Send a message to a recipient.

        Args:
            response: Response object with recipient and content

        Returns:
            True if sent, False otherwise
        """
        pass

    @abstractmethod
    def receive_messages(self) -> List[Message]:
        """
        Check for and retrieve incoming messages.

        Returns:
            List of Message objects
        """
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        Check if gateway connection is healthy.

        Returns:
            True if operational, False otherwise
        """
        pass

    def setup(self) -> bool:
        """
        Complete setup: authenticate and connect.

        Returns:
            True if ready to use
        """
        if not self.authenticate():
            return False
        if not self.connect():
            return False
        self.authenticated = True
        self.is_connected = True
        return True

    def teardown(self) -> bool:
        """Clean shutdown."""
        return self.disconnect()
