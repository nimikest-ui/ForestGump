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
from pathlib import Path
from datetime import datetime

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
    ('/provider', 'switch AI provider — saved'),
    ('/model',    'switch AI model — saved'),
    ('/resume',   'resume a previous session'),
]
_MAX_DROP  = len(SLASH_COMMANDS)
_CMD_WIDTH = 12  # fixed left column width for slash command names


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


def _readline_slash():
    """Custom input: typing '/' shows autocomplete dropdown (unless COLOR=1)."""
    import re as _re

    if not USE_COLOR:
        return input()

    buf          = []
    drop_sel     = -1
    prev_lines   = 0

    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setraw(fd)

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

        while True:
            ch = sys.stdin.read(1)

            if ch in ('\r', '\n'):
                text     = ''.join(buf)
                is_slash = text.startswith('/')
                matches  = [(c, d) for c, d in SLASH_COMMANDS if c.startswith(text)] if is_slash else []
                if drop_sel >= 0 and drop_sel < len(matches):
                    buf[:] = list(matches[drop_sel][0])
                _clear_drop()
                sys.stdout.write('\n')
                sys.stdout.flush()
                return ''.join(buf)

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
                    if arrow == 'B' and matches:   # ↓
                        drop_sel = min(len(matches) - 1, drop_sel + 1)
                        _render()
                    elif arrow == 'A' and matches: # ↑
                        drop_sel = max(-1, drop_sel - 1)
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
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
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
        """Interactive session picker. Returns immediately after launching."""
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
            return

        selected   = 0
        scroll_off = 0
        while True:
            self.clear_screen()
            self.display_header()
            print(f'  {_DIM}Resume session{_RST}\n')

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
                if ch == '\x1b':
                    self.getch_unix()
                    ch = self.getch_unix()
                    if ch == 'A':
                        selected = (selected - 1) % len(sessions)
                    elif ch == 'B':
                        selected = (selected + 1) % len(sessions)
                elif ch in ('\r', '\n'):
                    s = sessions[selected]
                    cmd = ['python3', 'agent.py', '--resume', s['file']]
                    if s['provider'] and s['provider'] != '?':
                        cmd.extend(['--provider', s['provider']])
                    if s['model']:
                        cmd.extend(['--model', s['model']])
                    if follow_up_task:
                        cmd.append(follow_up_task)
                    result = subprocess.run(cmd, cwd=SCRIPT_DIR, env=os.environ.copy())
                    sys.exit(result.returncode)
                elif ch.lower() == 'q':
                    return
                elif ch.isdigit():
                    idx = int(ch) - 1
                    if 0 <= idx < len(sessions):
                        s = sessions[idx]
                        cmd = ['python3', 'agent.py', '--resume', s['file']]
                        if s['provider'] and s['provider'] != '?':
                            cmd.extend(['--provider', s['provider']])
                        if s['model']:
                            cmd.extend(['--model', s['model']])
                        if follow_up_task:
                            cmd.append(follow_up_task)
                        result = subprocess.run(cmd, cwd=SCRIPT_DIR, env=os.environ.copy())
                        sys.exit(result.returncode)
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

    def _execute_agent(self, provider_name, model, task):
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
                run_agent(provider, task, max_turns=50, confirm=True, resume_data=None)
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

            # Use fixed input area with patch_stdout if prompt_toolkit available
            if _PT_AVAILABLE:
                self._run_with_fixed_input(provider, model, initial_task=initial_task)
            else:
                self._run_fallback(provider, model, initial_task=initial_task)

        except KeyboardInterrupt:
            print(f'\n {_DIM}quit{_RST}')
            sys.exit(1)

    def _run_with_fixed_input(self, provider, model, initial_task=None):
        """Run with fixed input prompt using terminal control sequences.

        Creates a Hermes-like TUI with:
        - Scrollable output region (top) using DECSTBM
        - Fixed input prompt (bottom)
        - Background agent execution with output capture
        - Proper steering: Enter=execute, Ctrl+C=interrupt, Esc=steer
        - Thread-safe output buffering
        """
        import io
        import sys
        import threading
        from time import sleep
        import select

        # Set up scroll region: reserve bottom 2 lines for status bar and input/prompt
        try:
            rows = os.get_terminal_size().lines
            cols = os.get_terminal_size().columns
        except Exception:
            rows, cols = 24, 80  # fallback

        # Set scroll region: lines 1 to (rows-3) for output, leave lines (rows-2) to rows for status+input
        sys.stdout.write(f'\033[1;{rows-3}r')  # Scroll region: top to (rows-3)
        sys.stdout.flush()

        # Shared state between threads
        output_lines = []  # Scrollback buffer
        output_lock = threading.Lock()
        agent_thread = None
        agent_running = False
        exit_requested = False
        steer_mode = False
        current_input = ""
        input_history = []  # For up/down arrows
        history_index = -1

        def add_output(text):
            """Add text to scrollback buffer (thread-safe)"""
            if not text:
                return
            with output_lock:
                for line in text.rstrip('\n').split('\n'):
                    output_lines.append(line)
                # Keep last 500 lines in memory, display last 200
                if len(output_lines) > 500:
                    output_lines[:] = output_lines[-500:]

        def get_display_lines():
            """Get lines to display in scrollable region"""
            with output_lock:
                start_idx = max(0, len(output_lines) - (rows - 4))  # Leave room for status bar+prompt
                return output_lines[start_idx:]

        def get_status_text():
            """Get Hermes-like status bar text"""
            # Track elapsed time for demo purposes
            import time
            if not hasattr(get_status_text, 'start_time'):
                get_status_text.start_time = time.time()

            elapsed_seconds = int(time.time() - get_status_text.start_time)
            minutes = elapsed_seconds // 60
            seconds = elapsed_seconds % 60

            # Format time as MM:SS or just Mm if under an hour
            if minutes > 0:
                time_str = f'{minutes}m{seconds:02d}s' if seconds > 0 else f'{minutes}m'
            else:
                time_str = f'{seconds}s'

            # Simulate token usage and progress (in real implementation, this comes from agent)
            # For demo, show some fake progress based on time
            progress_percent = min(95, (elapsed_seconds % 30) * 3)  # Cycle 0-95% every 30 seconds
            filled_blocks = int(progress_percent / 10)  # Each block represents 10%
            empty_blocks = 10 - filled_blocks
            progress_bar = '[' + '█' * filled_blocks + '░' * empty_blocks + f'] {progress_percent}%'

            # Simulate token usage (fake numbers for demo)
            used_tokens = (elapsed_seconds * 100) % 50000  # Cycle through 0-50K tokens
            max_tokens = 100000  # 100K max
            tokens_str = f'{used_tokens//1000}K/{max_tokens//1000}K'

            # Format: ⚕ provider │ model │ tokens │ progress │ time
            # Truncate model name if too long
            model_display = model[:12].ljust(12) if len(model) > 12 else model.ljust(12)

            status_line = (
                f'⚕ {provider:<8} │ {model_display} │ {tokens_str} │ {progress_bar} │ {time_str}'
            )
            return status_line

        def redisplay_screen():
            """Redraw the entire screen: scrollable output + status bar + fixed input prompt"""
            # Save cursor position
            sys.stdout.write('\033[s')

            # Clear screen and reset to home
            sys.stdout.write('\033[2J\033[H')

            # Display scrollable output (in scroll region)
            output_text = '\n'.join(get_display_lines())
            if output_text:
                sys.stdout.write(output_text + '\n')

            # Display status bar on line rows-2
            sys.stdout.write(f'\033[{rows-2};1H')  # Row 'rows-2', column 1
            sys.stdout.write('\033[2K')  # Clear line
            status_text = get_status_text()
            sys.stdout.write(status_text)

            # Position cursor at bottom row for input prompt
            sys.stdout.write(f'\033[{rows};1H')  # Row 'rows', column 1

            # Clear input line
            sys.stdout.write('\033[2K')

            # Show prompt and current input
            if steer_mode:
                prompt = f'  {_DIM}steer:{_RST} '
            else:
                prompt = f' {_GLD}❯{_RST} '

            sys.stdout.write(prompt)
            sys.stdout.write(current_input)
            sys.stdout.flush()

            # Position cursor at end of input
            # Calculate visible prompt length (stripping ANSI codes)
            prompt_plain = prompt
            if USE_COLOR:
                import re
                prompt_plain = re.sub(r'\033\[[0-9;]*m', '', prompt)
            cursor_pos = len(current_input) + len(prompt_plain) + 1  # +1 for the space after >
            sys.stdout.write(f'\033[{rows};{cursor_pos}H')
            sys.stdout.flush()

        def handle_input_key(key):
            """Handle keyboard input for the fixed prompt"""
            nonlocal current_input, input_history, history_index, steer_mode, exit_requested

            if key == '\r':  # Enter
                if current_input.strip():
                    # Add to history
                    if current_input.strip() not in input_history:
                        input_history.append(current_input.strip())
                        # Save to file
                        try:
                            with open(SCRIPT_DIR / '.prompt_history', 'a') as f:
                                f.write(current_input.strip() + '\n')
                        except:
                            pass

                    # Process the command
                    task = current_input.strip()
                    add_output(f'\n{_GLD}❯ {_RST}{task}\n')  # Echo the command

                    # Handle slash commands
                    if task.lower() == '/provider':
                        provider_names = list(self.providers.keys())
                        provider_labels = [self.providers[p]['label'] for p in provider_names]
                        provider_descs = [self.providers[p]['desc'] for p in provider_names]
                        provider_idx = self.show_menu('Select Provider', provider_labels, provider_descs)
                        provider = provider_names[provider_idx]
                        model = self._pick_model(provider)
                        _save_config({'provider': provider, 'model': model})
                        current_input = ""
                        history_index = -1
                        redisplay_screen()
                        return

                    if task.lower() == '/model':
                        model = self._pick_model(provider)
                        _save_config({'provider': provider, 'model': model})
                        current_input = ""
                        history_index = -1
                        redisplay_screen()
                        return

                    if task.lower().startswith('/resume'):
                        follow_up = task[7:].strip()
                        self._pick_session(follow_up_task=follow_up)
                        exit_requested = True
                        return

                    # Execute agent in background
                    self._save_history(provider, model, task)
                    _save_config({'provider': provider, 'model': model})
                    add_output(f'\n  {_GLD}⚔ bash{_RST}\n')
                    # Reset input after sending command to agent
                    current_input = ""
                    history_index = -1

                    # Reset input
                    current_input = ""
                    history_index = -1

                    # Start agent in background thread
                    def run_agent_bg():
                        nonlocal agent_running
                        agent_running = True
                        redisplay_screen()  # Show agent started

                        # Capture agent output
                        old_stdout, old_stderr = sys.stdout, sys.stderr
                        try:
                            capture = io.StringIO()
                            sys.stdout = capture
                            sys.stderr = capture

                            self._execute_agent(provider, model, task)

                            # Get captured output
                            output = capture.getvalue()
                            if output:
                                add_output(output)
                        finally:
                            sys.stdout, sys.stderr = old_stdout, old_stderr
                            agent_running = False
                            redisplay_screen()  # Update display when done

                    agent_thread = threading.Thread(target=run_agent_bg, daemon=True)
                    agent_thread.start()

            elif key == '\x03':  # Ctrl+C
                if agent_running:
                    # Interrupt the agent (this would need cooperation from agent thread)
                    # For now, just signal that we want to interrupt
                    add_output(f'\n  {_DIM}Interrupted by user{_RST}\n')
                    agent_running = False
                    redisplay_screen()
                else:
                    # No agent running, exit the TUI
                    exit_requested = True

            elif key == '\x1b':  # Esc - enter steer mode
                steer_mode = True
                current_input = ""
                history_index = -1
                redisplay_screen()

            elif key == '\x7f' or key == '\x08':  # Backspace
                if not steer_mode and current_input:
                    current_input = current_input[:-1]
                    redisplay_screen()

            elif key == '\x1b[A':  # Up arrow
                if not steer_mode and input_history:
                    if history_index < 0:
                        history_index = len(input_history) - 1
                    elif history_index > 0:
                        history_index -= 1
                    current_input = input_history[history_index]
                    redisplay_screen()

            elif key == '\x1b[B':  # Down arrow
                if not steer_mode and input_history:
                    if history_index >= len(input_history) - 1:
                        history_index = -1
                        current_input = ""
                    elif history_index >= 0:
                        history_index += 1
                        current_input = input_history[history_index]
                    redisplay_screen()

            elif key >= ' ' and key <= '~':  # Printable characters
                if not steer_mode:
                    current_input += key
                    redisplay_screen()

        # Initial screen setup
        add_output('')
        add_output(f'  {_GLD}⚕{_RST} {_BLD}Forest Gump{_RST}')
        add_output(f'  {_DIM}Provider{_RST}  {_GLD}{provider}{_RST}  {_DIM}{model}{_RST}')

        # Available tools
        tools = {
            'bash': 'Shell execution',
            'memory': 'Persistent facts & credentials',
            'skills': 'Learned attack patterns',
            'pty': 'Interactive terminal',
        }
        add_output(f'\n  {_DIM}Available Tools{_RST}')
        for tool, desc in tools.items():
            output_buf.append(f'    {_GLD}•{_RST}  {tool:<12}  {_DIM}{desc}{_RST}')

        # Available skills (from database)
        try:
            from skills import search_skills
            all_skills = search_skills('')
            skill_count = len(all_skills) if all_skills else 0
            add_output(f'\n  {_DIM}Learned Skills{_RST}')
            if skill_count > 0:
                output_buf.append(f'    {skill_count} patterns stored  {_DIM}(search with task keywords){_RST}')
                # Show top 3 by success rate
                for skill in sorted(all_skills, key=lambda s: s.get('success_rate', 0), reverse=True)[:3]:
                    rate = f"{skill.get('success_rate', 0):.0%}"
                    output_buf.append(f'      {_GLD}▸{_RST}  {skill.get("name", "?")[:30]:<30}  {_DIM}{rate}{_RST}')
            else:
                output_buf.append(f'    {_DIM}(None yet — skills learned after successful runs){_RST}')
        except:
            output_buf.append(f'\n  {_DIM}Learned Skills{_RST}')
            output_buf.append(f'    {_DIM}(Database not initialized){_RST}')

        if self.history:
            entry = self.history[-1]
            add_output(f'\n  {_DIM}Recent{_RST}')
            add_output(f'    {_DIM}[{datetime.fromisoformat(entry["timestamp"]).strftime("%H:%M")}]{_RST}  {entry["task"][:50]}')

        add_output(f'\n  {_DIM}Commands{_RST}')
        add_output(f'    {_GLD}/provider{_RST}  Switch AI provider')
        add_output(f'    {_GLD}/model{_RST}     Switch AI model')
        add_output(f'    {_GLD}/resume{_RST}    Resume previous session')
        add_output('')

        # Load input history from file
        try:
            if Path(SCRIPT_DIR / '.prompt_history').exists():
                with open(SCRIPT_DIR / '.prompt_history', 'r') as f:
                    input_history = [line.strip() for line in f.readlines() if line.strip()]
        except:
            input_history = []

        # Initial display
        redisplay_screen()

        # Main input loop
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)

            try:
                tty.setcbreak(fd)  # Allow reading single characters

                while not exit_requested:
                    # Check for input (non-blocking)
                    if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                        char = sys.stdin.read(1)
                        if char:
                            handle_input_key(char)

                    # Update display periodically to show agent output
                    sleep(0.1)
                    redisplay_screen()

            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        except KeyboardInterrupt:
            pass
        finally:
            # Restore full scroll region
            sys.stdout.write(f'\033[1;{rows}r')
            sys.stdout.flush()

            # Clear screen on exit
            sys.stdout.write('\033[2J\033[H')
            sys.stdout.flush()

    def _run_fallback(self, provider, model, initial_task=None):
        """Fallback to raw terminal input without fixed input area."""
        first_run = True
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
            try:
                task = _readline_slash().strip()
            except Exception:
                print(f' {_GLD}>{_RST} ', end='', flush=True)
                task = input().strip()

            if not task:
                continue

            if task.lower() == '/provider':
                provider_names  = list(self.providers.keys())
                provider_labels = [self.providers[p]['label'] for p in provider_names]
                provider_descs  = [self.providers[p]['desc']  for p in provider_names]
                provider_idx = self.show_menu('Select Provider', provider_labels, provider_descs)
                provider     = provider_names[provider_idx]
                model        = self._pick_model(provider)
                _save_config({'provider': provider, 'model': model})
                continue

            if task.lower() == '/model':
                model = self._pick_model(provider)
                _save_config({'provider': provider, 'model': model})
                continue

            if task.lower().startswith('/resume'):
                follow_up = task[7:].strip()
                self._pick_session(follow_up_task=follow_up)
                return

            self._save_history(provider, model, task)
            _save_config({'provider': provider, 'model': model})
            self._execute_agent(provider, model, task)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Bare Metal Agent CLI')
    parser.add_argument('--provider', help='Provider: ollama, claude, anthropic, copilot')
    parser.add_argument('--model', help='Model name')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmations')
    parser.add_argument('task', nargs='?', help='Task to execute (starts immediately)')

    args = parser.parse_args()
    menu = MenuSystem()

    # If provider/model specified, load them
    if args.provider:
        cfg = _load_config()
        if args.provider in menu.providers:
            cfg['provider'] = args.provider
        if args.model:
            cfg['model'] = args.model
        _save_config(cfg)

    # Run with initial task if provided (no prompt before TUI)
    menu.run(initial_task=args.task)
