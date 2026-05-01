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
from pathlib import Path
from datetime import datetime

SCRIPT_DIR   = Path(__file__).parent.resolve()
HISTORY_FILE = SCRIPT_DIR / '.menu_history.json'
CONFIG_FILE  = SCRIPT_DIR / '.agent_config.json'


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
_DIM = '\033[2m' if USE_COLOR else ''
_RST = '\033[0m' if USE_COLOR else ''
_BLD = '\033[1m' if USE_COLOR else ''
_GRN = '\033[32m' if USE_COLOR else ''
_RED = '\033[31m' if USE_COLOR else ''
_ORG = '\033[38;5;208m' if USE_COLOR else ''


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
        sys.stdout.write(f'\r\033[K {_ORG}>{_RST} {colored}')

        # Draw / clear dropdown lines below
        n = max(len(matches), prev_lines)
        for i in range(n):
            if i < len(matches):
                cmd, desc = matches[i]
                if i == drop_sel:
                    row = f'  {_ORG}❯{_RST} {_BLU}{_BLD}{cmd:<{_CMD_WIDTH}}{_RST}  {_DIM}{desc}{_RST}'
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
            print(f'\n {_ORG}●{_RST} {_BLD}Agent{_RST}\n')

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
                    marker = f'{_ORG}❯{_RST}'
                    label  = f'{_BLD}{options[i]}{_RST}'
                else:
                    marker = ' '
                    label  = f'{_DIM}{options[i]}{_RST}'
                if installed:
                    desc = f'  {_ORG}●{_RST} {_DIM}{clean_desc}{_RST}'
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
            print(f' {_ORG}>{_RST} ', end='', flush=True)
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
                    print(f'  {_ORG}❯{_RST} {_BLD}{line}{_RST}')
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

    def _execute_agent(self, provider, model, task):
        cmd = ['python3', 'agent.py', '--provider', provider, '--model', model, task]
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, env=os.environ.copy())
        sys.exit(result.returncode)

    def run(self):
        try:
            # Load saved provider/model; fall back to defaults — no startup menus
            cfg      = _load_config()
            provider = cfg.get('provider')
            model    = cfg.get('model')

            if provider not in self.providers:
                provider = list(self.providers.keys())[0]  # default: ollama
            if model not in self.providers[provider]['models']:
                model = list(self.providers[provider]['models'].keys())[0]

            # Task prompt loop — /provider and /model loop back; /resume + task launch
            while True:
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
                    print(f'  {_ORG}/resume{_RST}  {_DIM}↳ last: {age}  {s["turns"]}t  {s["task"][:48]}{_RST}')
                    print()

                _hr()
                try:
                    task = _readline_slash().strip()
                except Exception:
                    print(f' {_ORG}>{_RST} ', end='', flush=True)
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

        except KeyboardInterrupt:
            print(f'\n {_DIM}quit{_RST}')
            sys.exit(1)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Bare Metal Agent CLI')
    parser.add_argument('--provider', help='Provider: ollama, claude, anthropic, copilot')
    parser.add_argument('--model', help='Model name')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmations')
    parser.add_argument('task', nargs='?', help='Task to execute')

    args = parser.parse_args()
    menu = MenuSystem()

    if args.provider and args.model and args.task:
        menu._direct_run(args.provider, args.model, args.task)
    else:
        menu.run()
