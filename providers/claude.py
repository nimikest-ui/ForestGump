"""
Claude CLI provider implementation.
Uses subprocess to call `claude` command for chat interactions.
"""

import subprocess
import json
from typing import List, Dict, Optional
from providers.base import Provider


class ClaudeCliProvider(Provider):
    """Claude CLI provider using subprocess integration."""
    
    def __init__(self):
        """Initialize Claude CLI provider."""
        super().__init__("claude")
        self.model = "claude-3.5-sonnet"  # Latest Claude model
        self._available = self._check_claude_cli()
    
    def _check_claude_cli(self) -> bool:
        """Check if Claude CLI is installed and authenticated."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
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
        Send chat request via Claude CLI.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            
        Returns:
            Plain text response
            
        Raises:
            RuntimeError: If not available or CLI call fails
        """
        if not self.is_available:
            raise RuntimeError(
                "Claude CLI not available. Install with: npm install -g claude"
            )
        
        self._validate_messages(messages)
        
        # Build the prompt from messages
        prompt = self._build_prompt(messages, system_prompt)
        
        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--json"],
                capture_output=True,
                timeout=30,
                text=True,
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI error: {result.stderr}")
            
            # Parse JSON response
            try:
                response_data = json.loads(result.stdout)
                if isinstance(response_data, dict) and "content" in response_data:
                    return response_data["content"].strip()
                elif isinstance(response_data, dict) and "response" in response_data:
                    return response_data["response"].strip()
                else:
                    return result.stdout.strip()
            except json.JSONDecodeError:
                # Fall back to raw output if not JSON
                return result.stdout.strip()
        
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI request timed out")
        except Exception as e:
            raise RuntimeError(f"Claude CLI call failed: {e}")
    
    def _build_prompt(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Build a single prompt string from messages."""
        parts = []
        
        if system_prompt:
            parts.append(f"System: {system_prompt}\n")
        
        for msg in messages:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")
        
        return "\n".join(parts)
