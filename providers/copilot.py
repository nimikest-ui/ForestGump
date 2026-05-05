"""
GitHub Copilot provider implementation.
Uses subprocess to call `gh copilot suggest` command.
"""

import subprocess
from typing import List, Dict, Optional
from providers.base import Provider


class CopilotProvider(Provider):
    """GitHub Copilot CLI provider using subprocess integration."""
    
    def __init__(self):
        """Initialize GitHub Copilot provider."""
        super().__init__("copilot")
        self.model = "github-copilot"  # Abstracted model name
        self._available = self._check_gh_cli()
    
    def _check_gh_cli(self) -> bool:
        """Check if GitHub CLI is installed and authenticated."""
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
        Send chat request via GitHub Copilot CLI.
        Note: Copilot is limited in capabilities - no system prompts or multi-turn.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Ignored (Copilot doesn't support system prompts)
            
        Returns:
            Plain text response
            
        Raises:
            RuntimeError: If not available or CLI call fails
        """
        if not self.is_available:
            raise RuntimeError(
                "GitHub Copilot CLI not available. "
                "Install gh CLI and run: gh extension install github/gh-copilot"
            )
        
        self._validate_messages(messages)
        
        # Extract the last user message (Copilot doesn't support multi-turn context)
        prompt = self._extract_last_user_message(messages)
        
        if not prompt:
            raise RuntimeError("No user message found in messages")
        
        try:
            result = subprocess.run(
                ["gh", "copilot", "suggest", "--shell", prompt],
                capture_output=True,
                timeout=30,
                text=True,
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Copilot CLI error: {result.stderr}")
            
            return result.stdout.strip()
        
        except subprocess.TimeoutExpired:
            raise RuntimeError("Copilot CLI request timed out")
        except Exception as e:
            raise RuntimeError(f"Copilot CLI call failed: {e}")
    
    def _extract_last_user_message(self, messages: List[Dict[str, str]]) -> str:
        """Extract the last user message from the conversation."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""
