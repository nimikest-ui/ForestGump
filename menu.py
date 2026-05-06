#!/usr/bin/env python3
"""
Interactive Menu CLI for Bare Metal Agent
- Arrow key navigation and keyboard shortcuts
- Task history with timestamps
- Multiple models and providers
"""

import os
import sys
import subprocess
import json
import termios
import tty
import threading
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from prompt_toolkit import PromptSession, Application
    from prompt_toolkit.layout import Layout, HSplit, Window, WindowAlign
    from prompt_toolkit.layout.controls import BufferControl
    from prompt_toolkit.widgets import TextArea
    from prompt_toolkit.document import Document
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.styles import Style as PTStyle
    from prompt_toolkit.patch_stdout import patch_stdout
    _PT_AVAILABLE = True
except ImportError as e:
    _PT_AVAILABLE = False
    Completer = None  # Define stub so class definition doesn't fail

try:
    from rich.console import Console
    from rich.panel import Panel
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

SCRIPT_DIR   = Path(__file__).parent.resolve()
HISTORY_FILE = SCRIPT_DIR / '.menu_history.json'
CONFIG_FILE  = SCRIPT_DIR / '.agent_config.json'

__version__ = '0.2.0'

# Import theme for CLI commands
try:
    import theme
    from theme import Colors, Symbols, fmt, banner, success, error, warning, info
    _THEME_AVAILABLE = True
except ImportError:
    _THEME_AVAILABLE = False

# Import agent directly (instead of subprocess)
try:
    sys.path.insert(0, str(SCRIPT_DIR))
    from agent import (
        run_agent,
        ClaudeCliProvider,
        OllamaProvider,
        AnthropicProvider,
        CopilotProvider,
    )
    _AGENT_DIRECT = True
except ImportError:
    _AGENT_DIRECT = False


def _load_config():
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def _save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

USE_COLOR = os.environ.get('COLOR') == '1'
NO_COLOR = os.environ.get('NO_COLOR', '1') == '1'
_DIM = '\033[2m' if USE_COLOR else ''
_RST = '\033[0m' if USE_COLOR else ''
_BLD = '\033[1m' if USE_COLOR else ''
_GRN = '\033[32m' if USE_COLOR else ''
_RED = '\033[31m' if USE_COLOR else ''
_GLD = '\033[1;38;2;255;215;0m' if USE_COLOR else ''  # #FFD700 gold (Hermes theme)
_AMB = '\033[38;2;255;191;0m' if USE_COLOR else ''   # #FFBF00 amber
_BRZ = '\033[38;2;205;127;50m' if USE_COLOR else ''  # #CD7F32 bronze


def _cols():
    try:
        return os.get_terminal_size().columns
    except Exception:
        return 80


def _get_local_ollama_models():
    """Query Ollama API for installed local models. Returns set of model names."""
    try:
        import urllib.request
        with urllib.request.urlopen('http://localhost:11434/api/tags', timeout=2) as r:
            data = json.loads(r.read())
            # Only real local models have size > 1MB; tiny ones are cloud stubs
            return {
                m['name']
                for m in data.get('models', [])
                if m.get('size', 0) > 1_000_000
            }
    except Exception:
        return set()


_BLU = '\033[38;5;33m' if USE_COLOR else ''

SLASH_COMMANDS = [
    ('/chat',              'start chat session'),
    ('/skills',            'browse learned skills'),
    ('/memory',            'search/list memory'),
    ('/sessions',          'list recent sessions'),
    ('/monitor',           'show metrics dashboard'),
    ('/subagents',         'show subagent status'),
    ('/memory-advanced',   'advanced memory search'),
    ('/provider',          'switch AI provider — saved'),
    ('/model',             'switch AI model — saved'),
    ('/resume',            'resume previous session'),
]
_MAX_DROP  = len(SLASH_COMMANDS)
_CMD_WIDTH = 20  # fixed left column width for slash command names


def _hr():
    print(f'{_DIM}{"─" * _cols()}{_RST}')


# ─── Hermes-style branding and UI ───

FOREST_GUMP_LOGO = """[bold #FFD700]███████╗ ██████╗ ██████╗ ███████╗███████╗████████╗[/]
[#FFBF00]██╔════╝██╔═══██╗██╔══██╗██╔════╝██╔════╝╚══██╔══╝[/]
[#FFBF00]█████╗  ██║   ██║██████╔╝█████╗  ███████╗   ██║[/]
[#CD7F32]██╔══╝  ██║   ██║██╔══██╗██╔══╝  ╚════██║   ██║[/]
[#CD7F32]██║     ╚██████╔╝██║  ██║███████╗███████║   ██║[/]
[#B8860B]╚═╝      ╚═════╝ ╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝[/]"""


if _PT_AVAILABLE and Completer:
    class SlashCompleter(Completer):
        """prompt_toolkit Completer for slash commands."""
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if text.startswith('/'):
                for cmd, desc in SLASH_COMMANDS:
                    if cmd.startswith(text):
                        yield Completion(cmd[len(text):], display=cmd, display_meta=desc)
else:
    class SlashCompleter:
        """Stub completer when prompt_toolkit unavailable."""
        def get_completions(self, document, complete_event):
            return []


def _print_banner(provider, model, history):
    """Print a Hermes-style Rich banner at startup."""
    if not _RICH_AVAILABLE:
        print(f'\n {_GLD}⚕{_RST} {_BLD}Forest Gump{_RST}\n')
        return

    console = Console()
    last = f"Last: {history[-1]['task'][:40]}…" if history else "No history"
    body = (
        f"{FOREST_GUMP_LOGO}\n\n"
        f"[dim]Provider[/dim]  [bold #FFBF00]{provider}[/bold #FFBF00]  [dim]{model}[/dim]\n"
        f"[dim]{last}[/dim]"
    )
    console.print(Panel(
        body,
        title="[bold #FFD700]⚕ Bare Metal Agent[/bold #FFD700]",
        border_style="#CD7F32",
        padding=(0, 2),
    ))


def _readline_slash(timeout_seconds=3, on_timeout=None, history=None):
    """Custom input with timeout: typing '/' shows autocomplete dropdown (unless COLOR=1).

    Args:
        timeout_seconds: Timeout in seconds before returning None (triggers redraw)
        on_timeout: Optional callback function to call when timeout occurs
        history: Optional list of previous commands for history navigation
    """
    import re as _re

    if not USE_COLOR:
        # For non-color mode, use select with timeout
        import select
        try:
            rdy, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
            if rdy:
                return input()
            else:
                if on_timeout:
                    on_timeout()
                return None
        except Exception:
            return input()

    if history is None:
        history = []

    buf          = []
    drop_sel     = -1
    prev_lines   = 0
    cursor_pos   = 0
    hist_idx     = len(history)  # Start at end of history (new input)

    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setraw(fd)

    import select as _select

    def _visible(s):
        return len(_re.sub(r'\033\[[^m]*m', '', s))

    def _render():
        nonlocal prev_lines
        text = ''.join(buf)
        # Dropdown only when slash is the very first character
        is_slash = text.startswith('/') and (len(text) == 1 or buf[0] == '/')
        matches  = [(c, d) for c, d in SLASH_COMMANDS if c.startswith(text)] if is_slash else []

        colored = f'{_BLU}{_BLD}{text}{_RST}' if is_slash else text

        # Draw input line
        sys.stdout.write(f'\r\033[K {_GLD}>{_RST} {colored}')

        # Draw / clear dropdown lines below
        n = max(len(matches), prev_lines)
        for i in range(n):
            if i < len(matches):
                cmd, desc = matches[i]
                if i == drop_sel:
                    row = f'  {_GLD}❯{_RST} {_BLU}{_BLD}{cmd:<{_CMD_WIDTH}}{_RST}  {_DIM}{desc}{_RST}'
                else:
                    row = f'    {_BLU}{cmd:<{_CMD_WIDTH}}{_RST}  {_DIM}{desc}{_RST}'
            else:
                row = ''
            sys.stdout.write(f'\n\r\033[K{row}')

        prev_lines = len(matches)

        # Move cursor back to input line, correct column
        if n:
            sys.stdout.write(f'\033[{n}A')
        col = 3 + _visible(colored)   # " > " = 3 chars
        sys.stdout.write(f'\r\033[{col}C')
        sys.stdout.flush()

    def _clear_drop():
        sys.stdout.write('\033[s')
        for _ in range(_MAX_DROP):
            sys.stdout.write('\n\033[K')
        sys.stdout.write('\033[u')
        sys.stdout.flush()

    try:
        # Reserve space for dropdown
        sys.stdout.write(('\n\r') * (_MAX_DROP + 1))
        sys.stdout.write(f'\033[{_MAX_DROP + 1}A')
        sys.stdout.flush()
        _render()

        import fcntl as _fcntl
        flags = _fcntl.fcntl(fd, _fcntl.F_GETFL)

        while True:
            # Use select with timeout to allow periodic redraws
            rdy, _, _ = _select.select([fd], [], [], timeout_seconds)
            if not rdy:
                # Timeout occurred, call callback if provided
                _clear_drop()
                if on_timeout:
                    on_timeout()
                return None

            ch = sys.stdin.read(1)

            if ch in ('\r', '\n'):
                text     = ''.join(buf)
                is_slash = text.startswith('/')
                matches  = [(c, d) for c, d in SLASH_COMMANDS if c.startswith(text)] if is_slash else []
                if drop_sel >= 0 and drop_sel < len(matches):
                    buf[:] = list(matches[drop_sel][0])

                result = ''.join(buf)
                # Add to history if not empty
                if result and (not history or history[-1] != result):
                    history.append(result)

                _clear_drop()
                sys.stdout.write('\n')
                sys.stdout.flush()
                return result

            elif ch in ('\x7f', '\x08'):  # backspace
                if buf:
                    buf.pop()
                drop_sel = -1
                _render()

            elif ch == '\x03':  # Ctrl-C
                _clear_drop()
                raise KeyboardInterrupt

            elif ch == '\x1b':
                nxt = sys.stdin.read(1)
                if nxt == '[':
                    arrow    = sys.stdin.read(1)
                    text     = ''.join(buf)
                    is_slash = text.startswith('/')
                    matches  = [(c, d) for c, d in SLASH_COMMANDS if c.startswith(text)] if is_slash else []

                    if arrow == 'A':  # Up arrow
                        if matches and drop_sel >= 0:  # In dropdown mode
                            drop_sel = max(-1, drop_sel - 1)
                            _render()
                        else:  # History navigation
                            if hist_idx > 0:
                                hist_idx -= 1
                                buf[:] = list(history[hist_idx] if hist_idx < len(history) else '')
                                cursor_pos = len(buf)
                                _render()
                    elif arrow == 'B':  # Down arrow
                        if matches and drop_sel >= 0:  # In dropdown mode
                            drop_sel = min(len(matches) - 1, drop_sel + 1)
                            _render()
                        else:  # History navigation
                            if hist_idx < len(history):
                                hist_idx += 1
                                buf[:] = list(history[hist_idx] if hist_idx < len(history) else '')
                                cursor_pos = len(buf)
                                _render()
                    elif arrow == 'H':  # Home key
                        cursor_pos = 0
                        _render()
                    elif arrow == 'F':  # End key
                        cursor_pos = len(buf)
                        _render()

            elif ch == '\t':  # Tab: complete first match
                text     = ''.join(buf)
                is_slash = text.startswith('/')
                matches  = [(c, d) for c, d in SLASH_COMMANDS if c.startswith(text)] if is_slash else []
                if matches:
                    buf[:] = list(matches[0][0])
                    drop_sel = -1
                    _render()

            elif ord(ch) >= 32:
                buf.append(ch)
                drop_sel = -1
                _render()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _rel_time(ts_str):
    """'20260423_103533' or ISO string → '2h ago'"""
    try:
        if 'T' in ts_str or '-' in ts_str:
            dt = datetime.fromisoformat(ts_str)
        else:
            dt = datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
        secs = (datetime.now() - dt).total_seconds()
        if secs < 60:       return f'{int(secs)}s ago'
        if secs < 3600:     return f'{int(secs//60)}m ago'
        if secs < 86400:    return f'{int(secs//3600)}h ago'
        return f'{int(secs//86400)}d ago'
    except Exception:
        return '?'


def _load_sessions(sessions_dir, limit=20):
    """Return list of session dicts sorted newest first."""
    sessions = []
    for f in sorted(Path(sessions_dir).glob('*.json'), reverse=True)[:limit]:
        try:
            d = json.loads(f.read_text())
            sessions.append({
                'file':     str(f),
                'ts':       d.get('timestamp', f.stem),
                'provider': d.get('provider', '?'),
                'model':    d.get('model', ''),
                'turns':    d.get('turns', 0),
                'task':     d.get('task', ''),
            })
        except Exception:
            pass
    return sessions


# ─── CLI Command Functions (from cli.py) ───

def cmd_chat(args):
    """Start an interactive pentesting session."""
    # Clear screen before starting
    os.system('clear' if os.name != 'nt' else 'cls')

    task = args.task if hasattr(args, 'task') and args.task else ' '.join(args.task_args) if hasattr(args, 'task_args') else None
    if not task:
        if _THEME_AVAILABLE:
            print(error(f'{Symbols.CROSS} No task specified'))
        else:
            print('❌ No task specified')
        print(f'Usage: forestgump chat "<your pentesting task>"')
        return 1

    # Instantiate provider object (matching agent.py's main() logic)
    provider_name = args.provider or 'claude'

    if provider_name == 'claude':
        provider = ClaudeCliProvider(args.model or 'haiku')
    elif provider_name == 'anthropic':
        if not os.environ.get('ANTHROPIC_API_KEY'):
            if _THEME_AVAILABLE:
                print(error(f'{Symbols.CROSS} Set ANTHROPIC_API_KEY environment variable'))
            else:
                print('❌ Set ANTHROPIC_API_KEY environment variable')
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
        if _THEME_AVAILABLE:
            print(banner('\n⚙️  Available LLM Providers'))
            for provider, info in providers.items():
                print(f'\n{fmt(provider.upper(), Colors.GOLD, bold=True)}')
                print(f'  {info["name"]}')
                print(f'  Requires: {info["requires"]}')
                print(f'  Models: {", ".join(info["models"][:3])}...')
            print(f'\n{banner("Usage:")} forestgump chat --provider claude "your task"')
            print(f'         forestgump chat --provider ollama --model llama3.2:latest "your task"')
        else:
            for provider, info in providers.items():
                print(f'\n{provider.upper()}')
                print(f'  {info["name"]}')
                print(f'  Requires: {info["requires"]}')
        return 0

    if args.set:
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

        if _THEME_AVAILABLE:
            print(success(f'{Symbols.CHECK} Default provider set to {provider}'))
            if model:
                print(success(f'{Symbols.CHECK} Default model set to {model}'))
        else:
            print(f'✓ Default provider set to {provider}')
            if model:
                print(f'✓ Default model set to {model}')
        return 0

    return 0


def cmd_skills(args):
    """Browse and manage learned attack patterns."""
    from skill_manager import list_all_skills, search_skills, get_skill

    if args.search:
        if _THEME_AVAILABLE:
            print(banner(f'\n🎯 Searching for "{args.search}"'))
        else:
            print(f'\n🎯 Searching for "{args.search}"')
        skills = search_skills(args.search, limit=10)

        if not skills:
            if _THEME_AVAILABLE:
                print(warning(f'  No skills found for "{args.search}"'))
            else:
                print(f'  No skills found for "{args.search}"')
            return 0

        for skill in skills:
            eff = (skill['success_rate'] * max(1, skill['use_count']) * 100) - (skill['best_session_turns'] or 999)
            if _THEME_AVAILABLE:
                print(f'\n  {fmt(skill["name"], Colors.GOLD, bold=True)}')
            else:
                print(f'\n  {skill["name"]}')
            print(f'    Success rate: {skill["success_rate"]:.0%} | Used: {skill["use_count"]}x | Efficiency: {eff:.0f}')
            if skill['problem']:
                print(f'    Problem: {skill["problem"]}')
            if skill['template']:
                print(f'    Template: {skill["template"][:60]}...' if len(skill['template']) > 60 else f'    Template: {skill["template"]}')
        return 0

    if args.list:
        if _THEME_AVAILABLE:
            print(banner('\n📚 All Learned Skills'))
        else:
            print('\n📚 All Learned Skills')
        skills = list_all_skills()
        if not skills:
            print('  No skills yet. Run pentesting tasks to learn them!')
            return 0

        for skill in skills[:20]:
            print(f'  • {skill["name"]} ({skill["success_rate"]:.0%})')
        if len(skills) > 20:
            print(f'  ... and {len(skills) - 20} more')
        return 0

    return 0


def cmd_memory(args):
    """View and manage persistent memory."""
    from memory_manager import get_all_by_type, search_memory, get_memory_context

    if args.search:
        if _THEME_AVAILABLE:
            print(banner(f'\n🧠 Searching memory for "{args.search}"'))
        else:
            print(f'\n🧠 Searching memory for "{args.search}"')
        results = search_memory(args.search, limit=10)

        if not results:
            if _THEME_AVAILABLE:
                print(warning(f'  No memories found for "{args.search}"'))
            else:
                print(f'  No memories found for "{args.search}"')
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
                if _THEME_AVAILABLE:
                    print(f'\n{banner(type_.upper())}')
                else:
                    print(f'\n{type_.upper()}')
                for mem in mems[:5]:
                    print(f'  • {mem["content"][:70]}...' if len(mem['content']) > 70 else f'  • {mem["content"]}')

        return 0

    if args.summary:
        context = get_memory_context()
        if context:
            print(context)
        else:
            if _THEME_AVAILABLE:
                print(info('  No memories yet.'))
            else:
                print('  No memories yet.')
        return 0

    return 0


def cmd_sessions(args):
    """Manage session history."""
    sessions_dir = Path(__file__).parent / 'sessions'
    if not sessions_dir.exists():
        if _THEME_AVAILABLE:
            print(warning('  No sessions yet.'))
        else:
            print('  No sessions yet.')
        return 0

    sessions = sorted(sessions_dir.glob('*.json'), reverse=True)[:20]

    if args.list:
        if _THEME_AVAILABLE:
            print(banner('\n📋 Recent Sessions'))
        else:
            print('\n📋 Recent Sessions')
        for session_file in sessions:
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)
                task = data.get('task', 'unknown')[:40]
                timestamp = session_file.stem
                print(f'  {timestamp}  {task}')
            except:
                pass
        return 0

    if args.resume:
        session_file = sessions_dir / f'{args.resume}.json'
        if not session_file.exists():
            if _THEME_AVAILABLE:
                print(error(f'{Symbols.CROSS} Session not found: {args.resume}'))
            else:
                print(f'❌ Session not found: {args.resume}')
            return 1

        if _THEME_AVAILABLE:
            print(success(f'{Symbols.CHECK} Resuming session {args.resume}'))
        else:
            print(f'✓ Resuming session {args.resume}')
        return run_agent(resume_session=str(session_file))

    return 0


def cmd_config(args):
    """Configure ForestGump settings."""
    config_dir = Path.home() / '.forestgump'
    config_file = config_dir / 'config.json'

    if args.show:
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = json.load(f)
            if _THEME_AVAILABLE:
                print(banner('\n⚙️  Current Configuration'))
            else:
                print('\n⚙️  Current Configuration')
            for key, val in config.items():
                print(f'  {key}: {val}')
        else:
            if _THEME_AVAILABLE:
                print(info('  No config file yet. Run commands to create default config.'))
            else:
                print('  No config file yet. Run commands to create default config.')
        return 0

    return 0


def cmd_gateway(args):
    """Manage multi-channel gateways (Telegram, Discord, Slack, etc.)."""
    from gateway import list_gateways, get_gateway

    gateway_dir = Path.home() / '.forestgump' / 'gateways'

    if args.list:
        if _THEME_AVAILABLE:
            print(banner('\n📡 Available Gateways'))
        else:
            print('\n📡 Available Gateways')
        for gw_name in list_gateways():
            print(f'  • {gw_name.upper()}')
        if _THEME_AVAILABLE:
            print(f'\n{info("Configure")} forestgump gateway setup [telegram|discord|slack]')
        else:
            print(f'\nConfigure: forestgump gateway setup [telegram|discord|slack]')
        return 0

    if args.setup:
        gateway_name = args.setup.lower()
        gw_class = get_gateway(gateway_name)

        if not gw_class:
            if _THEME_AVAILABLE:
                print(error(f'Unknown gateway: {gateway_name}'))
            else:
                print(f'❌ Unknown gateway: {gateway_name}')
            return 1

        if _THEME_AVAILABLE:
            print(warning(f'⚠️  Gateway setup not yet implemented for {gateway_name}'))
        else:
            print(f'⚠️  Gateway setup not yet implemented for {gateway_name}')
        print(f'  Future: interactive token/config entry')
        return 0

    if args.status:
        gateway_dir.mkdir(parents=True, exist_ok=True)
        gateway_configs = list(gateway_dir.glob('*.json'))

        if not gateway_configs:
            if _THEME_AVAILABLE:
                print(info('  No configured gateways.'))
            else:
                print('  No configured gateways.')
            return 0

        if _THEME_AVAILABLE:
            print(banner('\n📡 Gateway Status'))
        else:
            print('\n📡 Gateway Status')
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
        if _THEME_AVAILABLE:
            print(banner('\n⏰ Scheduled Tasks'))
        else:
            print('\n⏰ Scheduled Tasks')
        tasks = scheduler.list_tasks()

        if not tasks:
            if _THEME_AVAILABLE:
                print(info('  No scheduled tasks yet.'))
            else:
                print('  No scheduled tasks yet.')
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
            if _THEME_AVAILABLE:
                print(error('Usage: forestgump schedule --add "name|schedule|task"'))
            else:
                print('Usage: forestgump schedule --add "name|schedule|task"')
            print('Example: forestgump schedule --add "daily-recon|every day at 6am|scan networks"')
            return 1

        name, schedule, task = parts
        task_id = scheduler.add_task(
            name=name.strip(),
            task_description=task.strip(),
            schedule=schedule.strip(),
            provider='claude',
        )

        if _THEME_AVAILABLE:
            print(success(f'✓ Task scheduled: {task_id}'))
        else:
            print(f'✓ Task scheduled: {task_id}')
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
        metrics_file = Path(__file__).parent / 'metrics.json'
        if metrics_file.exists():
            metrics_file.unlink()
        if _THEME_AVAILABLE:
            print(success('✓ Metrics cleared'))
        else:
            print('✓ Metrics cleared')
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
        if _THEME_AVAILABLE:
            print(banner('\n🤖 Subagent Tasks'))
        else:
            print('\n🤖 Subagent Tasks')
        tasks = manager.list_tasks()

        if not tasks:
            if _THEME_AVAILABLE:
                print(info('  No subagent tasks yet.'))
            else:
                print('  No subagent tasks yet.')
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
        if _THEME_AVAILABLE:
            print(banner('\n🧠 High Confidence Memories'))
        else:
            print('\n🧠 High Confidence Memories')
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
        if _THEME_AVAILABLE:
            print(banner('\n🧠 Unused Memories (30+ days)'))
        else:
            print('\n🧠 Unused Memories (30+ days)')
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


class MenuSystem:
    def __init__(self):
        self._local_models = _get_local_ollama_models()
        self.providers = {
            'ollama': {
                'label': 'Ollama',
                'desc': 'Fast local/cloud',
                'models': {
                    'glm-5.1-cloud': 'GLM 5.1 · Agentic',
                    'llama3.2:latest': 'Llama 3.2 · Fast',
                    'mistral:latest': 'Mistral 7B',
                }
            },
            'claude': {
                'label': 'Claude CLI',
                'desc': 'Pro · OAuth',
                'models': {
                    'sonnet': 'Claude Sonnet',
                    'haiku': 'Claude Haiku · Fast',
                }
            },
            'anthropic': {
                'label': 'Anthropic API',
                'desc': 'ANTHROPIC_API_KEY',
                'models': {
                    'claude-opus-4-7': 'Claude Opus 4.7',
                    'claude-haiku-4-5-20251001': 'Claude Haiku · Fast',
                }
            },
            'copilot': {
                'label': 'GitHub Copilot',
                'desc': 'gh auth',
                'models': {
                    'claude-haiku-4.5': 'Haiku · Fast',
                    'claude-sonnet-4.6': 'Sonnet 4.6',
                }
            }
        }
        self.history = self._load_history()

    def _load_history(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE) as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_history(self, provider, model, task):
        self.history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': provider,
            'model': model,
            'task': task,
        })
        if len(self.history) > 20:
            self.history = self.history[-20:]
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception:
            pass

    def clear_screen(self):
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()

    def display_header(self):
        if NO_COLOR:
            print('ForestGump\n')
        else:
            print(f'\n {_GLD}●{_RST} {_BLD}Agent{_RST}\n')

    def getch_unix(self):
        if os.name != 'posix':
            return sys.stdin.read(1)
        try:
            tty_fd = os.open('/dev/tty', os.O_RDWR | os.O_NOCTTY)
        except OSError:
            return sys.stdin.read(1)
        old = termios.tcgetattr(tty_fd)
        try:
            tty.setraw(tty_fd)
            ch = os.read(tty_fd, 1).decode('utf-8', errors='replace')
        finally:
            termios.tcsetattr(tty_fd, termios.TCSADRAIN, old)
            os.close(tty_fd)
        return ch

    def show_menu(self, title, options, descs=None):
        selected   = 0
        scroll_off = 0
        while True:
            self.clear_screen()
            self.display_header()
            print(f' {_DIM}{title}{_RST}\n')

            # Viewport: header(3) + title(2) + history(5) + footer(3) = ~13 overhead
            try:
                rows = os.get_terminal_size().lines
            except Exception:
                rows = 24
            has_history = bool(self.history and 'Provider' in title)
            overhead  = 13 if has_history else 8
            visible   = max(3, rows - overhead)

            # Keep selected in viewport
            if selected < scroll_off:
                scroll_off = selected
            elif selected >= scroll_off + visible:
                scroll_off = selected - visible + 1

            if scroll_off > 0:
                print(f'  {_DIM}↑ {scroll_off} more{_RST}')

            for i in range(scroll_off, min(scroll_off + visible, len(options))):
                raw_desc   = descs[i] if descs and i < len(descs) else ''
                installed  = raw_desc.startswith('\x00LOCAL\x00')
                clean_desc = raw_desc[7:] if installed else raw_desc
                if i == selected:
                    marker = f'{_GLD}❯{_RST}'
                    label  = f'{_BLD}{options[i]}{_RST}'
                else:
                    marker = ' '
                    label  = f'{_DIM}{options[i]}{_RST}'
                if installed:
                    desc = f'  {_GLD}●{_RST} {_DIM}{clean_desc}{_RST}'
                else:
                    desc = f'  {_DIM}{clean_desc}{_RST}' if clean_desc else ''
                print(f'  {marker} {label}{desc}')

            below = len(options) - scroll_off - visible
            if below > 0:
                print(f'  {_DIM}↓ {below} more{_RST}')

            if has_history:
                print(f'\n {_DIM}Recent{_RST}')
                for entry in self.history[-3:]:
                    dt = datetime.fromisoformat(entry['timestamp']).strftime('%H:%M')
                    print(f'  {_DIM}↳ [{dt}] {entry["provider"]}  {entry["task"][:50]}{_RST}')

            print()
            _hr()
            nav_text = '↑↓ ↵' if NO_COLOR else f' {_DIM}↑↓ navigate   ↵ select   h history   q quit{_RST}'
            print(f' {nav_text}')

            try:
                ch = self.getch_unix()
                if ch == '\x1b':
                    self.getch_unix()  # [
                    ch = self.getch_unix()
                    if ch == 'A':
                        selected = (selected - 1) % len(options)
                    elif ch == 'B':
                        selected = (selected + 1) % len(options)
                elif ch in ('\r', '\n'):
                    return selected
                elif ch.lower() == 'q':
                    print(f'\n {_DIM}quit{_RST}')
                    sys.exit(0)
                elif ch.lower() == 'h':
                    self._show_history()
                elif ch.isdigit():
                    idx = int(ch) - 1
                    if 0 <= idx < len(options):
                        return idx
            except Exception:
                return self._simple_menu(title, options, descs)

    def _show_history(self):
        self.clear_screen()
        self.display_header()
        print(f' {_DIM}History{_RST}\n')
        if not self.history:
            print(f'  {_DIM}No history yet.{_RST}')
        else:
            for entry in reversed(self.history[-10:]):
                dt = datetime.fromisoformat(entry['timestamp']).strftime('%H:%M')
                print(f'  {_DIM}[{dt}]{_RST}  {_DIM}{entry["provider"]:<12}{_RST}{entry["task"][:52]}')
        print()
        _hr()
        print(f' {_DIM}↵ back{_RST}')
        try:
            self.getch_unix()
        except Exception:
            pass

    def _simple_menu(self, title, options, descs=None):
        while True:
            self.clear_screen()
            self.display_header()
            print(f' {_DIM}{title}{_RST}\n')
            for i, option in enumerate(options, 1):
                desc = f'  {_DIM}{descs[i-1]}{_RST}' if descs else ''
                print(f'  [{i}] {option}{desc}')
            print()
            _hr()
            print(f' {_GLD}>{_RST} ', end='', flush=True)
            choice = input().strip()
            if choice.lower() == 'q':
                sys.exit(0)
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return idx

    def _pick_session(self, follow_up_task=''):
        """Interactive session picker. Returns selected session data (doesn't launch subprocess)."""
        sessions = _load_sessions(SCRIPT_DIR / 'sessions')
        if not sessions:
            self.clear_screen()
            self.display_header()
            print(f'  {_DIM}No sessions found.{_RST}')
            print()
            _hr()
            print(f'  {_DIM}↵ back{_RST}')
            try:
                self.getch_unix()
            except Exception:
                pass
            return None

        selected   = 0
        scroll_off = 0
        while True:
            self.clear_screen()
            self.display_header()
            print(f'  {_DIM}Resume session{_RST}\\n')

            try:
                rows = os.get_terminal_size().lines
                cols = os.get_terminal_size().columns
            except Exception:
                rows = 24; cols = 80
            # overhead: header(3) + title(2) + up-ind(1) + dn-ind(1) + blank(1) + hr(1) + nav(1) + follow_up(0/1) + margin(2)
            overhead = 13 + (1 if follow_up_task else 0)
            visible  = max(3, rows - overhead)

            if selected < scroll_off:
                scroll_off = selected
            elif selected >= scroll_off + visible:
                scroll_off = selected - visible + 1

            if scroll_off > 0:
                print(f'  {_DIM}↑ {scroll_off} more{_RST}')

            # fixed prefix width: "  ❯ " + age(8) + "  " + provider(14) + "  " + turns(4) + "  " = 34
            task_max = max(10, cols - 38)
            for i in range(scroll_off, min(scroll_off + visible, len(sessions))):
                s        = sessions[i]
                age      = _rel_time(s['ts'])
                provider = s['provider'].split('/')[0][:13]
                turns    = f"{s['turns']}t"
                task_pre = s['task'][:task_max] + ('…' if len(s['task']) > task_max else '')
                line = f'{age:<8}  {provider:<14}  {turns:<4}  {task_pre}'
                if i == selected:
                    print(f'  {_GLD}❯{_RST} {_BLD}{line}{_RST}')
                else:
                    print(f'    {_DIM}{line}{_RST}')

            below = len(sessions) - scroll_off - visible
            if below > 0:
                print(f'  {_DIM}↓ {below} more{_RST}')

            print()
            _hr()
            if follow_up_task and not NO_COLOR:
                print(f'  {_DIM}follow-up: {follow_up_task[:60]}{_RST}')
            nav_text = '↑↓ ↵' if NO_COLOR else f'  {_DIM}↑↓ navigate  ↵ resume  q cancel{_RST}'
            print(nav_text)

            try:
                ch = self.getch_unix()
                if ch == '\\x1b':
                    self.getch_unix()
                    ch = self.getch_unix()
                    if ch == 'A':
                        selected = (selected - 1) % len(sessions)
                    elif ch == 'B':
                        selected = (selected + 1) % len(sessions)
                elif ch in ('\\r', '\\n'):
                    s = sessions[selected]
                    # Load session file and return resume_data (instead of subprocess call)
                    try:
                        resume_data = json.loads(Path(s['file']).read_text())
                        return {'resume_data': resume_data, 'follow_up': follow_up_task}
                    except Exception as e:
                        print(f'  {_RED}✗ Failed to load session: {e}{_RST}')
                        return None
                elif ch.lower() == 'q':
                    return None
                elif ch.isdigit():
                    idx = int(ch) - 1
                    if 0 <= idx < len(sessions):
                        s = sessions[idx]
                        # Load session file and return resume_data (instead of subprocess call)
                        try:
                            resume_data = json.loads(Path(s['file']).read_text())
                            return {'resume_data': resume_data, 'follow_up': follow_up_task}
                        except Exception as e:
                            print(f'  {_RED}✗ Failed to load session: {e}{_RST}')
                            return None
            except Exception:
                return

    def _pick_model(self, provider):
        """Show model selection menu for given provider. Returns model name."""
        models_dict = self.providers[provider]['models']
        model_names = list(models_dict.keys())
        model_descs = list(models_dict.values())

        if provider == 'ollama' and self._local_models:
            pairs  = list(zip(model_names, model_descs))
            local  = [(n, f'\x00LOCAL\x00{d}') for n, d in pairs if n in self._local_models]
            remote = [(n, d)                   for n, d in pairs if n not in self._local_models]
            pairs  = local + remote
            model_names = [n for n, d in pairs]
            model_descs = [d for n, d in pairs]

        model_idx = self.show_menu('Select Model', model_names, model_descs)
        return model_names[model_idx]

    def _direct_run(self, provider, model, task):
        try:
            if provider not in self.providers:
                print(f' {_RED}✗{_RST} Unknown provider: {provider}')
                sys.exit(1)
            models_dict = self.providers[provider]['models']
            if model not in models_dict:
                print(f' {_RED}✗{_RST} Unknown model for {provider}: {model}')
                print(f' {_DIM}Available: {", ".join(list(models_dict.keys())[:5])}…{_RST}')
                sys.exit(1)
            self._save_history(provider, model, task)
            self._execute_agent(provider, model, task)
        except Exception as e:
            print(f' {_RED}✗{_RST} {e}')
            sys.exit(1)

    def _execute_agent(self, provider_name, model, task, steer_queue=None, stop_event=None, resume_data=None):
        """Execute agent directly (no subprocess) or via subprocess if import fails."""
        if _AGENT_DIRECT:
            try:
                # Build provider object
                if provider_name == 'claude':
                    provider = ClaudeCliProvider(model or 'haiku')
                elif provider_name == 'anthropic':
                    if not os.environ.get('ANTHROPIC_API_KEY'):
                        print(f'{_RED}✗{_RST} Set ANTHROPIC_API_KEY environment variable.')
                        return
                    provider = AnthropicProvider(model or 'claude-sonnet-4-20250514')
                elif provider_name == 'copilot':
                    provider = CopilotProvider(model or 'claude-sonnet-4.5')
                else:  # ollama
                    default_model = 'gpt-oss:120b-cloud' if os.environ.get('OLLAMA_API_KEY') else 'llama3.2:latest'
                    provider = OllamaProvider(model=model or default_model)

                # Run agent directly in same process
                run_agent(provider, task, max_turns=50, confirm=False, resume_data=resume_data, tui_mode=True, stop_event=stop_event)
                # Don't exit — return to menu for next task
                return
            except Exception as e:
                print(f'{_RED}✗{_RST} Agent error: {e}')
                return

        # Fallback to subprocess if agent not importable
        cmd = ['python3', 'agent.py', '--provider', provider_name, '--model', model, task]
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, env=os.environ.copy())
        sys.exit(result.returncode)

    def run(self, initial_task=None):
        try:
            # Load saved provider/model; fall back to defaults — no startup menus
            cfg      = _load_config()
            provider = cfg.get('provider')
            model    = cfg.get('model')

            if provider not in self.providers:
                provider = list(self.providers.keys())[0]  # default: ollama
            if model not in self.providers[provider]['models']:
                model = list(self.providers[provider]['models'].keys())[0]

            # Use main TUI with slash command support
            self._run_with_fixed_input(provider, model, initial_task=initial_task)

        except KeyboardInterrupt:
            print(f'\n {_DIM}quit{_RST}')
            sys.exit(1)
        except Exception as e:
            print(f'\n✗ Error: {e}', file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def _run_with_fixed_input(self, provider, model, initial_task=None):
        """Hermes-style fixed input TUI with slash picker, steering, and safe interrupts."""
        import io
        import re
        import time
        import select
        import fcntl
        import threading as _threading

        _real_stdout = sys.stdout
        _real_stdin = sys.stdin

        try:
            rows, cols = os.get_terminal_size()
        except OSError:
            rows, cols = 24, 80

        output_lines = []
        output_lock = _threading.Lock()
        import queue
        steer_queue = queue.Queue()

        agent_running = False
        agent_stop_event = None
        exit_requested = False
        current_input = ''
        input_history = []
        history_index = -1
        current_task = ''
        current_turn = 0
        pending_menu = None
        session_start = time.time()

        SLASH_COMMANDS_LOCAL = [
            ('/chat',             'Start chat session with custom task'),
            ('/skills',           'Browse or search learned skills'),
            ('/memory',           'Search or list persistent memory'),
            ('/sessions',         'List recent sessions'),
            ('/monitor',          'Show metrics dashboard'),
            ('/subagents',        'Show subagent task status'),
            ('/memory-advanced',  'Advanced memory search & stats'),
            ('/provider',         'Switch AI provider'),
            ('/model',            'Switch AI model'),
            ('/resume',           'Resume a previous session'),
            ('/new',              'Start a new session (fresh context)'),
            ('/reset',            'Start a new session (fresh context)'),
            ('/clear',            'Clear screen and keep current session'),
            ('/history',          'Show conversation history'),
            ('/save',             'Save current session state'),
            ('/retry',            'Retry the last user message'),
            ('/undo',             'Remove last exchange from local buffer'),
            ('/title',            'Set title for current session'),
            ('/branch',           'Branch current session (snapshot)'),
            ('/fork',             'Branch current session (snapshot)'),
            ('/compress',         'Compress conversation context'),
            ('/rollback',         'Restore previous checkpoint'),
            ('/help',             'Show all slash commands'),
            ('/status',           'Show provider/session status'),
            ('/quit',             'Exit ForestGump'),
        ]
        slash_picker_active = False
        slash_picker_idx = 0
        slash_filter = ''
        slash_list_count = 0

        class _RealtimeCapture(io.StringIO):
            def __init__(self, cb):
                super().__init__()
                self._cb = cb
            def write(self, s):
                if s:
                    self._cb(s)
                return super().write(s)

        def add_output(text):
            if not text:
                return
            clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07', '', text)
            with output_lock:
                for line in clean.rstrip('\n').split('\n'):
                    if '\r' in line:
                        parts = line.split('\r')
                        line = next((x.strip() for x in reversed(parts) if x.strip()), '')
                    if line.strip():
                        output_lines.append(line)
                output_lines[:] = output_lines[-500:]

        def get_display_lines():
            try:
                rows2, _ = os.get_terminal_size()
            except OSError:
                rows2 = 24
            max_lines = rows2 - 5
            with output_lock:
                return output_lines[-max(1, max_lines):]

        def get_status_lines():
            elapsed = time.time() - session_start
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            time_str = f'{minutes}m{seconds:02d}s' if minutes > 0 else f'{seconds}s'
            state = 'running' if agent_running else 'idle'
            model_display = model[:20] if len(model) > 20 else model
            try:
                from agent import _bar_state as _agent_bar
                live_turn = _agent_bar.get('turn', 0)
                live_action = _agent_bar.get('action', '')
                if live_turn:
                    turn_str = f'turn {live_turn}'
                    if live_action:
                        turn_str += f' · {live_action[:20]}'
                else:
                    turn_str = 'turn 0'
            except Exception:
                turn_str = f'turn {current_turn}' if current_turn > 0 else 'turn 0'

            if current_task:
                try:
                    cols3 = os.get_terminal_size().columns
                except OSError:
                    cols3 = 80
                max_task = max(10, cols3 - 4)
                task_display = current_task[:max_task] + ('…' if len(current_task) > max_task else '')
                mission = f' ◈ {task_display}'
            else:
                mission = ' ◈ ForestGump — ready'
            stats = f' ⚕ {model_display} │ 100K/400K │ [██░░░░░░░░] 25% │ {time_str}'
            return mission, stats

        def _draw_slash_picker():
            out = _real_stdout
            filtered = [(cmd, desc) for cmd, desc in SLASH_COMMANDS_LOCAL if slash_filter == '' or slash_filter in cmd][:12]
            # Draw BELOW the prompt line (Hermes-like): write new lines after prompt
            out.write('\n' + '─' * max(20, cols) + '\n')
            for i, (cmd, desc) in enumerate(filtered):
                marker = '▶ ' if i == slash_picker_idx % max(1, len(filtered)) else '  '
                out.write(f' {marker}{cmd:<36} {desc[:max(10, cols-42)]}\n')
            out.flush()

        def redisplay_screen():
            nonlocal rows, cols
            try:
                rows, cols = os.get_terminal_size()
            except OSError:
                rows, cols = 24, 80
            out = _real_stdout
            out.write('\033[2J\033[H')
            output_text = '\n'.join(get_display_lines())
            if output_text:
                out.write(output_text + '\n')
            mission_line, stats_line = get_status_lines()
            out.write('\033[{};1H'.format(rows-3)); out.write('\033[2K'); out.write(mission_line)
            out.write('\033[{};1H'.format(rows-2)); out.write('\033[2K'); out.write(stats_line)
            out.write('\033[{};1H'.format(rows)); out.write('\033[2K'); out.write(' ❯ ' + current_input)
            if slash_picker_active:
                _draw_slash_picker()
            out.flush()

        def _execute_slash(cmd):
            nonlocal provider, model, exit_requested, pending_menu, flags, fd
            c = cmd.strip().lower()
            if c == '/help':
                add_output('')
                add_output('  Slash Commands')
                for sc, sd in SLASH_COMMANDS_LOCAL:
                    add_output(f'    {sc:<14} {sd}')
                add_output('  Tip: type / to open picker  •  Ctrl+C to interrupt agent')
            elif c == '/provider':
                pending_menu = 'provider'
            elif c == '/model':
                pending_menu = 'model'
            elif c == '/resume':
                result = self._pick_session()
                if result:
                    resume_data = result['resume_data']
                    follow_up = result['follow_up']
                    # Load the previous session's provider/model if available
                    if 'provider' in resume_data:
                        provider = resume_data['provider']
                    if 'model' in resume_data:
                        model = resume_data['model']
                    # Create task for resume (include follow_up if provided)
                    task = resume_data.get('task', '') or '(continue)'
                    if follow_up:
                        task = follow_up
                    # Mark that we're resuming
                    output_lines.clear()
                    add_output(f'  ◈ Resuming session with {provider}:{model}')
                    # Run agent with resume_data (don't spawn thread, let it run inline)
                    agent_running = True
                    
                    # CRITICAL: Restore raw mode before agent (it was disabled by _pick_session menu)
                    try:
                        tty.setcbreak(fd)
                        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                    except:
                        pass
                    
                    self._execute_agent(provider, model, task, steer_queue=steer_queue, stop_event=stop_event, resume_data=resume_data)
                    agent_running = False
                    
                    # CRITICAL: Re-establish raw mode after agent (agent may have modified terminal)
                    try:
                        tty.setcbreak(fd)
                        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                    except:
                        pass
                    
                    # Redraw screen and clear input after resume
                    current_input = ''
                    redisplay_screen()
                else:
                    add_output('  (resume cancelled)')
            elif c in ('/new', '/reset'):
                output_lines.clear(); add_output('  ◈ New session started')
            elif c == '/clear':
                output_lines.clear(); add_output('  ◈ Screen cleared')
            elif c == '/history':
                add_output('  Recent history:')
                for h in self.history[-10:]:
                    ts = h.get('timestamp', '')
                    task = h.get('task', '')
                    add_output(f'    - {ts[:19]}  {task[:80]}')
            elif c == '/save':
                _save_config({'provider': provider, 'model': model}); add_output('  ✓ Session state saved')
            elif c == '/retry':
                add_output('  (retry) submit the same prompt again manually for now')
            elif c == '/undo':
                if output_lines:
                    output_lines.pop()
                add_output('  ✓ Last line removed')
            elif c == '/title':
                add_output('  (title) not implemented yet')
            elif c in ('/branch', '/fork'):
                add_output('  (branch/fork) not implemented yet')
            elif c == '/compress':
                add_output('  (compress) not implemented yet')
            elif c == '/rollback':
                add_output('  (rollback) not implemented yet')
            elif c == '/status':
                m, s = get_status_lines(); add_output(m); add_output(s)
            elif c == '/skills':
                add_output('')
                cmd_skills(type('args', (), {'search': None, 'list': True})())
            elif c == '/memory':
                add_output('')
                cmd_memory(type('args', (), {'search': None, 'list': True, 'summary': False})())
            elif c == '/sessions':
                add_output('')
                cmd_sessions(type('args', (), {'list': True, 'resume': None})())
            elif c == '/monitor':
                add_output('')
                cmd_monitor(type('args', (), {'dashboard': True, 'hours': '24', 'reset': False})())
            elif c == '/subagents':
                add_output('')
                cmd_subagents(type('args', (), {'status': True, 'list': False})())
            elif c == '/memory-advanced':
                add_output('')
                cmd_memory_advanced(type('args', (), {'stats': True, 'high_confidence': False, 'unused': False})())
            elif c == '/quit':
                exit_requested = True

        def handle_input_key(key):
            nonlocal current_input, history_index, slash_picker_active, slash_picker_idx, slash_filter
            nonlocal exit_requested, pending_menu, agent_running, agent_stop_event
            nonlocal current_task, current_turn

            if slash_picker_active:
                filtered = [(cmd, desc) for cmd, desc in SLASH_COMMANDS_LOCAL if slash_filter == '' or slash_filter in cmd]
                if key in ('\x1b[A', '[A', '\x1bOA', 'OA'):
                    slash_picker_idx = (slash_picker_idx - 1) % max(1, len(filtered)); redisplay_screen(); return
                if key in ('\x1b[B', '[B', '\x1bOB', 'OB'):
                    slash_picker_idx = (slash_picker_idx + 1) % max(1, len(filtered)); redisplay_screen(); return
                if key in ('\r', '\n'):
                    chosen = filtered[slash_picker_idx % len(filtered)][0] if filtered else current_input
                    # slash list is overlay-only; nothing to clear
                    slash_picker_active = False; slash_filter = ''; current_input = ''
                    _execute_slash(chosen); redisplay_screen(); return
                if key == '\x1b':
                    # Bare ESC only dismisses picker; '[A'/'[B' are handled as arrows
                    # slash list is overlay-only; nothing to clear
                    slash_picker_active = False; slash_filter = ''; current_input = ''; redisplay_screen(); return
                if key in ('\x7f', '\x08'):
                    if slash_filter:
                        slash_filter = slash_filter[:-1]
                        current_input = '/' + slash_filter
                    else:
                        # slash list is overlay-only; nothing to clear
                        slash_picker_active = False
                        current_input = ''
                    redisplay_screen(); return
                if len(key) == 1 and ord(key) >= 32:
                    slash_filter += key
                    current_input = '/' + slash_filter
                    slash_picker_idx = 0
                    redisplay_screen()
                    return
                return

            if key == '/' and not current_input:
                slash_picker_active = True
                slash_picker_idx = 0
                slash_filter = ''
                current_input = '/'
                # Fallback visibility disabled now that picker draws below prompt
                redisplay_screen()
                return

            if key in ('\r', '\n'):
                text = current_input.strip()
                current_input = ''; history_index = -1
                if not text:
                    redisplay_screen(); return
                if text not in input_history:
                    input_history.append(text)
                    try:
                        with open(SCRIPT_DIR / '.prompt_history', 'a') as f:
                            f.write(text + '\n')
                    except Exception:
                        pass
                if text.startswith('/'):
                    _execute_slash(text); redisplay_screen(); return
                if agent_running:
                    add_output(f'  → steering: {text}')
                    steer_queue.put(text)
                    redisplay_screen(); return

                add_output(f'  ❯ {text}')
                self._save_history(provider, model, text)
                _save_config({'provider': provider, 'model': model})
                agent_stop_event = _threading.Event()
                agent_running = True
                current_task = text
                current_turn = 0

                def run_agent_bg(task=text):
                    nonlocal agent_running, current_task, current_turn, agent_stop_event
                    old_stdout, old_stderr, old_stdin = sys.stdout, sys.stderr, sys.stdin
                    try:
                        sys.stdout = _RealtimeCapture(add_output)
                        sys.stderr = sys.stdout

                        class _SteerStdin:
                            def isatty(self): return False
                            def read(self, n=1): return ''
                            def readline(self):
                                try:
                                    return steer_queue.get_nowait() + '\n'
                                except Exception:
                                    return ''
                            def fileno(self): raise IOError('no fileno')

                        sys.stdin = _SteerStdin()
                        self._execute_agent(provider, model, task, steer_queue=steer_queue, stop_event=agent_stop_event)
                    except Exception as e:
                        import traceback
                        add_output(f'  [!] Agent error: {e}')
                        add_output(traceback.format_exc())
                    finally:
                        sys.stdout, sys.stderr, sys.stdin = old_stdout, old_stderr, old_stdin
                        agent_running = False
                        redisplay_screen()

                _threading.Thread(target=run_agent_bg, daemon=True).start()
                redisplay_screen(); return

            if key in ('\x7f', '\x08'):
                current_input = current_input[:-1]; redisplay_screen(); return

            if key in ('\x03',):
                # slash list is overlay-only; nothing to clear
                if agent_running:
                    if agent_stop_event: agent_stop_event.set()
                    add_output('  ↯ Interrupted — agent stopping after current turn')
                    redisplay_screen()
                else:
                    exit_requested = True
                return

            if key == '\x1b':
                if agent_running:
                    if agent_stop_event: agent_stop_event.set()
                    add_output('  ↯ Interrupted — agent stopping after current turn')
                else:
                    current_input = ''; history_index = -1; slash_picker_active = False; slash_filter = ''
                redisplay_screen(); return

            if key in ('\x1b[A', '[A', '\x1bOA', 'OA'):
                if input_history:
                    history_index = min(history_index + 1, len(input_history) - 1)
                    current_input = input_history[-(history_index + 1)]
                    redisplay_screen()
                return

            if key in ('\x1b[B', '[B', '\x1bOB', 'OB'):
                if history_index > 0:
                    history_index -= 1
                    current_input = input_history[-(history_index + 1)]
                else:
                    history_index = -1
                    current_input = ''
                redisplay_screen(); return

            if len(key) == 1 and ord(key) >= 32:
                current_input += key
                redisplay_screen()

        add_output('')
        add_output('  ⚕ Forest Gump')
        add_output(f'  Provider  {provider}  {model}')
        add_output('  Commands')
        add_output('    /new       Start a new session')
        add_output('    /provider  Switch AI provider')
        add_output('    /model     Switch AI model')
        add_output('    /resume    Resume previous session')
        add_output('    /help      Show all slash commands')

        try:
            if Path(SCRIPT_DIR / '.prompt_history').exists():
                with open(SCRIPT_DIR / '.prompt_history', 'r') as f:
                    input_history = [line.strip() for line in f.readlines() if line.strip()]
        except Exception:
            input_history = []

        redisplay_screen()

        try:
            fd = _real_stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            tty.setcbreak(fd)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            _real_stdout.write('\033[?2004h')
            _real_stdout.flush()

            while not exit_requested:
                try:
                    b = os.read(fd, 1)
                    char = b.decode('utf-8', errors='replace')
                    if char == '\x1b':
                        # Robust escape-sequence collection from raw fd
                        rest = ''
                        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
                        try:
                            for _ in range(8):
                                rdy, _, _ = select.select([fd], [], [], 0.03)
                                if not rdy:
                                    break
                                c = os.read(fd, 1).decode('utf-8', errors='replace')
                                rest += c
                                if c and (c[-1].isalpha() or c[-1] in ('~',)):
                                    break
                        finally:
                            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                        char = '\x1b' + rest

                        if char == '\x1b[200~':
                            paste_buf = ''
                            fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
                            try:
                                while True:
                                    rdy, _, _ = select.select([_real_stdin], [], [], 1.0)
                                    if not rdy:
                                        break
                                    c = os.read(fd, 128).decode('utf-8', errors='replace')
                                    if '\x1b[201~' in c:
                                        paste_buf += c.split('\x1b[201~')[0]
                                        break
                                    paste_buf += c
                            finally:
                                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                            first_line = paste_buf.split('\n')[0].rstrip('\r')
                            current_input += first_line
                            redisplay_screen()
                            char = ''

                    if char:
                        handle_input_key(char)
                except (IOError, BlockingIOError, OSError):
                    pass

                if pending_menu:
                    _real_stdout.write('\033[?2004l')
                    _real_stdout.flush()
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    try:
                        if pending_menu == 'provider':
                            provider_names = list(self.providers.keys())
                            provider_labels = [self.providers[p]['label'] for p in provider_names]
                            provider_descs = [self.providers[p]['desc'] for p in provider_names]
                            provider_idx = self.show_menu('Select Provider', provider_labels, provider_descs)
                            if provider_idx is not None and 0 <= provider_idx < len(provider_names):
                                provider = provider_names[provider_idx]
                                model = self._pick_model(provider)
                                _save_config({'provider': provider, 'model': model})
                        elif pending_menu == 'model':
                            model = self._pick_model(provider)
                            _save_config({'provider': provider, 'model': model})
                    finally:
                        pending_menu = None
                        try:
                            tty.setcbreak(fd)
                            _real_stdout.write('\033[?2004h')
                            _real_stdout.flush()
                            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                        except Exception:
                            pass
                    redisplay_screen()

                time.sleep(0.05)

        except KeyboardInterrupt:
            pass
        finally:
            try:
                _real_stdout.write('\033[?2004l')
                _real_stdout.flush()
            except Exception:
                pass
            try:
                termios.tcsetattr(_real_stdin.fileno(), termios.TCSADRAIN, old_settings)
            except Exception:
                pass
            _real_stdout.write('\033[2J\033[H')
            _real_stdout.flush()

    def _run_fallback(self, provider, model, initial_task=None):
        """Fallback to raw terminal input without fixed input area."""
        first_run = True
        cmd_history = []  # Track command history for up/down navigation
        # Task prompt loop — /provider and /model loop back; /resume + task launch
        while True:
            if first_run:
                # Show banner once at startup
                _print_banner(provider, model, self.history)
                first_run = False
            else:
                self.clear_screen()
                self.display_header()
                print(f' {_BLD}{provider}{_RST}  {_DIM}{model}{_RST}\n')

            if self.history and not NO_COLOR:
                print(f' {_DIM}Recent{_RST}')
                entry = self.history[-1]
                dt = datetime.fromisoformat(entry['timestamp']).strftime('%H:%M')
                print(f'  {_DIM}↳ [{dt}] {entry["task"][:60]}{_RST}')
                print()

            sessions = _load_sessions(SCRIPT_DIR / 'sessions', limit=1)
            if sessions:
                s   = sessions[0]
                age = _rel_time(s['ts'])
                print(f'  {_GLD}/resume{_RST}  {_DIM}↳ last: {age}  {s["turns"]}t  {s["task"][:48]}{_RST}')
                print()

            _hr()

            # Read with timeout for auto-refresh every 3 seconds
            def redraw_banner():
                """Redraw banner when timeout occurs."""
                try:
                    rows, cols = os.get_terminal_size()
                except:
                    rows, cols = 24, 80
                os.system('clear' if os.name != 'nt' else 'cls')
                _print_banner(provider, model, input_history[-5:])

            try:
                task = _readline_slash(timeout_seconds=3, on_timeout=redraw_banner, history=cmd_history)
                if task is None:
                    # Timeout occurred, banner redrawn, continue waiting
                    continue
                task = task.strip()
            except Exception:
                print(f' {_GLD}>{_RST} ', end='', flush=True)
                task = input().strip()

            if not task:
                continue

            # Handle slash commands
            task_lower = task.lower()

            if task_lower == '/chat':
                print(f' {_GLD}Task:{_RST} ', end='', flush=True)
                chat_task = input().strip()
                if chat_task:
                    self._save_history(provider, model, chat_task)
                    _save_config({'provider': provider, 'model': model})
                    self._execute_agent(provider, model, chat_task)
                continue

            if task_lower == '/skills':
                print(f' {_GLD}Search (or press Enter for list):{_RST} ', end='', flush=True)
                search_term = input().strip()
                print()
                if search_term:
                    cmd_skills(type('args', (), {'search': search_term, 'list': False})())
                else:
                    cmd_skills(type('args', (), {'search': None, 'list': True})())
                print(f'\n{_DIM}Press Enter to continue...{_RST}', end='', flush=True)
                input()
                continue

            if task_lower == '/memory':
                print(f' {_GLD}Search (or press Enter for list):{_RST} ', end='', flush=True)
                search_term = input().strip()
                print()
                if search_term:
                    cmd_memory(type('args', (), {'search': search_term, 'list': False, 'summary': False})())
                else:
                    cmd_memory(type('args', (), {'search': None, 'list': True, 'summary': False})())
                print(f'\n{_DIM}Press Enter to continue...{_RST}', end='', flush=True)
                input()
                continue

            if task_lower == '/sessions':
                print()
                cmd_sessions(type('args', (), {'list': True, 'resume': None})())
                print(f'\n{_DIM}Press Enter to continue...{_RST}', end='', flush=True)
                input()
                continue

            if task_lower == '/monitor':
                print()
                cmd_monitor(type('args', (), {'dashboard': True, 'hours': '24', 'reset': False})())
                print(f'\n{_DIM}Press Enter to continue...{_RST}', end='', flush=True)
                input()
                continue

            if task_lower == '/subagents':
                print()
                cmd_subagents(type('args', (), {'status': True, 'list': False})())
                print(f'\n{_DIM}Press Enter to continue...{_RST}', end='', flush=True)
                input()
                continue

            if task_lower == '/memory-advanced':
                print()
                cmd_memory_advanced(type('args', (), {'stats': True, 'high_confidence': False, 'unused': False})())
                print(f'\n{_DIM}Press Enter to continue...{_RST}', end='', flush=True)
                input()
                continue

            if task_lower == '/provider':
                provider_names  = list(self.providers.keys())
                provider_labels = [self.providers[p]['label'] for p in provider_names]
                provider_descs  = [self.providers[p]['desc']  for p in provider_names]
                provider_idx = self.show_menu('Select Provider', provider_labels, provider_descs)
                provider     = provider_names[provider_idx]
                model        = self._pick_model(provider)
                _save_config({'provider': provider, 'model': model})
                continue

            if task_lower == '/model':
                model = self._pick_model(provider)
                _save_config({'provider': provider, 'model': model})
                continue

            if task_lower.startswith('/resume'):
                follow_up = task[7:].strip()
                self._pick_session(follow_up_task=follow_up)
                return

            # Regular chat task
            self._save_history(provider, model, task)
            _save_config({'provider': provider, 'model': model})
            self._execute_agent(provider, model, task)


def main():
    """Main entry point for CLI/interactive mode."""
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

    # If --version flag or no command, show version or run interactive menu
    if args.version or (not args.command and '--version' in sys.argv):
        return cmd_version(args)

    # If a command was specified, run it
    if args.command and hasattr(args, 'func'):
        return args.func(args)

    # Otherwise, run interactive menu
    menu = MenuSystem()
    menu.run(initial_task=None)
    return 0


if __name__ == '__main__':
    sys.exit(main())
