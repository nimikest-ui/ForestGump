#!/usr/bin/env python3
"""
ForestGump CLI: Hermes-compatible command-line interface for the bare-metal pentesting agent.

This module is now a thin wrapper around menu.py for backward compatibility.
All functionality has been merged into menu.py which serves as both:
- Interactive menu system (when called without arguments)
- CLI with subcommands (when called with arguments)

Usage:
  forestgump [COMMAND] [OPTIONS]
  python menu.py [COMMAND] [OPTIONS]

Commands:
  chat           Start interactive pentesting session
  model          Select/list available LLM providers and models
  skills         Browse learned attack patterns
  memory         View/manage persistent memory
  sessions       Manage session history
  config         Configure settings
  gateway        Manage messaging gateways
  schedule       Manage scheduled tasks
  monitor        View metrics and monitoring
  subagents      Manage subagent tasks
  memory-advanced Advanced memory search and statistics
  version        Show version information
"""

# Import and re-export all CLI functionality from menu.py
from menu import (
    main,
    cmd_chat,
    cmd_model,
    cmd_skills,
    cmd_memory,
    cmd_sessions,
    cmd_config,
    cmd_gateway,
    cmd_schedule,
    cmd_monitor,
    cmd_subagents,
    cmd_memory_advanced,
    cmd_version,
)

__all__ = [
    'main',
    'cmd_chat',
    'cmd_model',
    'cmd_skills',
    'cmd_memory',
    'cmd_sessions',
    'cmd_config',
    'cmd_gateway',
    'cmd_schedule',
    'cmd_monitor',
    'cmd_subagents',
    'cmd_memory_advanced',
    'cmd_version',
]

if __name__ == '__main__':
    import sys
    sys.exit(main())
