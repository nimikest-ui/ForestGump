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
    import os
    from agent import run_agent, ClaudeCliProvider, AnthropicProvider, CopilotProvider, OllamaProvider

    # Clear screen before starting
    os.system('clear' if os.name != 'nt' else 'cls')

    task = args.task if hasattr(args, 'task') and args.task else ' '.join(args.task_args) if hasattr(args, 'task_args') else None
    if not task:
        print(error(f'{Symbols.CROSS} No task specified'))
        print(f'Usage: forestgump chat "<your pentesting task>"')
        return 1

    # Instantiate provider object (matching agent.py's main() logic)
    provider_name = args.provider or 'claude'

    if provider_name == 'claude':
        provider = ClaudeCliProvider(args.model or 'haiku')
    elif provider_name == 'anthropic':
        if not os.environ.get('ANTHROPIC_API_KEY'):
            print(error(f'{Symbols.CROSS} Set ANTHROPIC_API_KEY environment variable'))
            return 1
        provider = AnthropicProvider(args.model or 'claude-sonnet-4-20250514')
    elif provider_name == 'copilot':
        provider = CopilotProvider(args.model or 'claude-sonnet-4.5')
    else:  # ollama
        default_model = 'gpt-oss:120b-cloud' if os.environ.get('OLLAMA_API_KEY') else 'llama3.2:latest'
        provider = OllamaProvider(
            model=args.model or default_model,
            host=args.host if hasattr(args, 'host') else None,
        )

    # Pass through to agent
    return run_agent(
        provider=provider,
        task=task,
        confirm=not args.no_confirm,
        max_turns=args.max_turns,
        resume_data=args.resume if hasattr(args, 'resume') else None,
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


def cmd_gateway(args):
    """Manage multi-channel gateways (Telegram, Discord, Slack, etc.)."""
    from gateway import list_gateways, get_gateway
    from pathlib import Path
    import json

    gateway_dir = Path.home() / '.forestgump' / 'gateways'

    if args.list:
        print(banner('\n📡 Available Gateways'))
        for gw_name in list_gateways():
            print(f'  • {gw_name.upper()}')
        print(f'\n{info("Configure")} forestgump gateway setup [telegram|discord|slack]')
        return 0

    if args.setup:
        gateway_name = args.setup.lower()
        gw_class = get_gateway(gateway_name)

        if not gw_class:
            print(error(f'Unknown gateway: {gateway_name}'))
            return 1

        # TODO: Interactive setup
        print(warning(f'⚠️  Gateway setup not yet implemented for {gateway_name}'))
        print(f'  Future: interactive token/config entry')
        return 0

    if args.status:
        gateway_dir.mkdir(parents=True, exist_ok=True)
        gateway_configs = list(gateway_dir.glob('*.json'))

        if not gateway_configs:
            print(info('  No configured gateways.'))
            return 0

        print(banner('\n📡 Gateway Status'))
        for config_file in gateway_configs:
            gw_name = config_file.stem
            with open(config_file, 'r') as f:
                config = json.load(f)
            enabled = config.get('enabled', False)
            status = '✅' if enabled else '⚠️'
            print(f'  {status} {gw_name.upper()} - {"enabled" if enabled else "disabled"}')
        return 0

    return 0


def cmd_schedule(args):
    """Manage scheduled tasks."""
    from scheduler import Scheduler

    scheduler = Scheduler()

    if args.list:
        print(banner('\n⏰ Scheduled Tasks'))
        tasks = scheduler.list_tasks()

        if not tasks:
            print(info('  No scheduled tasks yet.'))
            return 0

        for task in tasks[:20]:
            status = '✅' if task.enabled else '⚠️'
            print(f'  {status} {task.name}')
            print(f'     Schedule: {task.schedule}')
            print(f'     Provider: {task.provider}')
        return 0

    if args.add:
        parts = args.add.split('|', 2)
        if len(parts) < 3:
            print(error('Usage: forestgump schedule --add "name|schedule|task"'))
            print('Example: forestgump schedule --add "daily-recon|every day at 6am|scan networks"')
            return 1

        name, schedule, task = parts
        task_id = scheduler.add_task(
            name=name.strip(),
            task_description=task.strip(),
            schedule=schedule.strip(),
            provider='claude',
        )

        print(success(f'✓ Task scheduled: {task_id}'))
        print(f'  Name: {name}')
        print(f'  Schedule: {schedule}')
        return 0

    return 0


def cmd_monitor(args):
    """View monitoring and metrics dashboard."""
    from monitor import get_collector

    collector = get_collector()

    if args.dashboard:
        hours = int(args.hours) if args.hours else 24
        print(collector.print_dashboard(hours=hours))
        return 0

    if args.reset:
        # Clear metrics
        from pathlib import Path
        metrics_file = Path(__file__).parent / 'metrics.json'
        if metrics_file.exists():
            metrics_file.unlink()
        print(success('✓ Metrics cleared'))
        return 0

    return 0


def cmd_subagents(args):
    """Manage subagent tasks."""
    from subagent import get_manager

    manager = get_manager()

    if args.status:
        print(manager.print_status())
        return 0

    if args.list:
        print(banner('\n🤖 Subagent Tasks'))
        tasks = manager.list_tasks()

        if not tasks:
            print(info('  No subagent tasks yet.'))
            return 0

        for task in tasks:
            status_icon = {
                'pending': '⏳',
                'running': '🏃',
                'completed': '✅',
                'failed': '❌',
                'timeout': '⏱️',
                'cancelled': '⛔',
            }.get(task.status, '❓')

            print(
                f'  {status_icon} {task.id}: {task.description[:40]}... '
                f'[{task.status}]'
            )
        return 0

    return 0


def cmd_memory_advanced(args):
    """Advanced memory search and statistics."""
    from memory_search import AdvancedMemorySearch

    search = AdvancedMemorySearch()

    if args.stats:
        print(search.print_stats())
        return 0

    if args.high_confidence:
        print(banner('\n🧠 High Confidence Memories'))
        results = search.search_high_confidence(min_confidence=0.8, limit=10)

        for result in results:
            print(f'\n  [{result.type.upper()}] Confidence: {result.confidence:.0%}')
            content = (
                result.content[:70] + '...'
                if len(result.content) > 70
                else result.content
            )
            print(f'    {content}')
        return 0

    if args.unused:
        print(banner('\n🧠 Unused Memories (30+ days)'))
        results = search.search_unused(days_since_use=30, limit=10)

        for result in results:
            print(f'\n  [{result.type.upper()}]')
            content = (
                result.content[:70] + '...'
                if len(result.content) > 70
                else result.content
            )
            print(f'    {content}')
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
    chat_parser.add_argument('--host', help='Ollama host URL (default: http://localhost:11434)')
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

    # gateway
    gateway_parser = subparsers.add_parser('gateway', help='Manage messaging gateways')
    gateway_parser.add_argument('--list', action='store_true', help='List available gateways')
    gateway_parser.add_argument('--setup', help='Setup a gateway (telegram|discord|slack)')
    gateway_parser.add_argument('--status', action='store_true', help='Show gateway status')
    gateway_parser.set_defaults(func=cmd_gateway)

    # schedule
    schedule_parser = subparsers.add_parser('schedule', help='Manage scheduled tasks')
    schedule_parser.add_argument('--list', action='store_true', help='List scheduled tasks')
    schedule_parser.add_argument('--add', help='Add task: "name|schedule|task"')
    schedule_parser.set_defaults(func=cmd_schedule)

    # monitor
    monitor_parser = subparsers.add_parser('monitor', help='View metrics and monitoring')
    monitor_parser.add_argument('--dashboard', action='store_true', help='Show metrics dashboard')
    monitor_parser.add_argument('--hours', default='24', help='Hours of history (default: 24)')
    monitor_parser.add_argument('--reset', action='store_true', help='Clear metrics')
    monitor_parser.set_defaults(func=cmd_monitor)

    # subagents
    subagents_parser = subparsers.add_parser('subagents', help='Manage subagent tasks')
    subagents_parser.add_argument('--status', action='store_true', help='Show subagent status')
    subagents_parser.add_argument('--list', action='store_true', help='List subagent tasks')
    subagents_parser.set_defaults(func=cmd_subagents)

    # memory (advanced search)
    memory_adv_parser = subparsers.add_parser('memory-advanced', help='Advanced memory search')
    memory_adv_parser.add_argument('--stats', action='store_true', help='Show memory statistics')
    memory_adv_parser.add_argument(
        '--high-confidence', action='store_true', help='Show high confidence memories'
    )
    memory_adv_parser.add_argument('--unused', action='store_true', help='Show unused memories')
    memory_adv_parser.set_defaults(func=cmd_memory_advanced)

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
