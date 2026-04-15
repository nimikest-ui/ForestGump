#!/usr/bin/env python3
"""
Bare Metal Agent — The anti-framework experiment.
No tools. No playbooks. No tiers. Just a model and a raw shell.

Usage:
  # Claude via Claude Code CLI (OAuth — uses your Pro subscription, no API key)
  python agent.py --provider claude "scan wifi networks"

  # Ollama Cloud (set OLLAMA_API_KEY from ollama.com/settings/keys)
  OLLAMA_API_KEY=your_key python agent.py --provider ollama --model "gpt-oss:120b-cloud" "scan wifi networks"

  # Ollama local
  python agent.py --provider ollama --model "llama3:8b" --host http://localhost:11434 "scan wifi networks"

  # Anthropic API (direct, needs ANTHROPIC_API_KEY)
  python agent.py --provider anthropic "scan wifi networks"

  # YOLO mode (no command confirmation)
  python agent.py --provider claude --no-confirm "scan wifi networks"

  # Resume a previous session
  python agent.py --resume sessions/20260415_190031.json

  # Resume and give a new follow-up task  
  python agent.py --resume sessions/20260415_190031.json "now try a different network"
"""

import os
import sys
import pty
import select
import fcntl
import struct
import termios
import subprocess
import time
import re
import json
import argparse
import uuid
import signal
import glob
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
SESSIONS_DIR = SCRIPT_DIR / 'sessions'
MEMORY_FILE = SCRIPT_DIR / 'memory.json'


# ─── Utilities ────────────────────────────────────────────────

def strip_ansi(text):
    """Remove ANSI escape sequences so the model sees clean text."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b\[.*?[@-~]|\r', '', text)


# ─── Safety Guard ─────────────────────────────────────────────

DANGEROUS_PATTERNS = [
    (r'\brm\s+(-[a-zA-Z]*[rf])', 'rm with -r or -f flags'),
    (r'\brm\s+/', 'rm on absolute path'),
    (r'\bmkfs\b', 'filesystem format'),
    (r'\bdd\b.*\bof=/', 'dd writing to device/disk'),
    (r'\b(shred|wipe)\b', 'disk wipe tool'),
    (r'^\s*format\b', 'format command'),
    (r'>\s*/dev/sd', 'writing to block device'),
    (r'\bsystemctl\s+(stop|disable|mask)\b', 'disabling system services'),
    (r'\biptables\s+.*-F\b', 'flushing firewall rules'),
    (r'\biptables\s+.*DROP.*wlan0\b', 'blocking wlan0 traffic'),
    (r'\bifconfig\s+wlan0\s+down\b', 'taking down wlan0'),
    (r'\bip\s+link\s+set\s+wlan0\s+down\b', 'taking down wlan0'),
    (r'\bnmcli\s+.*wlan0.*disconnect\b', 'disconnecting wlan0'),
    (r'\bairmon-ng\s+.*wlan0\b', 'monitor mode on wlan0'),
    (r'\bairmon-ng\s+check\s+kill\b', 'airmon-ng check kill — kills NetworkManager, will drop internet'),
    (r'wlan0.*mon\b', 'monitor mode on wlan0'),
    (r'\bchmod\s+777\s+/', 'chmod 777 on root paths'),
    (r'\bpasswd\b', 'changing passwords'),
    (r'\buserdel\b', 'deleting users'),
    (r'\breboot\b|\bshutdown\b|\bpoweroff\b|\binit\s+[06]\b', 'system reboot/shutdown'),
]


def is_dangerous(cmd):
    """Return reason string if command matches a dangerous pattern, else None."""
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return reason
    return None


def sanitize_command(cmd):
    """Rewrite background patterns to foreground-friendly equivalents."""
    original = cmd

    # Normalize multiline commands to single line for pattern matching
    flat = re.sub(r'\s*\n\s*', '; ', cmd).strip()

    # Pattern: anything & [;] sleep N [&&;] kill ... [; after_stuff]
    m = re.match(
        r'^(.+?)\s*&\s*;?\s*sleep\s+(\d+)\s*(?:&&|;)\s*(?:sudo\s+)?kill\b[^;]*(;\s*(.*))?$',
        flat, re.DOTALL
    )
    if m:
        main_cmd = m.group(1).strip()
        seconds = min(int(m.group(2)), 30)
        after = (m.group(4) or '').strip()
        # Strip any existing timeout wrapper from main_cmd
        main_cmd = re.sub(r'^(sudo\s+)?timeout\s+\d+\s+', r'\1', main_cmd)
        rewritten = f'sudo timeout {seconds} {main_cmd.removeprefix("sudo").strip()}'
        if after:
            rewritten += f'; {after}'
        return rewritten

    # Simple trailing &
    if re.search(r'&\s*$', flat):
        inner = flat.rstrip('& ').strip()
        inner = re.sub(r'^(sudo\s+)?timeout\s+\d+\s+', r'\1', inner)
        return f'timeout 30 {inner}'

    # Cap excessively long timeouts
    m = re.match(r'^(sudo\s+)?timeout\s+(\d+)\s+(.+)', flat)
    if m and int(m.group(2)) > 30:
        prefix = m.group(1) or ''
        return f'{prefix}timeout 30 {m.group(3)}'

    # Fix double timeout
    m = re.match(r'^(sudo\s+)?timeout\s+\d+\s+(sudo\s+)?timeout\s+(\d+)\s+(.+)', flat)
    if m:
        prefix = m.group(1) or m.group(2) or ''
        seconds = min(int(m.group(3)), 30)
        return f'{prefix}timeout {seconds} {m.group(4)}'

    return cmd


# ─── Persistent PTY Shell ────────────────────────────────────

class Shell:
    """A real pseudo-terminal bash session with sentinel-based output capture."""

    def __init__(self):
        self.master, slave = pty.openpty()
        # Give it a wide terminal so tools don't line-wrap weirdly
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 50, 200, 0, 0))

        self.proc = subprocess.Popen(
            ['/bin/bash', '--norc', '--noprofile'],
            stdin=slave, stdout=slave, stderr=slave,
            preexec_fn=os.setsid,
            env={**os.environ, 'PS1': '', 'TERM': 'dumb', 'COLUMNS': '200'},
        )
        os.close(slave)

        # Non-blocking reads
        flags = fcntl.fcntl(self.master, fcntl.F_GETFL)
        fcntl.fcntl(self.master, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        time.sleep(0.3)
        self._drain()

    # ── internal ──

    def _drain(self):
        while select.select([self.master], [], [], 0.1)[0]:
            try:
                os.read(self.master, 65536)
            except OSError:
                break

    def _read_until(self, sentinel, timeout):
        chunks = []
        deadline = time.time() + timeout
        found_sentinel = False
        while time.time() < deadline:
            ready = select.select([self.master], [], [], 0.5)[0]
            if ready:
                try:
                    data = os.read(self.master, 65536).decode('utf-8', errors='replace')
                    chunks.append(data)
                    if sentinel in ''.join(chunks):
                        found_sentinel = True
                        break
                except OSError:
                    break

        raw = ''.join(chunks)
        idx = raw.find(sentinel)
        if idx != -1:
            raw = raw[:idx]

        if not found_sentinel:
            raw += '\n[command timed out]'

        return strip_ansi(raw).strip()

    # ── public ──

    def run(self, command, timeout=300):
        """Execute command, return clean output."""
        sentinel = f"__SENTINEL_{uuid.uuid4().hex[:8]}__"
        # Wait for any prior output to settle, then send command
        time.sleep(0.2)
        self._drain()
        payload = f"{command}\necho {sentinel}\n"
        os.write(self.master, payload.encode())
        output = self._read_until(sentinel, timeout)

        # If sentinel wasn't found (ncurses apps etc), send Ctrl+C and try to recover
        if '[command timed out]' in output:
            os.write(self.master, b'\x03')
            time.sleep(1)
            self._drain()
            # Try running the sentinel echo again to reset state
            retry_sentinel = f"__SENTINEL_{uuid.uuid4().hex[:8]}__"
            os.write(self.master, f'echo {retry_sentinel}\n'.encode())
            self._read_until(retry_sentinel, 5)

        # Strip the echoed command, sentinel, and common noise from output
        lines = output.split('\n')
        cleaned = [
            ln for ln in lines
            if ln.strip() != command.strip()
            and f'echo {sentinel}' not in ln
            and '__SENTINEL_' not in ln
        ]
        return '\n'.join(cleaned).strip()

    def ctrl_c(self):
        os.write(self.master, b'\x03')
        time.sleep(0.3)
        self._drain()

    def close(self):
        try:
            os.close(self.master)
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


# ─── Model Providers ─────────────────────────────────────────

class AnthropicProvider:
    def __init__(self, model='claude-sonnet-4-20250514'):
        from anthropic import Anthropic
        self.client = Anthropic()
        self.model = model
        self.name = f'anthropic/{model}'

    def chat(self, messages, system):
        r = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        return r.content[0].text


class OllamaProvider:
    def __init__(self, model='gpt-oss:120b-cloud', host=None):
        from ollama import Client
        api_key = os.environ.get('OLLAMA_API_KEY')
        # Default to ollama.com cloud if API key is set and no host specified
        if not host:
            host = 'https://ollama.com' if api_key else None
        kwargs = {}
        if host:
            kwargs['host'] = host
        if api_key:
            kwargs['headers'] = {'Authorization': f'Bearer {api_key}'}
        self.client = Client(**kwargs)
        self.model = model
        self.name = f'ollama/{model}'

    def chat(self, messages, system):
        msgs = [{'role': 'system', 'content': system}] + messages
        r = self.client.chat(self.model, messages=msgs)
        return r['message']['content']


class ClaudeCliProvider:
    """Uses the Claude Code CLI with OAuth (Pro subscription, no API key needed)."""

    def __init__(self, model='sonnet'):
        self.model = model
        self.name = f'claude-cli/{model}'
        self._history = []  # maintain conversation for context

    def chat(self, messages, system):
        # Build the full prompt from conversation history
        prompt_parts = []
        for msg in messages:
            role = msg['role']
            content = msg['content']
            if role == 'user':
                prompt_parts.append(content)
            elif role == 'assistant':
                prompt_parts.append(f'[Previous response]\n{content}')

        full_prompt = '\n\n'.join(prompt_parts)

        cmd = [
            'claude', '-p',
            '--model', self.model,
            '--output-format', 'text',
            '--system-prompt', system,
            '--tools', '',
            '--verbose',
        ]

        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            raise RuntimeError(f'Claude CLI error: {result.stderr.strip()}')

        return result.stdout.strip()


# ─── Memory ───────────────────────────────────────────────────

def load_memory():
    """Load persistent memory (things learned across sessions)."""
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return {'facts': [], 'networks': {}, 'credentials': {}, 'notes': []}


def save_memory(mem):
    """Save persistent memory."""
    with open(MEMORY_FILE, 'w') as f:
        json.dump(mem, f, indent=2)


def memory_context(mem):
    """Format memory into a string the model can reference."""
    parts = []
    if mem.get('facts'):
        parts.append('Known facts:\n' + '\n'.join(f'- {f}' for f in mem['facts'][-20:]))
    if mem.get('networks'):
        nets = []
        for ssid, info in mem['networks'].items():
            nets.append(f'- {ssid}: {json.dumps(info)}')
        parts.append('Known networks:\n' + '\n'.join(nets))
    if mem.get('credentials'):
        creds = []
        for target, info in mem['credentials'].items():
            creds.append(f'- {target}: {json.dumps(info)}')
        parts.append('Credentials found:\n' + '\n'.join(creds))
    if mem.get('notes'):
        parts.append('Notes:\n' + '\n'.join(f'- {n}' for n in mem['notes'][-10:]))
    return '\n\n'.join(parts) if parts else ''


def extract_memory_updates(response, output, cmd, mem):
    """Auto-extract useful info to remember from agent output."""
    # Auto-detect found passwords/keys in output
    for pattern, label in [
        (r'WPA PSK:\s*["\']?([^"\'\'\n]+)', 'wpa_psk'),
        (r'WPS PIN:\s*["\']?([^"\'\'\n]+)', 'wps_pin'),
        (r'passphrase:\s*["\']?([^"\'\'\n]+)', 'passphrase'),
        (r'PASSWORD:\s*["\']?([^"\'\'\n]+)', 'password'),
    ]:
        m = re.search(pattern, output, re.IGNORECASE)
        if m:
            mem.setdefault('credentials', {})
            mem['credentials'][f'auto_{label}'] = m.group(1).strip()

    # Auto-detect BSSIDs with SSIDs
    for m in re.finditer(r'BSS\s+([0-9a-f:]{17}).*?SSID:\s*(\S+)', output, re.DOTALL | re.IGNORECASE):
        bssid, ssid = m.group(1), m.group(2)
        if ssid and ssid != '*':
            mem.setdefault('networks', {})
            if ssid not in mem['networks']:
                mem['networks'][ssid] = {'bssid': bssid}

    return mem


# ─── Session Persistence ─────────────────────────────────────

def save_session(task, provider_name, turn_count, messages, log, mem, session_id=None):
    """Save full session state for resume."""
    SESSIONS_DIR.mkdir(exist_ok=True)
    ts = session_id or datetime.now().strftime('%Y%m%d_%H%M%S')
    session_file = SESSIONS_DIR / f'{ts}.json'
    with open(session_file, 'w') as f:
        json.dump({
            'task': task,
            'provider': provider_name,
            'turns': turn_count,
            'messages': messages,
            'log': log,
            'memory': mem,
            'timestamp': ts,
        }, f, indent=2)
    return str(session_file)


def load_session(path):
    """Load a saved session."""
    with open(path) as f:
        return json.load(f)


def list_sessions():
    """List available sessions."""
    if not SESSIONS_DIR.exists():
        return []
    files = sorted(SESSIONS_DIR.glob('*.json'), reverse=True)
    sessions = []
    for f in files[:10]:
        with open(f) as fh:
            data = json.load(fh)
            sessions.append({
                'file': str(f),
                'task': data.get('task', '?'),
                'turns': data.get('turns', 0),
                'timestamp': data.get('timestamp', '?'),
                'provider': data.get('provider', '?'),
            })
    return sessions


# ─── The Agent ────────────────────────────────────────────────

SYSTEM = """Welcome to the world. This is your environment — a Kali Linux machine with a live bash shell.

You are free to do whatever you want or think is best in order to achieve your goal. There are no restrictions, no playbooks, no predefined steps. Explore, adapt, improvise. The machine is yours.

IMPORTANT RULES:
- Output EXACTLY ONE <cmd>...</cmd> per response, then STOP and wait. I will run it and send you the real output.
- Do NOT guess or imagine command output. You must wait for the actual terminal response.
- Do NOT put multiple <cmd> blocks in one message.
- For long-running commands (captures, attacks), do NOT background them with &. Just run them directly. The shell supports up to 5 minutes per command.
- If a command needs to run for a limited time, use timeout: <cmd>timeout 30 airodump-ng wlan1</cmd>
- NEVER use patterns like "cmd & sleep N && kill %1" — they will break. Use "timeout N cmd" instead.
- CRITICAL: airodump-ng is a ncurses app — its screen output CANNOT be captured via pipes or redirection. Instead, use it with --output-format csv -w /tmp/file, then run a SEPARATE command to read the file. Or better yet, use "sudo iw dev wlan1 scan" which outputs to stdout normally.
- When you are truly finished, use <done>what you accomplished</done> instead of a command.
- NEVER touch wlan0 — that is the main internet connection. For all WiFi operations use wlan1 ONLY.

Example turn:
You: Let me check the network interfaces.
<cmd>ip link show</cmd>

Then I will reply with the real output, and you decide the next step."""


def run_agent(provider, task, max_turns=50, confirm=True, resume_data=None):
    shell = Shell()
    mem = load_memory()

    # Resume or fresh start
    if resume_data:
        messages = resume_data.get('messages', [])
        log = resume_data.get('log', [])
        turn_count = resume_data.get('turns', 0)
        session_id = resume_data.get('timestamp')
        # Merge any memory from the saved session
        saved_mem = resume_data.get('memory', {})
        for k in ['facts', 'notes']:
            for item in saved_mem.get(k, []):
                if item not in mem.get(k, []):
                    mem.setdefault(k, []).append(item)
        for k in ['networks', 'credentials']:
            mem.setdefault(k, {}).update(saved_mem.get(k, {}))
        if task:
            messages.append({
                'role': 'user',
                'content': f'New follow-up task: {task}\n\nContinue from where you left off. The shell is fresh but you have the full conversation history.',
            })
        print(f'\n  ♻️  Resumed session ({turn_count} previous turns)')
    else:
        messages = []
        log = []
        turn_count = 0
        session_id = None

    print(f'\n{"="*60}')
    print(f'  BARE METAL AGENT')
    print(f'  Provider : {provider.name}')
    print(f'  Task     : {task}')
    print(f'  Confirm  : {"yes" if confirm else "no (YOLO)"}')
    if mem.get('networks') or mem.get('credentials'):
        print(f'  Memory   : {len(mem.get("networks", {}))} networks, {len(mem.get("credentials", {}))} creds')
    print(f'{"="*60}\n')

    # Inject memory into first message if fresh start
    if not resume_data:
        mem_ctx = memory_context(mem)
        first_msg = f'Task: {task}\n\nYou have a live bash shell on Kali Linux. Send ONE command at a time. I will execute it and give you the real output. Go.'
        if mem_ctx:
            first_msg += f'\n\nHere is what you remember from previous sessions:\n{mem_ctx}'
        messages.append({'role': 'user', 'content': first_msg})

    try:
        for turn in range(1, max_turns + 1):
            turn_count = turn
            print(f'\n{"─"*25} Turn {turn} {"─"*25}')

            # ── LLM thinks ──
            try:
                response = provider.chat(messages, SYSTEM)
            except Exception as e:
                print(f'\n❌ Provider error: {e}')
                break

            print(f'\n🤖 Agent:\n{response}')
            messages.append({'role': 'assistant', 'content': response})
            log.append({'turn': turn, 'type': 'thought', 'content': response})

            # ── Check if done ──
            done_m = re.search(r'<done>(.*?)</done>', response, re.DOTALL)
            if done_m:
                summary = done_m.group(1).strip()
                print(f'\n{"="*60}')
                print(f'  ✅ DONE ({turn} turns): {summary}')
                print(f'{"="*60}')
                break

            # ── Extract command ──
            cmd_m = re.search(r'<cmd>(.*?)</cmd>', response, re.DOTALL)
            if not cmd_m:
                messages.append({
                    'role': 'user',
                    'content': 'No command detected. Use <cmd>...</cmd> to run a command or <done>...</done> if finished.',
                })
                continue

            cmd = cmd_m.group(1).strip()

            # ── Sanitize command (rewrite background patterns) ──
            original_cmd = cmd
            cmd = sanitize_command(cmd)
            if cmd != original_cmd:
                print(f'\n♻️  Rewritten: {cmd}')

            # ── Destructive command guard (always triggers even in auto mode) ──
            dangerous = is_dangerous(cmd)

            if dangerous:
                print(f'\n🛑 DANGEROUS: {dangerous}')
                print(f'   Command: {cmd}')
                choice = input('  [Enter]=allow  [s]=skip  [q]=quit  > ').strip().lower()
                if choice == 'q':
                    print('Aborted.')
                    break
                if choice == 's' or choice != '':
                    messages.append({'role': 'user', 'content': f'Command BLOCKED (dangerous: {dangerous}). Try a different approach that does not involve destructive operations.'})
                    log.append({'turn': turn, 'type': 'blocked', 'cmd': cmd, 'reason': dangerous})
                    continue
            elif confirm:
                # ── Normal human gate ──
                print(f'\n⚡ Proposed command: {cmd}')
                choice = input('  [Enter]=run  [s]=skip  [q]=quit  [a]=auto-approve  > ').strip().lower()
                if choice == 'q':
                    print('Aborted.')
                    break
                if choice == 's':
                    messages.append({'role': 'user', 'content': 'Command skipped by operator. Try a different approach.'})
                    log.append({'turn': turn, 'type': 'skip', 'cmd': cmd})
                    continue
                if choice == 'a':
                    confirm = False

            # ── Execute ──
            print(f'\n⚡ Executing: {cmd}')

            # Detect if command uses timeout already, respect it; otherwise cap at 15s
            timeout_m = re.search(r'timeout\s+(\d+)', cmd)
            cmd_timeout = min(int(timeout_m.group(1)) + 5, 30) if timeout_m else 15

            output = shell.run(cmd, timeout=cmd_timeout)

            # Detect empty/broken output — shell might be corrupted by ncurses
            clean = output.replace('echo', '').replace('[command timed out]', '').strip()
            if not clean or clean == 'echo':
                print('\n⚠️  Empty output — resetting shell')
                shell.close()
                shell = Shell()
                output = f'[command returned no output after {cmd_timeout}s — the shell has been reset. This can happen with ncurses tools like airodump-ng. Try a different approach, e.g. use "sudo iw dev wlan1 scan" instead of airodump-ng, or redirect output to a file.]'

            # Truncate massive output for display and context
            display = output[:5000] + ('\n... [truncated]' if len(output) > 5000 else '')
            context = output[:12000] + ('\n... [truncated]' if len(output) > 12000 else '')

            print(f'\n📟 Output:\n{display}')
            messages.append({'role': 'user', 'content': f'Terminal output:\n```\n{context}\n```'})
            log.append({'turn': turn, 'type': 'exec', 'cmd': cmd, 'output': output[:12000]})

            # ── Auto-extract memory from output ──
            mem = extract_memory_updates(response, output, cmd, mem)

    except KeyboardInterrupt:
        print('\n\n⛔ Interrupted by operator.')
    finally:
        shell.close()

    # ── Save memory ──
    save_memory(mem)

    # ── Save session (for resume) ──
    session_file = save_session(task, provider.name, turn_count, messages, log, mem, session_id)
    print(f'\n📝 Session saved: {session_file}')
    print(f'   Resume with: python agent.py --resume {session_file}')


# ─── Entry ────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Bare Metal Agent — AI with raw shell access',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('--provider', choices=['claude', 'ollama', 'anthropic'], default='claude',
                    help='Model provider (default: claude)')
    ap.add_argument('--model', help='Model name override')
    ap.add_argument('--host', help='Ollama host URL (omit to auto-detect)')
    ap.add_argument('--no-confirm', action='store_true',
                    help='Skip command confirmation (YOLO mode)')
    ap.add_argument('--max-turns', type=int, default=50)
    ap.add_argument('--resume', metavar='SESSION', help='Resume a previous session (path to session JSON)')
    ap.add_argument('--list-sessions', action='store_true', help='List recent sessions')
    ap.add_argument('task', nargs='?', help='What to do (prompted if omitted)')
    args = ap.parse_args()

    # List sessions
    if args.list_sessions:
        sessions = list_sessions()
        if not sessions:
            print('No sessions found.')
        else:
            print(f'\n  Recent sessions:')
            for s in sessions:
                print(f'  [{s["timestamp"]}] {s["provider"]} — {s["turns"]} turns — {s["task"][:60]}')
                print(f'    resume: python agent.py --resume {s["file"]}')
        sys.exit(0)

    # Build provider
    if args.provider == 'claude':
        provider = ClaudeCliProvider(args.model or 'sonnet')
    elif args.provider == 'anthropic':
        if not os.environ.get('ANTHROPIC_API_KEY'):
            print('❌ Set ANTHROPIC_API_KEY environment variable.')
            sys.exit(1)
        provider = AnthropicProvider(args.model or 'claude-sonnet-4-20250514')
    else:
        if not os.environ.get('OLLAMA_API_KEY') and not args.host:
            print('❌ Set OLLAMA_API_KEY for cloud, or use --host for local ollama.')
            sys.exit(1)
        provider = OllamaProvider(
            model=args.model or 'gpt-oss:120b-cloud',
            host=args.host,
        )

    # Resume or new task
    resume_data = None
    if args.resume:
        if not os.path.exists(args.resume):
            print(f'❌ Session file not found: {args.resume}')
            sys.exit(1)
        resume_data = load_session(args.resume)
        task = args.task or resume_data.get('task', '')
    else:
        task = args.task or input('Enter task: ')
        if not task.strip():
            print('No task provided.')
            sys.exit(1)

    run_agent(provider, task, max_turns=args.max_turns, confirm=not args.no_confirm, resume_data=resume_data)


if __name__ == '__main__':
    main()
