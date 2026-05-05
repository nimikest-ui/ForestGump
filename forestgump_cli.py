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

# ANSI colors
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

VERSION = "2.0.0-hermes-compatible"
CONFIG_DIR = Path.home() / ".forestgump"
SESSIONS_DIR = Path("/root/ForestGump/sessions")


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
    
    PROVIDERS = ["groq", "claude", "anthropic", "copilot", "ollama"]
    
    def __init__(self):
        self.config_file = CONFIG_DIR / "config.json"
        CONFIG_DIR.mkdir(exist_ok=True)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"provider": "groq", "model": "llama-3.3-70b-versatile"}
    
    def _save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=2)
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
        """Get active provider."""
        return self.config.get("provider", "groq")
    
    def get_model(self) -> str:
        """Get active model."""
        return self.config.get("model", "llama-3.3-70b-versatile")
    
    def detect_api_keys(self) -> Dict[str, bool]:
        """Detect which providers have API keys configured."""
        return {
            "groq": bool(os.environ.get("GROQ_API_KEY")),
            "claude": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "copilot": bool(os.environ.get("COPILOT_API_KEY")),
            "ollama": self._check_ollama(),
        }
    
    def _check_ollama(self) -> bool:
        """Check if Ollama is running locally."""
        try:
            subprocess.run(
                ["curl", "-s", "http://localhost:11434/api/tags"],
                capture_output=True,
                timeout=2,
                check=False
            )
            return True
        except Exception:
            return False


class SessionManager:
    """Manage session persistence and resumption."""
    
    def __init__(self):
        SESSIONS_DIR.mkdir(exist_ok=True)
    
    def save_session(self, task: str, provider: str, model: str, messages: List[Dict] = None) -> str:
        """Save a new session and return session ID."""
        session_id = datetime.now().strftime("%Y%m%dT%H%M%S")
        session_file = SESSIONS_DIR / f"{session_id}.json"
        
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
        session_file = SESSIONS_DIR / f"{session_id}.json"
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
            session_files = sorted(SESSIONS_DIR.glob("*.json"), reverse=True)[:limit]
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
        session_file = SESSIONS_DIR / f"{session_id}.json"
        if not session_file.exists():
            return False
        
        try:
            session_file.unlink()
            return True
        except Exception as e:
            print(f"{Colors.error('[!]')} Failed to delete session: {e}")
            return False


class ForestGumpCLI:
    """Main ForestGump CLI interface (Hermes-compatible)."""
    
    def __init__(self):
        self.providers = ProviderManager()
        self.sessions = SessionManager()
        self.models = ModelDiscovery()
    
    def chat(self, args):
        """Start a chat session."""
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
        
        # Handle single query mode
        if args.query:
            session_id = self.sessions.save_session(args.query, provider, model)
            if not args.quiet:
                print(f"{Colors.success('[+]')} Session ID: {session_id}\n")
            
            # Placeholder: actual chat logic would go here in phase 2
            print(f"{Colors.info('[*]')} Processing query (demo mode)...")
            print(f"Response would be displayed here.\n")
            return
        
        # Interactive mode placeholder
        print(f"{Colors.warning('[!]')} Interactive mode not yet implemented (demo mode)\n")
    
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
        print(f"  Sessions: {SESSIONS_DIR}")
        
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
