"""
Anthropic provider implementation.
Direct integration with Anthropic API using official SDK.
"""

import os
from typing import List, Dict, Optional
from providers.base import Provider


class AnthropicProvider(Provider):
    """Anthropic API provider using official SDK."""
    
    def __init__(self):
        """Initialize Anthropic provider with API key discovery."""
        super().__init__("anthropic")
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = "claude-3-5-sonnet-20241022"  # Latest Sonnet model (May 2026)
        self.client = None
        self.timeout = 30  # seconds
        
        if self.api_key:
            self._initialize_client()
        else:
            self._available = False
    
    def _initialize_client(self):
        """Initialize Anthropic client."""
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=self.api_key)
            self._available = True
        except ImportError:
            raise RuntimeError(
                "Anthropic SDK not installed. Install with: pip install anthropic"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Anthropic provider: {e}")
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Send chat request to Anthropic API.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt to set context
            
        Returns:
            Plain text response
            
        Raises:
            RuntimeError: If not available or API call fails
        """
        if not self.is_available:
            raise RuntimeError(
                "Anthropic provider not available (missing ANTHROPIC_API_KEY)"
            )
        
        if not self.client:
            raise RuntimeError("Anthropic client not initialized")
        
        self._validate_messages(messages)
        
        # Filter out system messages from messages list (Anthropic handles separately)
        user_messages = [
            msg for msg in messages if msg.get("role") != "system"
        ]
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=user_messages,
                timeout=self.timeout,
            )
            
            if response.content and len(response.content) > 0:
                # Extract text from first content block
                content_block = response.content[0]
                if hasattr(content_block, "text"):
                    return content_block.text.strip()
                return str(content_block).strip()
            
            raise RuntimeError("Anthropic API returned empty response")
        
        except Exception as e:
            raise RuntimeError(f"Anthropic API call failed: {e}")
