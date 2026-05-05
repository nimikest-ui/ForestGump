#!/usr/bin/env python3
"""
ForestGump CLI — Hermes-compatible command-line interface for pentesting agents.
Matches Hermes' command structure and behavior with Kali Linux integration.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import subprocess

# Import providers
from providers import (
    GroqProvider,
    ClaudeCliProvider,
    AnthropicProvider,
    CopilotProvider,
)

# Import tool sandbox
from toolsandbox import Sandbox, CommandParser, CommandFilter

# ANSI colors
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

VERSION = "2.0.0-hermes-compatible"


class Colors:
    """ANSI color utilities."""
    
    @staticmethod
    def info(text: str) -> str:
        return f"{CYAN}{text}{RESET}"
    
    @staticmethod
    def success(text: str) -> str:
        return f"{GREEN}{text}{RESET}"
    
    @staticmethod
    def error(text: str) -> str:
        return f"{RED}{text}{RESET}"
    
    @staticmethod
    def warning(text: str) -> str:
        return f"{YELLOW}{text}{RESET}"


class ModelDiscovery:
    """Dynamic Groq model discovery with fallback chain."""
    
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")
        self.available_models = []
        self.recommended_model = None
        if self.api_key:
            self._discover_models()
    
    def _discover_models(self):
        """Query Groq API for available models at runtime."""
        try:
            from groq import Groq
            client = Groq(api_key=self.api_key)
            models = client.models.list()
            self.available_models = [m.id for m in models.data]
        except Exception as e:
            print(f"{Colors.warning('[!]')} Could not discover Groq models: {e}")
            self.available_models = []
    
    def get_recommended_model(self) -> str:
        """Get best available model with fallback chain."""
        if not self.api_key:
            return "groq-unavailable"
        
        # Preference order (May 2026)
        preferences = [
            "llama-3.3-70b-versatile",      # Primary
            "llama-3.1-8b-instant",          # Fast fallback
            "groq/compound-mini",            # Tools
            "qwen/qwen3-32b",                # Alternative
            "openai/gpt-oss-120b",           # Alternative
        ]
        
        for model in preferences:
            if model in self.available_models:
                return model
        
        # Use first available if nothing matches
        if self.available_models:
            return self.available_models[0]
        
        return "llama-3.3-70b-versatile"  # Last resort default


class ProviderManager:
    """Manage provider configuration and detection."""
    
    PROVIDERS = ["copilot", "claude", "anthropic", "ollama", "groq"]
    
    def __init__(self):
        self.config_dir = Path.home() / ".forestgump"
        self.config_file = self.config_dir / "config.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"provider": "copilot", "model": "claude-haiku-4-5"}
    
    def _save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=2)
            os.chmod(self.config_file, 0o600)  # Owner read/write only
        except Exception as e:
            print(f"{Colors.error('[!]')} Failed to save config: {e}")
    
    def set_provider(self, provider: str, model: str = None):
        """Set active provider and model."""
        if provider not in self.PROVIDERS:
            print(f"{Colors.error('[!]')} Unknown provider: {provider}")
            return False
        self.config["provider"] = provider
        if model:
            self.config["model"] = model
        self._save_config()
        return True
    
    def get_provider(self) -> str:
        """Get default provider from config."""
        return self.config.get("provider", "copilot")
    
    def get_model(self) -> str:
        """Get default model from config."""
        return self.config.get("model", "claude-haiku-4-5")
    
    def detect_api_keys(self) -> Dict[str, bool]:
        """Detect which providers have API keys or are available."""
        return {
            "groq": bool(os.environ.get("GROQ_API_KEY")),
            "claude": self._check_claude_cli(),
            "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "copilot": self._check_copilot(),
            "ollama": self._check_ollama(),
        }
    
    def _check_claude_cli(self) -> bool:
        """Check if Claude CLI is installed."""
        try:
            subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                timeout=2,
                check=False
            )
            return True
        except Exception:
            return False
    
    def _check_copilot(self) -> bool:
        """Check if GitHub Copilot CLI is available."""
        try:
            subprocess.run(
                ["gh", "copilot", "--version"],
                capture_output=True,
                timeout=2,
                check=False
            )
            return True
        except Exception:
            return False
    
    def create_provider(self, provider_name: str, model: str = None):
        """Create and return a provider instance by name.
        
        Args:
            provider_name: Name of provider (groq, claude, anthropic, copilot)
            model: Optional model name/alias to pass to provider
        """
        try:
            if provider_name == "groq":
                return GroqProvider()
            elif provider_name == "claude":
                return ClaudeCliProvider(model=model or "haiku")
            elif provider_name == "anthropic":
                return AnthropicProvider()
            elif provider_name == "copilot":
                return CopilotProvider()
            else:
                print(f"{Colors.error('[!]')} Unknown provider: {provider_name}")
                return None
        except RuntimeError as e:
            print(f"{Colors.error('[!]')} Provider initialization failed: {e}")
            return None
        except Exception as e:
            print(f"{Colors.error('[!]')} Unexpected error creating provider: {e}")
            return None


class SessionManager:
    """Manage session persistence and resumption."""
    
    def __init__(self):
        self.sessions_dir = Path.home() / ".forestgump" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    def save_session(self, task: str, provider: str, model: str, messages: List[Dict] = None) -> str:
        """Save a new session and return session ID."""
        session_id = datetime.now().strftime("%Y%m%dT%H%M%S")
        session_file = self.sessions_dir / f"{session_id}.json"
        
        session_data = {
            "session_id": session_id,
            "task": task,
            "provider": provider,
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "messages": messages or [],
            "state": "active"
        }
        
        try:
            with open(session_file, "w") as f:
                json.dump(session_data, f, indent=2)
            return session_id
        except Exception as e:
            print(f"{Colors.error('[!]')} Failed to save session: {e}")
            return ""
    
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a session by ID."""
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return None
        
        try:
            with open(session_file) as f:
                return json.load(f)
        except Exception as e:
            print(f"{Colors.error('[!]')} Failed to load session: {e}")
            return None
    
    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent sessions."""
        sessions = []
        try:
            session_files = sorted(self.sessions_dir.glob("*.json"), reverse=True)[:limit]
            for session_file in session_files:
                try:
                    with open(session_file) as f:
                        session = json.load(f)
                        sessions.append({
                            "id": session.get("session_id"),
                            "task": session.get("task", "Unknown"),
                            "provider": session.get("provider"),
                            "timestamp": session.get("timestamp"),
                        })
                except Exception:
                    continue
        except Exception as e:
            print(f"{Colors.error('[!]')} Failed to list sessions: {e}")
        
        return sessions
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return False
        
        try:
            session_file.unlink()
            return True
        except Exception as e:
            print(f"{Colors.error('[!]')} Failed to delete session: {e}")
            return False


class InteractiveREPL:
    """Interactive REPL for ForestGump chat sessions."""
    def __init__(self, provider, model: str, provider_name: str, session_dir: Path = None, session_id: str = None, yolo: bool = False, memory=None, system_prompt: str = None):
        
        """
        Initialize the interactive REPL.
        
        Args:
            provider: The LLM provider instance
            model: Model name/identifier
            provider_name: Provider name (groq, claude, etc.)
            session_dir: Directory for session storage
            session_id: Optional existing session ID to resume
            yolo: If True, skip command confirmations (dangerous!)
            memory: Optional MemoryManager instance for session context
            system_prompt: Optional system prompt with memory context
        """
        self.provider = provider
        self.model = model
        self.provider_name = provider_name
        self.session_dir = session_dir or Path.home() / ".forestgump" / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        self.session_id = session_id or None
        self.conversation_history = []
        self.task_description = ""
        self.memory = memory
        self.system_prompt = system_prompt
        
        # Initialize tool sandbox for command parsing and execution
        self.sandbox = Sandbox(timeout=30, yolo=yolo)
        self.command_filter = CommandFilter()
        
        # Load existing session if provided
        if session_id:
            self._load_session(session_id)
    
    def _load_session(self, session_id: str):
        """Load conversation history from existing session."""
        session_file = self.session_dir / f"{session_id}.json"
        if not session_file.exists():
            return
        
        try:
            with open(session_file) as f:
                session_data = json.load(f)
                self.conversation_history = session_data.get("messages", [])
                self.task_description = session_data.get("task", "")
        except Exception as e:
            print(f"{Colors.error('[!]')} Failed to load session: {e}")
    
    def parse_command(self, input_text: str) -> tuple:
        """
        Parse input to identify commands.
        
        Returns:
            (command, args) tuple, or (None, None) for regular messages
        """
        input_text = input_text.strip()
        if not input_text or not input_text.startswith("/"):
            return None, None
        
        parts = input_text[1:].split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1].split() if len(parts) > 1 else []
        
        return command, args
    
    def handle_help(self, args: List[str]):
        """Display help for available commands."""
        help_text = f"""
{Colors.info('ForestGump Interactive Chat - Commands:')}

  /help              Show this help message
  /status            Show current configuration
  /clear             Clear conversation history
  /save              Save current session
  /sessions          List recent sessions
  /load <session_id> Load a previous session
  /exit or Ctrl+D    Save and exit

Type regular messages to chat. Messages are automatically saved after each turn.
"""
        print(help_text)
    
    def handle_status(self, args: List[str]):
        """Display current REPL status."""
        turn_count = self.get_turn_count()
        max_turns = 50
        
        print(f"""
{Colors.info('Current Configuration:')}
  Provider: {self.provider_name}
  Model: {self.model}
  Session: {self.session_id or 'new'}
  Turn: {turn_count}/{max_turns}
  Messages: {len(self.conversation_history)}
""")
    
    def handle_clear(self, args: List[str]):
        """Clear conversation history."""
        self.conversation_history = []
        print(f"{Colors.success('[+]')} Conversation cleared.")
    
    def handle_save(self, args: List[str]):
        """Save current session."""
        session_id = self.save_session()
        print(f"{Colors.success('[+]')} Session saved: {session_id}")
    
    def handle_sessions(self, args: List[str]):
        """List recent sessions."""
        sessions = self.list_sessions(limit=10)
        if not sessions:
            print(f"{Colors.warning('[!]')} No sessions found.\n")
            return
        
        print(f"\n{Colors.info('Recent Sessions:')}")
        for session in sessions:
            session_id = session.get("id") or "unknown"
            task = (session.get("task") or "unknown")[:40]
            print(f"  {session_id:<20} | {task}")
        print()
    
    def handle_load(self, args: List[str]):
        """Load a previous session."""
        if not args:
            print(f"{Colors.error('[!]')} Usage: /load <session_id>\n")
            return False
        
        session_id = args[0]
        session_file = self.session_dir / f"{session_id}.json"
        
        if not session_file.exists():
            print(f"{Colors.error('[!]')} Session not found: {session_id}\n")
            return False
        
        self._load_session(session_id)
        self.session_id = session_id
        print(f"{Colors.success('[+]')} Loaded session: {session_id}")
        print(f"  Messages: {len(self.conversation_history)}")
        print()
        return True
    
    def handle_exit(self, args: List[str]) -> bool:
        """Handle exit command."""
        if self.conversation_history:
            self.save_session()
            print(f"{Colors.success('[+]')} Session saved before exit.")
        print(f"{Colors.info('[*]')} Exiting ForestGump.\n")
        return True
    
    def append_message(self, role: str, content: str):
        """Append a message to conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content
        })
    
    def save_session(self) -> str:
        """Save current session to disk."""
        if not self.session_id:
            self.session_id = datetime.now().strftime("%Y%m%dT%H%M%S")
        
        session_file = self.session_dir / f"{self.session_id}.json"
        session_data = {
            "session_id": self.session_id,
            "task": self.task_description,
            "provider": self.provider_name,
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
            "messages": self.conversation_history,
            "state": "active"
        }
        
        try:
            with open(session_file, "w") as f:
                json.dump(session_data, f, indent=2)
            return self.session_id
        except Exception as e:
            print(f"{Colors.error('[!]')} Failed to save session: {e}")
            return ""
    
    def list_sessions(self, limit: int = 10) -> List[Dict[str, str]]:
        """List recent sessions."""
        sessions = []
        try:
            session_files = sorted(self.session_dir.glob("*.json"), reverse=True)[:limit]
            for session_file in session_files:
                try:
                    with open(session_file) as f:
                        session = json.load(f)
                        sessions.append({
                            "id": session.get("session_id", "unknown"),
                            "task": session.get("task", "Untitled"),
                            "provider": session.get("provider", "unknown"),
                            "timestamp": session.get("timestamp", "unknown"),
                        })
                except Exception:
                    continue
        except Exception as e:
            print(f"{Colors.error('[!]')} Failed to list sessions: {e}")
        
        return sessions
    
    def get_turn_count(self) -> int:
        """Get the number of complete turns (user-assistant pairs)."""
        # Count pairs where we have both user and assistant messages
        pairs = 0
        for i in range(0, len(self.conversation_history) - 1, 2):
            if (i + 1 < len(self.conversation_history) and 
                self.conversation_history[i].get("role") == "user" and
                self.conversation_history[i + 1].get("role") == "assistant"):
                pairs += 1
        return pairs
    
    def format_user_message(self, content: str) -> str:
        """Format user message with color."""
        return f"{CYAN}You: {content}{RESET}"
    
    def format_assistant_message(self, content: str) -> str:
        """Format assistant message with color."""
        return f"{GREEN}Assistant: {content}{RESET}"
    
    def format_error_message(self, content: str) -> str:
        """Format error message with color."""
        return f"{RED}Error: {content}{RESET}"
    
    def extract_and_handle_commands(self, response: str) -> str:
        """
        Extract commands from response and prompt user for execution.
        
        Args:
            response: Assistant response text
            
        Returns:
            Feedback text about command execution (if any)
        """
        commands = self.sandbox.parse_response(response)
        if not commands:
            return ""
        
        # Filter and prioritize
        commands = self.command_filter.filter_commands(commands)
        commands = self.command_filter.prioritize_commands(commands)
        
        if not commands:
            return ""
        
        # Validate commands
        validation = self.command_filter.validate_commands(commands)
        
        # Show summary
        print(f"\n{Colors.warning('[*]')} Found {len(commands)} command(s) in response")
        
        feedback_parts = []
        
        # Handle safe commands
        for cmd_info in validation['safe']:
            cmd = cmd_info['command']
            success, output = self.sandbox.execute_and_feedback(cmd)
            feedback_parts.append(f"SAFE: {cmd}\n{output}")
            if success:
                print(f"{Colors.success('[+]')} Executed safe command")
            else:
                print(f"{Colors.error('[!]')} Safe command failed: {output[:100]}")
        
        # Handle dangerous commands - requires user confirmation
        for cmd_info in validation['dangerous']:
            cmd = cmd_info['command']
            reason = cmd_info['reason']
            print(f"{Colors.error('[!]')} DANGEROUS: {cmd}")
            print(f"    Reason: {reason}")
            feedback_parts.append(f"BLOCKED (dangerous): {cmd}\n{reason}")
        
        # Handle unknown commands - ask user
        for cmd_info in validation['unknown']:
            cmd = cmd_info['command']
            conf = cmd_info['confidence']
            print(f"{Colors.warning('[?]')} UNKNOWN (confidence: {conf:.1%}): {cmd}")
            if self.sandbox.confirm_execution(cmd):
                success, output = self.sandbox.execute_and_feedback(cmd)
                feedback_parts.append(f"UNKNOWN: {cmd}\n{output}")
                if success:
                    print(f"{Colors.success('[+]')} Executed unknown command")
                else:
                    print(f"{Colors.error('[!]')} Unknown command failed")
        
        return "\n".join(feedback_parts)
    
    
    def print_welcome(self):
        """Print welcome banner."""
        print(f"\n{Colors.info('╔════════════════════════════════════════╗')}")
        print(f"{Colors.info('║  ForestGump Interactive Chat            ║')}")
        print(f"{Colors.info('║  Provider: ' + self.provider_name + ' ' * (30 - len(self.provider_name)) + '║')}")
        print(f"{Colors.info('║  Model: ' + self.model + ' ' * (32 - len(self.model)) + '║')}")
        print(f"{Colors.info('╚════════════════════════════════════════╝')}\n")
        
        if self.session_id:
            turn_count = self.get_turn_count()
            print(f"{Colors.info('[*]')} Resumed session: {self.session_id} (Turn {turn_count})\n")
        
        print(f"{Colors.warning('[?]')} Type /help for commands or Ctrl+D to exit.\n")
    
    def print_prompt(self) -> str:
        """Print the input prompt and return the user input."""
        try:
            model_short = self.model.split("/")[-1][:20]
            prompt = f"{Colors.info(model_short)}> {RESET}"
            return input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C or Ctrl+D
            return "/exit"
    
    def run(self):
        """Main REPL loop."""
        self.print_welcome()
        
        while True:
            try:
                user_input = self.print_prompt()
                
                if not user_input:
                    continue
                
                # Parse command or regular message
                command, args = self.parse_command(user_input)
                
                if command:
                    # Handle special commands
                    if command == "help":
                        self.handle_help(args)
                    elif command == "status":
                        self.handle_status(args)
                    elif command == "clear":
                        self.handle_clear(args)
                    elif command == "save":
                        self.handle_save(args)
                    elif command == "sessions":
                        self.handle_sessions(args)
                    elif command == "load":
                        self.handle_load(args)
                    elif command == "exit":
                        if self.handle_exit(args):
                            break
                    else:
                        print(f"{Colors.error('[!]')} Unknown command: /{command}")
                        print(f"{Colors.info('[?]')} Type /help for available commands.\n")
                else:
                    # Regular message - send to provider
                    self.append_message("user", user_input)
                    print(self.format_user_message(user_input))
                    
                    # Get response from provider
                    try:
                        print(f"{Colors.warning('[*]')} Thinking...", end="", flush=True)
                        
                        # Build messages list for provider API
                        # Include system prompt if available, then conversation history
                        messages = []
                        if self.system_prompt:
                            messages.append({"role": "system", "content": self.system_prompt})
                        
                        # Add conversation history (skip any system messages already added)
                        for msg in self.conversation_history:
                            if msg.get("role") != "system" or not self.system_prompt:
                                messages.append(msg)
                        
                        # Call provider's chat method with formatted messages
                        response = self.provider.chat(messages, self.system_prompt)
                        
                        print("\r", end="")  # Clear the "Thinking..." line
                        print(self.format_assistant_message(response))
                        print()
                        
                        # Add response to history
                        self.append_message("assistant", response)
                        
                        # Extract and handle commands from response
                        cmd_feedback = self.extract_and_handle_commands(response)
                        if cmd_feedback:
                            print(f"\n{Colors.info('[*]')} Command execution feedback:")
                            print(cmd_feedback)
                            print()
                        
                        # Auto-save after each turn
                        self.save_session()
                        
                    except subprocess.TimeoutExpired:
                        print("\r", end="")  # Clear the "Thinking..." line
                        error_msg = f"Request timed out (30 seconds). Please try again."
                        print(self.format_error_message(error_msg))
                        print()
                    except RuntimeError as e:
                        print("\r", end="")  # Clear the "Thinking..." line
                        error_msg = f"Provider error: {str(e)}"
                        print(self.format_error_message(error_msg))
                        print()
                    except Exception as e:
                        print("\r", end="")  # Clear the "Thinking..." line
                        error_msg = f"Unexpected error: {str(e)}"
                        print(self.format_error_message(error_msg))
                        print()
                        
            except KeyboardInterrupt:
                print(f"\n{Colors.warning('[!]')} Interrupted. Use /exit to save and quit.\n")
            except EOFError:
                # Ctrl+D
                if self.handle_exit([]):
                    break


class ForestGumpCLI:
    """Main ForestGump CLI interface (Hermes-compatible)."""
    
    def __init__(self):
        self.providers = ProviderManager()
        self.sessions = SessionManager()
        self.models = ModelDiscovery()
    
    def chat(self, args):
        """Start a chat session with memory context injection."""
        # Try to import MemoryManager if available
        try:
            from memory import MemoryManager
        except (ImportError, ModuleNotFoundError):
            MemoryManager = None
        
        print(f"\n{Colors.info('╔════════════════════════════════════════╗')}")
        print(f"{Colors.info('║  ForestGump Chat - Pentesting Agent    ║')}")
        print(f"{Colors.info('╚════════════════════════════════════════╝')}\n")
        
        # Determine provider and model
        provider = args.provider or self.providers.get_provider()
        model = args.model or self.models.get_recommended_model()
        
        if not args.quiet:
            print(f"{Colors.info('[*]')} Provider: {provider}")
            print(f"{Colors.info('[*]')} Model: {model}")
            if args.query:
                print(f"{Colors.info('[*]')} Query: {args.query}")
        
        # Determine session_id (resume or new)
        if args.resume:
            session_id = args.resume
            session = self.sessions.load_session(session_id)
            if not session:
                print(f"{Colors.error('[!]')} Session not found: {session_id}\n")
                return
            if not args.quiet:
                print(f"{Colors.success('[+]')} Resumed session: {session_id}\n")
        elif args.__dict__.get('continue'):
            # Resume most recent session
            recent = self.sessions.list_sessions(limit=1)
            if not recent:
                print(f"{Colors.error('[!]')} No recent sessions found\n")
                return
            session_id = recent[0]["id"]
            session = self.sessions.load_session(session_id)
            if not args.quiet:
                print(f"{Colors.success('[+]')} Resumed session: {session_id}\n")
        else:
            # Create new session
            query = args.query or "Interactive pentesting session"
            session_id = self.sessions.save_session(query, provider, model)
            session = {"session_id": session_id, "task": query, "messages": []}
            if not args.quiet:
                print(f"{Colors.success('[+]')} Session ID: {session_id}\n")
        
        # Load memory manager for this session (if available)
        if MemoryManager:
            memory = MemoryManager(session_id)
        else:
            memory = None
        
        # Build system prompt with memory context (if memory available)
        if memory:
            system_prompt = self._build_system_prompt(memory)
            if not args.quiet and memory.get_context():
                print(f"{Colors.info('[*]')} Memory context loaded\\n")
        else:
            system_prompt = None
        
        # Create real provider instance
        real_provider = self.providers.create_provider(provider)
        if not real_provider:
            print(f"{Colors.error('[!]')} Failed to initialize provider: {provider}")
            print(f"{Colors.warning('[*]')} Falling back to demo mode\n")
            real_provider = self._create_mock_provider(provider, model)
        elif not real_provider.is_available:
            print(f"{Colors.warning('[!]')} Provider {provider} not available")
            print(f"{Colors.warning('[*]')} Falling back to demo mode\n")
            real_provider = self._create_mock_provider(provider, model)
        
        # Handle single query mode
        if args.query:
            if not args.quiet:
                print(f"{Colors.info('[*]')} Processing query...\n")
            
            # Build messages list for provider
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": args.query})
            
            # Call provider with error handling
            try:
                if not args.quiet:
                    print(f"{Colors.info('[*]')} Waiting for response from {provider}...")
                
                response = real_provider.chat(messages, system_prompt)
                
                if not response:
                    print(f"{Colors.error('[!]')} Provider returned empty response\n")
                    return
                
                if not args.quiet:
                    print()  # Newline after status message
                
                print(f"{GREEN}Response:{RESET}")
                print(response)
                print()
                
            except subprocess.TimeoutExpired:
                print(f"\r{Colors.error('[!]')} Request timed out (30 seconds). Please try again.\n")
                return
            except RuntimeError as e:
                error_msg = str(e)
                print(f"\r{Colors.error('[!]')} Provider error: {error_msg}\n")
                if "not available" in error_msg.lower():
                    print(f"{Colors.warning('[*]')} Tip: Check that {provider} is properly configured\n")
                return
            except Exception as e:
                print(f"\r{Colors.error('[!]')} Unexpected error: {str(e)}\n")
                return
            
            # Save session with memory snapshot
            session["messages"] = messages
            if memory:
                session["memory_snapshot"] = {
                    "facts": memory.memory.get("facts", []),
                    "credentials": memory.memory.get("credentials", {}),
                    "networks": list(memory.memory.get("networks", {}).keys()),
                    "notes": memory.memory.get("notes", []),
                }
                memory.save()
            self.sessions.save_session(args.query, provider, model, session.get("messages", []))
            return
        
        # Interactive mode - use real provider
        # Enter interactive REPL
        repl = InteractiveREPL(
            provider=real_provider,
            model=model,
            provider_name=provider,
            session_dir=self.sessions.sessions_dir,
            session_id=session_id,
            yolo=args.yolo,
            memory=memory,
            system_prompt=system_prompt
        )
        repl.run()
    
    def _create_mock_provider(self, provider_name: str, model: str):
        """Create a mock provider for testing. In production, use real provider."""
        class MockProvider:
            def __init__(self, name: str, model: str):
                self.name = name
                self.model = model
            
            def chat(self, message: str, history: List[Dict] = None) -> str:
                # Mock response - in production, call real API
                return f"[Mock {self.name}] This is a demo response to: {message}"
        
        return MockProvider(provider_name, model)
    
    def _build_system_prompt(self, memory) -> str:
        """Build system prompt with memory context injection.
        
        Args:
            memory: MemoryManager instance for the session
            
        Returns:
            Complete system prompt including memory context
        """
        base_prompt = """You are a pentesting agent running on Kali Linux. You have access to:
- nmap: Network scanning and enumeration
- netcat: Network communication and testing
- metasploit: Exploit framework and tools
- aircrack-ng: WiFi security testing
- hashcat: Password cracking
- sqlmap: SQL injection testing
- And other standard penetration testing tools

Your role is to help with authorized security testing and vulnerability assessment.
Always respect scope and legal boundaries."""
        
        memory_context = memory.get_context()
        
        if memory_context:
            return f"""{base_prompt}

Memory Context (Previous Session Information):
{memory_context}"""
        else:
            return base_prompt
    
    def model_select(self, args):
        """Select default model and provider."""
        if args.list:
            # List available providers
            print(f"\n{Colors.info('Available Providers:')}")
            api_keys = self.providers.detect_api_keys()
            for provider in self.providers.PROVIDERS:
                status = Colors.success("✓ configured") if api_keys[provider] else Colors.error("✗ not configured")
                print(f"  {provider:<15} {status}")
            print()
            return
        
        if args.provider or args.model:
            provider = args.provider or self.providers.get_provider()
            model = args.model or self.providers.get_model()
            self.providers.set_provider(provider, model)
            print(f"{Colors.success('[+]')} Set provider: {provider}, model: {model}\n")
            return
        
        # Interactive selection (placeholder)
        print(f"{Colors.warning('[!]')} Interactive model selection not yet implemented\n")
    
    def sessions_cmd(self, args):
        """Manage sessions."""
        if args.action == "list":
            sessions = self.sessions.list_sessions(args.limit)
            if not sessions:
                print(f"{Colors.warning('[!]')} No sessions found\n")
                return
            
            print(f"\n{Colors.info('Recent Sessions:')}")
            for session in sessions:
                session_id = session.get("id") or "unknown"
                provider = session.get("provider") or "unknown"
                timestamp = (session.get("timestamp") or "unknown")[:19]
                task = (session.get("task") or "unknown")[:40]
                print(f"  {session_id:<20} | {provider:<8} | {timestamp} | {task}")
            print()
            return
        
        elif args.action == "resume":
            if not args.session_id:
                print(f"{Colors.error('[!]')} Session ID required\n")
                return
            
            session = self.sessions.load_session(args.session_id)
            if not session:
                print(f"{Colors.error('[!]')} Session not found: {args.session_id}\n")
                return
            
            print(f"{Colors.success('[+]')} Resumed session: {args.session_id}")
            print(f"  Task: {session.get('task')}")
            print(f"  Provider: {session.get('provider')}\n")
            return
        
        elif args.action == "delete":
            if not args.session_id:
                print(f"{Colors.error('[!]')} Session ID required\n")
                return
            
            if self.sessions.delete_session(args.session_id):
                print(f"{Colors.success('[+]')} Deleted session: {args.session_id}\n")
            else:
                print(f"{Colors.error('[!]')} Failed to delete session\n")
            return
    
    def status(self, args):
        """Show system status."""
        print(f"\n{Colors.info('ForestGump Status:')}")
        print(f"  Version: {VERSION}")
        print(f"  Config: {self.providers.config_file}")
        print(f"  Sessions: {self.sessions.sessions_dir}")
        
        api_keys = self.providers.detect_api_keys()
        print(f"\n{Colors.info('Provider Status:')}")
        for provider, configured in api_keys.items():
            status = Colors.success("✓") if configured else Colors.error("✗")
            print(f"  {status} {provider}")
        
        print(f"\n{Colors.info('Available Models:')}")
        if self.models.available_models:
            for model in self.models.available_models[:5]:
                print(f"  • {model}")
            if len(self.models.available_models) > 5:
                print(f"  ... and {len(self.models.available_models) - 5} more")
        else:
            print(f"  {Colors.warning('(Groq API not configured)')}")
        
        print()
    
    def config(self, args):
        """View configuration."""
        print(f"\n{Colors.info('Configuration:')}")
        print(json.dumps(self.providers.config, indent=2))
        print()
    
    def version(self, args):
        """Show version."""
        print(f"ForestGump {VERSION}")


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser matching Hermes' structure."""
    parser = argparse.ArgumentParser(
        prog="forestgump",
        description="ForestGump - Hermes-compatible pentesting agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument("--version", "-V", action="store_true", help="Show version and exit")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # chat command
    chat_parser = subparsers.add_parser("chat", help="Start interactive chat session")
    chat_parser.add_argument("-q", "--query", help="Single query (non-interactive mode)")
    chat_parser.add_argument("-m", "--model", help="Model to use")
    chat_parser.add_argument("--provider", help="Provider (groq, claude, anthropic, copilot)")
    chat_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    chat_parser.add_argument("-Q", "--quiet", action="store_true", help="Quiet mode")
    chat_parser.add_argument("--yolo", action="store_true", help="Bypass confirmations")
    chat_parser.add_argument("--resume", help="Resume session by ID")
    chat_parser.add_argument("-c", "--continue", action="store_true", help="Resume most recent session")
    chat_parser.add_argument("-t", "--toolsets", help="Comma-separated toolsets to enable")
    
    # model command
    model_parser = subparsers.add_parser("model", help="Select default model and provider")
    model_parser.add_argument("-l", "--list", action="store_true", help="List available providers")
    model_parser.add_argument("-m", "--model", help="Set default model")
    model_parser.add_argument("-p", "--provider", help="Set default provider")
    
    # sessions command
    sessions_parser = subparsers.add_parser("sessions", help="Manage session history")
    sessions_subparsers = sessions_parser.add_subparsers(dest="action", help="Session action")
    
    list_parser = sessions_subparsers.add_parser("list", help="List recent sessions")
    list_parser.add_argument("--limit", type=int, default=20, help="Number of sessions to show")
    
    resume_parser = sessions_subparsers.add_parser("resume", help="Resume a session")
    resume_parser.add_argument("session_id", help="Session ID to resume")
    
    delete_parser = sessions_subparsers.add_parser("delete", help="Delete a session")
    delete_parser.add_argument("session_id", help="Session ID to delete")
    
    # status command
    subparsers.add_parser("status", help="Show system status")
    
    # config command
    subparsers.add_parser("config", help="View configuration")
    
    # version command
    subparsers.add_parser("version", help="Show version information")
    
    return parser


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()
    
    cli = ForestGumpCLI()
    
    # Handle global --version flag
    if args.version:
        cli.version(args)
        return
    
    # Handle commands
    if args.command == "chat":
        cli.chat(args)
    elif args.command == "model":
        cli.model_select(args)
    elif args.command == "sessions":
        cli.sessions_cmd(args)
    elif args.command == "status":
        cli.status(args)
    elif args.command == "config":
        cli.config(args)
    elif args.command == "version":
        cli.version(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
