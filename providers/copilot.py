"""
GitHub Copilot provider implementation.
Uses Copilot API with Claude Haiku 4.5 (matching Hermes default).
"""

import os
import subprocess
from typing import List, Dict, Optional
from providers.base import Provider


class CopilotProvider(Provider):
    """GitHub Copilot API provider with Claude Haiku 4.5."""
    
    def __init__(self, model: str = "claude-haiku-4-5"):
        """Initialize GitHub Copilot provider."""
        super().__init__("copilot")
        self.model = model  # Default: claude-haiku-4-5 (Hermes default)
        self._api_key = os.environ.get("GITHUB_COPILOT_TOKEN")
        self._available = self._check_availability()
    
    def _check_availability(self) -> bool:
        """Check if Copilot API is available (has token or gh auth)."""
        # Try API key first
        if self._api_key:
            return True
        
        # Fallback: check gh CLI auth
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                timeout=5,
                text=True,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Send chat request via GitHub Copilot API with Claude Haiku.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: System prompt to include
            
        Returns:
            Plain text response
            
        Raises:
            RuntimeError: If not available or API call fails
        """
        if not self.is_available:
            raise RuntimeError(
                "GitHub Copilot not available. "
                "Set GITHUB_COPILOT_TOKEN or run: gh auth login"
            )
        
        self._validate_messages(messages)
        
        try:
            import requests
        except ImportError:
            raise RuntimeError("requests library required: pip install requests")
        
        # Build request payload (OpenAI-compatible API)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2048,
        }
        
        if system_prompt:
            payload["messages"] = [
                {"role": "system", "content": system_prompt}
            ] + messages
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(
                "https://api.githubcopilot.com/chat/completions",
                json=payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Copilot API error: {e}")
