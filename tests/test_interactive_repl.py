"""Tests for InteractiveREPL functionality."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from forestgump_cli import InteractiveREPL, Colors


@pytest.fixture
def temp_session_dir():
    """Create a temporary directory for sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_provider():
    """Create a mock provider."""
    provider = Mock()
    provider.chat = Mock(return_value="This is a test response.")
    return provider


@pytest.fixture
def interactive_repl(temp_session_dir, mock_provider):
    """Create an InteractiveREPL instance with mocked components."""
    repl = InteractiveREPL(
        provider=mock_provider,
        model="test-model",
        provider_name="groq",
        session_dir=temp_session_dir
    )
    return repl


class TestInteractiveREPLInit:
    """Test InteractiveREPL initialization."""
    
    def test_init_creates_instance(self, interactive_repl):
        """Test that REPL initializes correctly."""
        assert interactive_repl.provider is not None
        assert interactive_repl.model == "test-model"
        assert interactive_repl.provider_name == "groq"
        assert interactive_repl.conversation_history == []
    
    def test_init_with_existing_session(self, temp_session_dir, mock_provider):
        """Test initializing REPL with existing session."""
        session_id = "20260505T210000"
        session_file = temp_session_dir / f"{session_id}.json"
        
        # Create a mock session file
        session_data = {
            "session_id": session_id,
            "task": "Test conversation",
            "provider": "groq",
            "model": "test-model",
            "timestamp": "2026-05-05T21:00:00",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
        }
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f)
        
        repl = InteractiveREPL(
            provider=mock_provider,
            model="test-model",
            provider_name="groq",
            session_dir=temp_session_dir,
            session_id=session_id
        )
        
        assert repl.session_id == session_id
        assert len(repl.conversation_history) == 2


class TestInteractiveREPLCommands:
    """Test REPL command parsing and execution."""
    
    def test_parse_command_help(self, interactive_repl):
        """Test parsing /help command."""
        cmd, args = interactive_repl.parse_command("/help")
        assert cmd == "help"
        assert args == []
    
    def test_parse_command_with_args(self, interactive_repl):
        """Test parsing command with arguments."""
        cmd, args = interactive_repl.parse_command("/load session123")
        assert cmd == "load"
        assert args == ["session123"]
    
    def test_parse_command_with_multiple_args(self, interactive_repl):
        """Test parsing command with multiple arguments."""
        cmd, args = interactive_repl.parse_command("/model some model name")
        assert cmd == "model"
        assert args == ["some", "model", "name"]
    
    def test_parse_regular_message(self, interactive_repl):
        """Test that regular messages are identified."""
        cmd, args = interactive_repl.parse_command("Hello, how are you?")
        assert cmd is None
        assert args is None
    
    def test_handle_help_command(self, interactive_repl, capsys):
        """Test /help command output."""
        interactive_repl.handle_help([])
        captured = capsys.readouterr()
        assert "Available commands:" in captured.out or "/help" in captured.out
    
    def test_handle_status_command(self, interactive_repl, capsys):
        """Test /status command output."""
        interactive_repl.handle_status([])
        captured = capsys.readouterr()
        assert "groq" in captured.out.lower() or "test-model" in captured.out
    
    def test_handle_clear_command(self, interactive_repl):
        """Test /clear command."""
        interactive_repl.conversation_history = [
            {"role": "user", "content": "Test"}
        ]
        interactive_repl.handle_clear([])
        assert interactive_repl.conversation_history == []
    
    def test_handle_exit_command(self, interactive_repl):
        """Test /exit command returns True."""
        result = interactive_repl.handle_exit([])
        assert result is True


class TestSessionPersistence:
    """Test session save/load functionality."""
    
    def test_save_session(self, interactive_repl, temp_session_dir):
        """Test saving a session."""
        interactive_repl.conversation_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"}
        ]
        interactive_repl.session_id = "test_session_123"
        
        session_id = interactive_repl.save_session()
        assert session_id == "test_session_123"
        
        session_file = temp_session_dir / f"{session_id}.json"
        assert session_file.exists()
        
        with open(session_file) as f:
            data = json.load(f)
            assert len(data["messages"]) == 2
            assert data["model"] == "test-model"
    
    def test_load_session(self, temp_session_dir, mock_provider):
        """Test loading an existing session."""
        session_id = "load_test_123"
        session_file = temp_session_dir / f"{session_id}.json"
        
        session_data = {
            "session_id": session_id,
            "task": "Previous conversation",
            "provider": "groq",
            "model": "test-model",
            "timestamp": "2026-05-05T20:00:00",
            "messages": [
                {"role": "user", "content": "Previous query"},
                {"role": "assistant", "content": "Previous response"}
            ]
        }
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f)
        
        repl = InteractiveREPL(
            provider=mock_provider,
            model="test-model",
            provider_name="groq",
            session_dir=temp_session_dir,
            session_id=session_id
        )
        
        assert repl.conversation_history == session_data["messages"]


class TestConversationFlow:
    """Test conversation handling."""
    
    def test_append_to_history(self, interactive_repl):
        """Test appending messages to conversation history."""
        interactive_repl.append_message("user", "Test message")
        assert len(interactive_repl.conversation_history) == 1
        assert interactive_repl.conversation_history[0]["role"] == "user"
        assert interactive_repl.conversation_history[0]["content"] == "Test message"
    
    def test_multiple_messages_in_history(self, interactive_repl):
        """Test multiple messages in history."""
        interactive_repl.append_message("user", "First question")
        interactive_repl.append_message("assistant", "First answer")
        interactive_repl.append_message("user", "Second question")
        
        assert len(interactive_repl.conversation_history) == 3
        assert interactive_repl.conversation_history[0]["role"] == "user"
        assert interactive_repl.conversation_history[1]["role"] == "assistant"
        assert interactive_repl.conversation_history[2]["role"] == "user"
    
    def test_get_turn_count(self, interactive_repl):
        """Test getting turn count."""
        interactive_repl.append_message("user", "Q1")
        interactive_repl.append_message("assistant", "A1")
        interactive_repl.append_message("user", "Q2")
        interactive_repl.append_message("assistant", "A2")
        
        turn_count = interactive_repl.get_turn_count()
        assert turn_count == 2  # 2 user-assistant pairs


class TestColorOutput:
    """Test color-coded output."""
    
    def test_format_user_message(self, interactive_repl):
        """Test formatting user message with color."""
        formatted = interactive_repl.format_user_message("Hello")
        assert "Hello" in formatted
    
    def test_format_assistant_message(self, interactive_repl):
        """Test formatting assistant message with color."""
        formatted = interactive_repl.format_assistant_message("Hi there!")
        assert "Hi there!" in formatted
    
    def test_format_error_message(self, interactive_repl):
        """Test formatting error message with color."""
        formatted = interactive_repl.format_error_message("Something went wrong")
        assert "Something went wrong" in formatted


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_input(self, interactive_repl):
        """Test handling empty input."""
        cmd, args = interactive_repl.parse_command("")
        assert cmd is None
    
    def test_whitespace_only_input(self, interactive_repl):
        """Test handling whitespace-only input."""
        cmd, args = interactive_repl.parse_command("   ")
        assert cmd is None
    
    def test_command_case_insensitivity(self, interactive_repl):
        """Test that commands are case-insensitive."""
        cmd, _ = interactive_repl.parse_command("/HELP")
        assert cmd == "help"
    
    def test_get_turn_count_empty_history(self, interactive_repl):
        """Test turn count with empty history."""
        assert interactive_repl.get_turn_count() == 0
    
    def test_get_turn_count_odd_messages(self, interactive_repl):
        """Test turn count with odd number of messages."""
        interactive_repl.append_message("user", "Q1")
        interactive_repl.append_message("assistant", "A1")
        interactive_repl.append_message("user", "Q2")
        # Only 1 complete turn (Q2 without response yet)
        assert interactive_repl.get_turn_count() == 1


class TestProviderInteraction:
    """Test interactions with the provider."""
    
    def test_chat_with_provider(self, interactive_repl):
        """Test sending a message to the provider."""
        interactive_repl.provider.chat = Mock(return_value="Response from provider")
        
        response = interactive_repl.provider.chat("Hello", interactive_repl.conversation_history)
        
        assert response == "Response from provider"
        interactive_repl.provider.chat.assert_called_once()


class TestSessionListing:
    """Test session listing functionality."""
    
    def test_list_sessions_empty(self, interactive_repl):
        """Test listing sessions when none exist."""
        sessions = interactive_repl.list_sessions()
        assert sessions == []
    
    def test_list_sessions_with_data(self, temp_session_dir, interactive_repl):
        """Test listing sessions with existing data."""
        # Create test sessions
        for i in range(3):
            session_file = temp_session_dir / f"session_{i}.json"
            session_data = {
                "session_id": f"session_{i}",
                "task": f"Task {i}",
                "provider": "groq",
                "model": "test-model",
                "timestamp": "2026-05-05T20:00:00",
                "messages": []
            }
            with open(session_file, 'w') as f:
                json.dump(session_data, f)
        
        sessions = interactive_repl.list_sessions(limit=10)
        assert len(sessions) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
