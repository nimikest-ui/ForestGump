"""
Abstract base provider class for all LLM integrations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import json


class Provider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, name: str):
        """Initialize provider with name."""
        self.name = name
        self.model = None
        self._available = False
    
    @property
    def is_available(self) -> bool:
        """Check if provider is properly configured and available."""
        return self._available
    
    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Send messages to the provider and get a response.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system_prompt: Optional system prompt to set context
            
        Returns:
            Plain text response string
            
        Raises:
            RuntimeError: If provider is not available or call fails
        """
        pass
    
    def _validate_messages(self, messages: List[Dict[str, str]]) -> bool:
        """Validate message format."""
        if not isinstance(messages, list):
            raise ValueError("Messages must be a list")
        
        for msg in messages:
            if not isinstance(msg, dict):
                raise ValueError("Each message must be a dict")
            if "role" not in msg or "content" not in msg:
                raise ValueError("Each message must have 'role' and 'content'")
        
        return True
    
    def format_messages_for_api(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Format messages for API consumption.
        Override in subclasses if needed.
        """
        if system_prompt:
            formatted = [{"role": "system", "content": system_prompt}]
            formatted.extend(messages)
            return formatted
        return messages
