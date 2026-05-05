"""
Tests for provider initialization and basic functionality.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from providers.base import Provider
from providers.groq import GroqProvider
from providers.claude import ClaudeCliProvider
from providers.anthropic import AnthropicProvider
from providers.copilot import CopilotProvider


class TestProviderBase:
    """Test abstract Provider base class."""
    
    def test_provider_cannot_instantiate(self):
        """Provider is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            Provider("test")
    
    def test_provider_validate_messages(self):
        """Test message validation."""
        # Can't instantiate directly, so we'll test through a concrete provider
        # when we test the others
        pass


class TestGroqProvider:
    """Test Groq provider."""
    
    def test_groq_init_no_api_key(self):
        """Groq provider should be unavailable without API key."""
        with patch.dict(os.environ, {}, clear=False):
            if "GROQ_API_KEY" in os.environ:
                del os.environ["GROQ_API_KEY"]
            provider = GroqProvider()
            assert provider.name == "groq"
            assert not provider.is_available
    
    def test_groq_provider_structure(self):
        """Groq provider has correct attributes."""
        provider = GroqProvider()
        assert hasattr(provider, "api_key")
        assert hasattr(provider, "available_models")
        assert hasattr(provider, "model")
        assert hasattr(provider, "timeout")
        assert provider.timeout == 30
    
    def test_groq_model_preferences(self):
        """Test Groq model preference order."""
        preferences = GroqProvider.MODEL_PREFERENCES
        assert preferences[0] == "llama-3.3-70b-versatile"
        assert "llama-3.1-8b-instant" in preferences
        assert len(preferences) >= 3


class TestClaudeCliProvider:
    """Test Claude CLI provider."""
    
    @patch("subprocess.run")
    def test_claude_init_not_available(self, mock_run):
        """Claude CLI should be unavailable if CLI not installed."""
        mock_run.side_effect = FileNotFoundError()
        provider = ClaudeCliProvider()
        assert provider.name == "claude"
        assert not provider.is_available
    
    @patch("subprocess.run")
    def test_claude_init_available(self, mock_run):
        """Claude CLI should be available if CLI is installed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        provider = ClaudeCliProvider()
        assert provider.name == "claude"
        assert provider.is_available


class TestAnthropicProvider:
    """Test Anthropic provider."""
    
    def test_anthropic_init_no_api_key(self):
        """Anthropic provider should be unavailable without API key."""
        with patch.dict(os.environ, {}, clear=False):
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]
            provider = AnthropicProvider()
            assert provider.name == "anthropic"
            assert not provider.is_available
    
    def test_anthropic_provider_structure(self):
        """Anthropic provider has correct attributes."""
        provider = AnthropicProvider()
        assert hasattr(provider, "api_key")
        assert hasattr(provider, "model")
        assert hasattr(provider, "client")
        assert hasattr(provider, "timeout")
        assert provider.timeout == 30


class TestCopilotProvider:
    """Test GitHub Copilot provider."""
    
    @patch("subprocess.run")
    def test_copilot_init_not_available(self, mock_run):
        """Copilot should be unavailable if gh CLI not installed."""
        mock_run.side_effect = FileNotFoundError()
        provider = CopilotProvider()
        assert provider.name == "copilot"
        assert not provider.is_available
    
    @patch("subprocess.run")
    def test_copilot_init_available(self, mock_run):
        """Copilot should be available if gh CLI is installed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        provider = CopilotProvider()
        assert provider.name == "copilot"
        assert provider.is_available


class TestProviderImports:
    """Test that all providers can be imported."""
    
    def test_import_base(self):
        """Can import base Provider."""
        from providers.base import Provider
        assert Provider is not None
    
    def test_import_groq(self):
        """Can import GroqProvider."""
        from providers.groq import GroqProvider
        assert GroqProvider is not None
    
    def test_import_claude(self):
        """Can import ClaudeCliProvider."""
        from providers.claude import ClaudeCliProvider
        assert ClaudeCliProvider is not None
    
    def test_import_anthropic(self):
        """Can import AnthropicProvider."""
        from providers.anthropic import AnthropicProvider
        assert AnthropicProvider is not None
    
    def test_import_copilot(self):
        """Can import CopilotProvider."""
        from providers.copilot import CopilotProvider
        assert CopilotProvider is not None
    
    def test_import_from_package(self):
        """Can import from providers package."""
        from providers import (
            Provider,
            GroqProvider,
            ClaudeCliProvider,
            AnthropicProvider,
            CopilotProvider,
        )
        assert all([
            Provider,
            GroqProvider,
            ClaudeCliProvider,
            AnthropicProvider,
            CopilotProvider,
        ])
