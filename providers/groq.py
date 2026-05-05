"""
Groq provider implementation with dynamic model discovery.
"""

import os
from typing import List, Dict, Optional
from providers.base import Provider


class GroqProvider(Provider):
    """Groq API provider with automatic model discovery."""
    
    # Fallback chain for model selection
    MODEL_PREFERENCES = [
        "llama-3.3-70b-versatile",      # Primary (May 2026)
        "llama-3.1-8b-instant",          # Fast fallback
        "groq/compound-mini",            # Tools support
        "qwen/qwen3-32b",                # Alternative
        "openai/gpt-oss-120b",           # Alternative
    ]
    
    def __init__(self):
        """Initialize Groq provider with API key discovery."""
        super().__init__("groq")
        self.api_key = os.environ.get("GROQ_API_KEY")
        self.available_models = []
        self.model = None
        self.client = None
        self.timeout = 30  # seconds
        
        if self.api_key:
            self._initialize_client()
        else:
            self._available = False
    
    def _initialize_client(self):
        """Initialize Groq client and discover models."""
        try:
            from groq import Groq
            self.client = Groq(api_key=self.api_key)
            self._discover_models()
            self._select_best_model()
            self._available = True
        except ImportError:
            raise RuntimeError(
                "Groq SDK not installed. Install with: pip install groq"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Groq provider: {e}")
    
    def _discover_models(self):
        """Query Groq API for available models at runtime."""
        try:
            models = self.client.models.list()
            self.available_models = [m.id for m in models.data]
        except Exception as e:
            self.available_models = []
            raise RuntimeError(f"Failed to discover Groq models: {e}")
    
    def _select_best_model(self):
        """Select best available model using fallback chain."""
        # Try preferences in order
        for model in self.MODEL_PREFERENCES:
            if model in self.available_models:
                self.model = model
                return
        
        # Use first available
        if self.available_models:
            self.model = self.available_models[0]
            return
        
        # Last resort
        self.model = "llama-3.3-70b-versatile"
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Send chat request to Groq API.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt to set context
            
        Returns:
            Plain text response
            
        Raises:
            RuntimeError: If not available or API call fails
        """
        if not self.is_available:
            raise RuntimeError("Groq provider not available (missing GROQ_API_KEY)")
        
        if not self.client:
            raise RuntimeError("Groq client not initialized")
        
        self._validate_messages(messages)
        
        formatted_messages = self.format_messages_for_api(messages, system_prompt)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                temperature=0.7,
                max_tokens=2048,
                timeout=self.timeout,
            )
            
            if response.choices and response.choices[0].message:
                return response.choices[0].message.content.strip()
            
            raise RuntimeError("Groq API returned empty response")
        
        except Exception as e:
            raise RuntimeError(f"Groq API call failed: {e}")
    
    def set_model(self, model: str) -> bool:
        """Override model selection."""
        if model in self.available_models or model == self.MODEL_PREFERENCES[0]:
            self.model = model
            return True
        return False
