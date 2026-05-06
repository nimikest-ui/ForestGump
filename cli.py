#!/usr/bin/env python3
"""
ForestGump CLI: Hermes-compatible command-line interface for the bare-metal pentesting agent.

Usage:
  forestgump [COMMAND] [OPTIONS]

Commands:
  chat       Start interactive pentesting session
  model      Select/list available LLM providers and models
  skills     Browse learned attack patterns
  memory     View/manage persistent memory
  sessions   Manage session history
  config     Configure settings
  version    Show version information
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

import theme
from theme import Colors, Symbols, fmt, banner, success, error, warning, info

__version__ = '0.2.0'


def cmd_chat(args):
    """Start an interactive pentesting session."""
    from agent import run_agent

    task = args.task if hasattr(args, 'task') and args.task else ' '.join(args.task_args) if hasattr(args, 'task_args') else None
    if not task:
        print(error(f'{Symbols.CROSS} No task specified'))
        print(f'Usage: forestgump chat "<your pentesting task>"')
        return 1

    # Pass through to agent
    return run_agent(
        task=task,
        provider=args.provider or 'claude',
        model=args.model,
        no_confirm=args.no_confirm,
        max_turns=args.max_turns,
        resume_session=args.resume,
    )


def cmd_model(args):
    """List and select LLM providers/models."""
    import json
    from pathlib import Path

    providers = {
        'claude': {
            'name': 'Claude Code CLI',
            'models': ['claude-opus', 'claude-sonnet', 'claude-haiku'],
            'requires': 'OAuth (built-in)',
        },
        'anthropic': {
            'name': 'Anthropic API',
            'models': ['claude-opus', 'claude-sonnet', 'claude-haiku'],
            'requires': 'ANTHROPIC_API_KEY env var',
        },
        'ollama': {
            'name': 'Ollama (local/cloud)',
            'models': [
                'llama3.2:latest',
                'mistral:latest',
                'glm-5-cloud',
                'gemma2:27b',
            ],
            'requires': 'Local: http://localhost:11434; Cloud: OLLAMA_API_KEY',
        },
        'copilot': {
            'name': 'GitHub Copilot CLI',
            'models': ['claude-sonnet-4.5', 'claude-sonnet-4.6', 'gpt-5.4'],
            'requires': 'GitHub CLI + Copilot CLI extension',
        },
    }

    if args.list:
        print(banner('\n⚙️  Available LLM Providers'))
        for provider, info in providers.items():
            print(f'\n{fmt(provider.upper(), Colors.GOLD, bold=True)}')
            print(f'  {info["name"]}')
            print(f'  Requires: {info["requires"]}')
            print(f'  Models: {", ".join(info["models"][:3])}...')

        print(f'\n{banner("Usage:")} forestgump chat --provider claude "your task"')
        print(f'         forestgump chat --provider ollama --model llama3.2:latest "your task"')
        return 0

    if args.set:
        # Save default provider/model to config
        config_dir = Path.home() / '.forestgump'
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / 'config.json'

        config = {}
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = json.load(f)

        provider, model = args.set.split(':') if ':' in args.set else (args.set, None)
        config['default_provider'] = provider
        if model:
            config['default_model'] = model

        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        print(success(f'{Symbols.CHECK} Default provider set to {provider}'))
        if model:
            print(success(f'{Symbols.CHECK} Default model set to {model}'))
        return 0

    return 0


def cmd_skills(args):
    """Browse and manage learned attack patterns."""
    from skill_manager import list_all_skills, search_skills, get_skill
    from pathlib import Path
    import json

    if args.search:
        print(banner(f'\n🎯 Searching for "{args.search}"'))
        skills = search_skills(args.search, limit=10)

        if not skills:
            print(warning(f'  No skills found for "{args.search}"'))
            return 0

        for skill in skills:
            eff = (skill['success_rate'] * max(1, skill['use_count']) * 100) - (skill['best_session_turns'] or 999)
            print(f'\n  {fmt(skill["name"], Colors.GOLD, bold=True)}')
            print(f'    Success rate: {skill["success_rate"]:.0%} | Used: {skill["use_count"]}x | Efficiency: {eff:.0f}')
            if skill['problem']:
                print(f'    Problem: {skill["problem"]}')
            if skill['template']:
                print(f'    Template: {skill["template"][:60]}...' if len(skill['template']) > 60 else f'    Template: {skill["template"]}')
        return 0

    if args.list:
        print(banner('\n📚 All Learned Skills'))
        skills = list_all_skills()
        if not skills:
            print('  No skills yet. Run pentesting tasks to learn them!')
            return 0

        for skill in skills[:20]:  # Show top 20
            print(f'  • {skill["name"]} ({skill["success_rate"]:.0%})')
        if len(skills) > 20:
            print(f'  ... and {len(skills) - 20} more')
        return 0

    return 0


def cmd_memory(args):
    """View and manage persistent memory."""
    from memory_manager import get_all_by_type, search_memory, get_memory_context

    if args.search:
        print(banner(f'\n🧠 Searching memory for "{args.search}"'))
        results = search_memory(args.search, limit=10)

        if not results:
            print(warning(f'  No memories found for "{args.search}"'))
            return 0

        for mem in results:
            print(f'\n  [{mem["type"].upper()}] Confidence: {mem.get("confidence", 0.8):.0%}')
            content = mem['content'][:100] + '...' if len(mem['content']) > 100 else mem['content']
            print(f'    {content}')
        return 0

    if args.list:
        for type_ in ['fact', 'network', 'credential', 'insight', 'technique']:
            mems = get_all_by_type(type_)
            if mems:
                print(f'\n{banner(type_.upper())}')
                for mem in mems[:5]:
                    print(f'  • {mem["content"][:70]}...' if len(mem['content']) > 70 else f'  • {mem["content"]}')

        return 0

    if args.summary:
        context = get_memory_context()
        if context:
            print(context)
        else:
            print(info('  No memories yet.'))
        return 0

    return 0


def cmd_sessions(args):
    """Manage session history."""
    from pathlib import Path
    import json
    from datetime import datetime

    sessions_dir = Path(__file__).parent / 'sessions'
    if not sessions_dir.exists():
        print(warning('  No sessions yet.'))
        return 0

    sessions = sorted(sessions_dir.glob('*.json'), reverse=True)[:20]

    if args.list:
        print(banner('\n📋 Recent Sessions'))
        for session_file in sessions:
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)
                task = data.get('task', 'unknown')[:40]
                timestamp = session_file.stem
                print(f'  {fmt(timestamp, Colors.AMBER)}  {task}')
            except:
                pass
        return 0

    if args.resume:
        # Find session file
        session_file = sessions_dir / f'{args.resume}.json'
        if not session_file.exists():
            print(error(f'{Symbols.CROSS} Session not found: {args.resume}'))
            return 1

        from agent import run_agent
        print(success(f'{Symbols.CHECK} Resuming session {args.resume}'))
        return run_agent(resume_session=str(session_file))

    return 0


def cmd_config(args):
    """Configure ForestGump settings."""
    from pathlib import Path
    import json

    config_dir = Path.home() / '.forestgump'
    config_file = config_dir / 'config.json'

    if args.show:
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = json.load(f)
            print(banner('\n⚙️  Current Configuration'))
            for key, val in config.items():
                print(f'  {key}: {val}')
        else:
            print(info('  No config file yet. Run commands to create default config.'))
        return 0

    return 0


def cmd_version(args):
    """Show version information."""
    print(f'ForestGump v{__version__} (Hermes-compatible pentesting agent)')
    print(f'Theme: Hermes gold/amber/bronze')
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='forestgump',
        description='Hermes-compatible bare-metal pentesting agent',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--version', action='store_true', help='Show version')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # chat
    chat_parser = subparsers.add_parser('chat', help='Start interactive pentesting session')
    chat_parser.add_argument('task_args', nargs='*', help='Task description')
    chat_parser.add_argument('--provider', help='LLM provider (claude, ollama, anthropic, copilot)')
    chat_parser.add_argument('--model', help='Model name')
    chat_parser.add_argument('--no-confirm', action='store_true', help='Skip command confirmation')
    chat_parser.add_argument('--max-turns', type=int, default=50, help='Max conversation turns')
    chat_parser.add_argument('--resume', help='Resume from session file')
    chat_parser.set_defaults(func=cmd_chat)

    # model
    model_parser = subparsers.add_parser('model', help='Select/list LLM providers')
    model_parser.add_argument('--list', action='store_true', help='List available providers')
    model_parser.add_argument('--set', help='Set default provider (e.g., claude, ollama:llama3.2:latest)')
    model_parser.set_defaults(func=cmd_model)

    # skills
    skills_parser = subparsers.add_parser('skills', help='Browse learned patterns')
    skills_parser.add_argument('--search', help='Search skills')
    skills_parser.add_argument('--list', action='store_true', help='List all skills')
    skills_parser.set_defaults(func=cmd_skills)

    # memory
    memory_parser = subparsers.add_parser('memory', help='View/manage persistent memory')
    memory_parser.add_argument('--search', help='Search memory')
    memory_parser.add_argument('--list', action='store_true', help='List all memories by type')
    memory_parser.add_argument('--summary', action='store_true', help='Show memory summary')
    memory_parser.set_defaults(func=cmd_memory)

    # sessions
    sessions_parser = subparsers.add_parser('sessions', help='Manage session history')
    sessions_parser.add_argument('--list', action='store_true', help='List recent sessions')
    sessions_parser.add_argument('--resume', help='Resume session by timestamp')
    sessions_parser.set_defaults(func=cmd_sessions)

    # config
    config_parser = subparsers.add_parser('config', help='Configure settings')
    config_parser.add_argument('--show', action='store_true', help='Show current config')
    config_parser.set_defaults(func=cmd_config)

    # version
    version_parser = subparsers.add_parser('version', help='Show version')
    version_parser.set_defaults(func=cmd_version)

    args = parser.parse_args()

    if args.version or (not args.command and '--version' in sys.argv):
        return cmd_version(args)

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, 'func'):
        return args.func(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
