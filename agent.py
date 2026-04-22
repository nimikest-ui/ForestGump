#!/usr/bin/env python3
"""
Bare Metal Agent — The anti-framework experiment.
No tools. No playbooks. No tiers. Just a model and a raw shell.

Usage:
  # Claude via Claude Code CLI (OAuth — uses your Pro subscription, no API key)
  python agent.py --provider claude "scan wifi networks"

  # Ollama local
    python agent.py --provider ollama --model "llama3:8b" "scan wifi networks"

    # Ollama Cloud (set OLLAMA_API_KEY from ollama.com/settings/keys)
    OLLAMA_API_KEY=your_key python agent.py --provider ollama --model "gpt-oss:120b-cloud" --host https://ollama.com "scan wifi networks"

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
import random
from datetime import datetime
from pathlib import Path

from skills import init_db as init_skills_db, skills_context, extract_skills_from_session, migrate_techniques_json

SCRIPT_DIR = Path(__file__).parent.resolve()
SESSIONS_DIR = SCRIPT_DIR / 'sessions'
MEMORY_FILE = SCRIPT_DIR / 'memory.json'
TECHNIQUES_FILE = SCRIPT_DIR / 'techniques.json'


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
    (r'\bairmon-ng\b', 'airmon-ng is forbidden — wlan1 is already in monitor mode, use airodump-ng with -w directly'),
    (r'wlan0.*mon\b', 'monitor mode on wlan0'),
    (r'\bchmod\s+777\s+/', 'chmod 777 on root paths'),
    (r'\bpasswd\b', 'changing passwords'),
    (r'\buserdel\b', 'deleting users'),
    (r'\breboot\b|\bshutdown\b|\bpoweroff\b|\binit\s+[06]\b', 'system reboot/shutdown'),
    # SSH/telnet are interactive and hang waiting for password (only block direct SSH/telnet, not sshpass which is non-interactive)
    # (r'^\s*(ssh|telnet)[\s\-]', 'SSH/telnet are interactive and cause hangs — use sshpass with commands or scripted tools like paramiko'),
    # Known problematic Bluetooth tools that hang/crash PTY without proper subprocess handling
    (r'\bsdptool\b.*\bbrowse\b|\bsdptool\b.*\brecords\b|\bsdptool\b.*\bsearch\b', 'sdptool is unstable and hangs — use hcitool info or bluetoothctl info instead'),
    (r'\brfcomm\b', 'rfcomm causes PTY hangs — use bluetoothctl connect instead'),
    (r'\bgatttool\b', 'gatttool is problematic — use bluetoothctl gatt-tools or bluepy instead'),
    (r'\bobexftp\b', 'obexftp causes PTY hangs — consider alternative tools'),
    (r'\bbluesnarfer\b', 'bluesnarfer causes PTY hangs — try other enumeration methods'),
    (r'\bl2ping\b', 'l2ping causes PTY hangs — use simple pings or connection tests'),
]


def is_dangerous(cmd):
    """Return reason string if command matches a dangerous pattern, else None."""
    # Hard safety rule: never allow any direct reference to wlan0.
    if re.search(r'\bwlan0\b', cmd, re.IGNORECASE):
        return 'wlan0 is protected and cannot be used'

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

    # Cap excessively long timeouts (35s to allow airodump-ng 25s captures)
    m = re.match(r'^(sudo\s+)?timeout\s+(\d+)\s+(.+)', flat)
    if m and int(m.group(2)) > 35:
        prefix = m.group(1) or ''
        return f'{prefix}timeout 35 {m.group(3)}'

    # Fix double timeout
    m = re.match(r'^(sudo\s+)?timeout\s+\d+\s+(sudo\s+)?timeout\s+(\d+)\s+(.+)', flat)
    if m:
        prefix = m.group(1) or m.group(2) or ''
        seconds = min(int(m.group(3)), 35)
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
        usage = {
            'input_tokens': r.usage.input_tokens,
            'output_tokens': r.usage.output_tokens,
        }
        return r.content[0].text, usage


class OllamaProvider:
    def __init__(self, model='gpt-oss:120b-cloud', host=None):
        from ollama import Client
        api_key = os.environ.get('OLLAMA_API_KEY')
        # Default to local Ollama unless host is explicitly provided
        # or cloud is implied by an API key.
        if not host:
            host = 'https://ollama.com' if api_key else 'http://localhost:11434'
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
        usage = {
            'input_tokens': r.get('prompt_eval_count', 0),
            'output_tokens': r.get('eval_count', 0),
        }
        return r['message']['content'], usage


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

        return result.stdout.strip(), None  # Claude CLI provides no token usage


class CopilotProvider:
    """GitHub Copilot CLI provider.

    Wraps `gh copilot -p` in non-interactive mode.
    Shell/write tools are denied so Copilot CLI never executes commands
    itself — ForestGump's own PTY loop stays in control.

    Auth: uses existing `gh auth` session (no API key needed).
    Install: curl -fsSL https://gh.io/copilot-install | bash
    """

    def __init__(self, model='claude-sonnet-4.5'):
        self.model = model
        self.name = f'copilot/{model}'

    def chat(self, messages, system):
        # Build a single prompt from conversation history (same pattern as ClaudeCliProvider)
        prompt_parts = [f'[System instructions]\n{system}']
        for msg in messages:
            role = msg['role']
            content = msg['content']
            if role == 'user':
                prompt_parts.append(content)
            elif role == 'assistant':
                prompt_parts.append(f'[Previous response]\n{content}')

        full_prompt = '\n\n'.join(prompt_parts)
        # Remove null bytes and other dangerous chars from prompt before passing to subprocess
        full_prompt = full_prompt.replace('\x00', '').replace('\r\n', '\n')

        cmd = [
            'gh', 'copilot',
            '--model', self.model,
            '--output-format', 'text',
            '--no-custom-instructions',  # ForestGump supplies its own system prompt above
            '--deny-tool=shell',         # ForestGump's PTY executes commands, not Copilot CLI
            '--deny-tool=write',         # Same — no file writes by Copilot CLI itself
            '-p', full_prompt,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,  # Get bytes first to handle encoding issues gracefully
                timeout=180,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f'Copilot CLI timeout (>180s)') from e
        except Exception as e:
            raise RuntimeError(f'Copilot CLI subprocess error: {e}') from e

        if result.returncode != 0:
            # Decode stderr/stdout carefully, replacing bad bytes
            err_text = result.stderr.decode('utf-8', errors='replace').strip() if result.stderr else ''
            out_text = result.stdout.decode('utf-8', errors='replace').strip() if result.stdout else ''
            err_msg = (err_text or out_text or '(no error message)').replace('\x00', '')
            raise RuntimeError(f'Copilot CLI error: {err_msg}')

        # Decode output, aggressively removing null bytes and other problematic chars
        try:
            output = result.stdout.decode('utf-8', errors='replace').strip()
        except Exception as e:
            # Fallback: use latin-1 which accepts all byte values
            output = result.stdout.decode('latin-1', errors='replace').strip()

        # Remove null bytes and control chars that cause issues downstream
        output = ''.join(c for c in output if c not in '\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f')
        return output, None  # Copilot CLI provides no token usage


# ─── Memory ───────────────────────────────────────────────────

def load_memory():
    """Load persistent memory (things learned across sessions)."""
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f:
            data = json.load(f)
        # Normalize networks: list of {ssid, bssid, ...} → dict keyed by ssid
        if isinstance(data.get('networks'), list):
            data['networks'] = {
                n['ssid']: {k: v for k, v in n.items() if k != 'ssid'}
                for n in data['networks'] if n.get('ssid')
            }
        # Normalize credentials: list → dict keyed by ssid/target
        if isinstance(data.get('credentials'), list):
            data['credentials'] = {
                c.get('ssid', c.get('target', f'cred_{i}')): {k: v for k, v in c.items() if k not in ('ssid', 'target')}
                for i, c in enumerate(data['credentials'])
            }
        return data
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


# ─── Technique Memory ─────────────────────────────────────────

def load_techniques():
    """Load discovered techniques from persistent storage."""
    if TECHNIQUES_FILE.exists():
        with open(TECHNIQUES_FILE) as f:
            data = json.load(f)
        return data.get('techniques', {})
    return {}


def techniques_context(techniques, task=''):
    """Format techniques into a string for the system prompt.

    Ranks by relevance to current task + efficiency score.
    Score = (use_count * 100) - best_session_turns
    Fewer turns to solve = higher priority.
    """
    if not techniques:
        return ''

    task_lower = task.lower()
    task_tags = set()
    if any(w in task_lower for w in ['ssh', 'bandit', 'overthewire', 'port 2220']):
        task_tags.update(['ssh', 'bandit', 'automation'])
    if any(w in task_lower for w in ['wifi', 'wlan', 'wpa', 'handshake']):
        task_tags.update(['wifi', 'wireless'])
    if any(w in task_lower for w in ['decode', 'hex', 'base64', 'gzip', 'rot13']):
        task_tags.update(['decode', 'forensics'])

    def relevance(item):
        tech_tags = set(item[1].get('tags', []))
        overlap = len(tech_tags & task_tags) * 100
        # Fewer turns = higher efficiency bonus (max 50 pts at 0 turns)
        efficiency = max(0, 50 - item[1].get('best_session_turns', 50))
        usage = item[1].get('use_count', 1) * 10
        return overlap + efficiency + usage

    ranked = sorted(techniques.items(), key=relevance, reverse=True)

    parts = ['PROVEN TECHNIQUES (most relevant + efficient first):']
    for key, tech in ranked[:5]:
        turns = tech.get('best_session_turns', '?')
        uses = tech.get('use_count', 1)
        parts.append(f'\n✓ {tech.get("name", key)} [used {uses}x, best={turns} turns]:')
        if 'problem' in tech:
            parts.append(f'  Problem: {tech["problem"]}')
        if 'solution' in tech:
            parts.append(f'  Solution: {tech["solution"]}')
        if 'template' in tech:
            parts.append(f'  Template: {tech["template"]}')
        if tech.get('tags'):
            parts.append(f'  Tags: {", ".join(tech["tags"])}')
    return '\n'.join(parts)


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


def command_base(cmd):
    """Extract command base name without wrappers like sudo/timeout."""
    parts = cmd.strip().split()
    i = 0
    if i < len(parts) and parts[i] in ('sudo', 'su'):
        i += 1
    if i + 1 < len(parts) and parts[i] == 'timeout' and parts[i + 1].isdigit():
        i += 2
    if i < len(parts) and parts[i] == 'sudo':
        i += 1
    return parts[i] if i < len(parts) else ''


def is_output_success(output):
    """Heuristic success detector for terminal command output."""
    if not output:
        return False
    out = output.lower()
    fail_markers = [
        'command not found',
        'no such file',
        'permission denied',
        'failed',
        'error',
        'timed out',
        'not found',
        'traceback',
        'operation not permitted',
        'invalid',
    ]
    success_markers = [
        'completed',
        'success',
        'connected',
        'written',
        'captured',
        'found',
        'listening',
    ]

    if any(m in out for m in fail_markers):
        return False
    return any(m in out for m in success_markers) or len(out.strip()) > 20


def is_command_failure(output, cmd_base=''):
    """Detect whether a command truly failed.

    Filters heredoc echo lines (bash '> ' prefix) before evaluation so that
    expect scripts written as heredocs don't produce false progress signals.
    """
    out = (output or '').lower()
    if not out:
        return True

    # Filter heredoc echo lines — bash prints '> ' before each heredoc input line.
    # These lines contain the script text (e.g. '> expect "password:"') but are
    # NOT real output. Also filter out the heredoc opening lines (e.g., 'expect << EOF'
    # or 'cat > file << EOF') which are command echoes, not real output.
    lines = out.splitlines()
    real_lines = []
    for l in lines:
        if not l.strip():
            continue  # skip empty lines
        if re.match(r'^>\s', l):
            continue  # skip heredoc echo lines
        if re.match(r'^(cat|echo|expect|sh|bash|python|perl|ruby|node)\s+.*<<', l):
            continue  # skip heredoc opening declarations
        real_lines.append(l)

    if not real_lines:
        return True   # all output was heredoc echo — nothing actually ran
    eval_out = '\n'.join(real_lines)

    progress_markers = [
        'spawn ',          # expect spawned a process (real expect output, not echo)
        'password:',
        'connecting to',
        'connection established',
        'connected successfully',
        'authentication failed',
        'userauth',
        'permission denied, please try again',
        'remote host identification has changed',
        'are you sure you want to continue connecting',
    ]
    # 'expect ' intentionally removed: it matched heredoc echo lines like
    # '> expect "password:"' and caused false progress detection.

    if any(marker in eval_out for marker in progress_markers):
        # This command reached a live prompt or network interaction and should not be treated
        # as a hard failure unless it contains an explicit fatal error.
        if 'command not found' in eval_out or 'no such file' in eval_out or 'unknown command' in eval_out:
            return True
        if 'invalid' in eval_out and 'timeout' not in eval_out:
            return True
        if 'failed' in eval_out and 'permission denied' not in eval_out and 'authentication failed' not in eval_out:
            return True
        return False

    fail_markers = [
        'command not found',
        'no such file',
        'permission denied',
        'authentication failed',
        'timed out',
        'error',
        'failed',
        'not found',
        'traceback',
        'operation not permitted',
        'invalid',
    ]
    return any(marker in eval_out for marker in fail_markers)


def build_round_review(turn, log, mem, task):
    """Build a ranked success/failure review and retrieval hints for next moves."""
    exec_events = [e for e in log if e.get('type') == 'exec']
    blocked_events = [e for e in log if e.get('type') in ('blocked', 'loop_break')]

    recent = exec_events[-12:]
    if not recent and not blocked_events:
        return ''

    success_rank = {}
    failure_rank = {}
    total_success = 0
    total_fail = 0

    for event in recent:
        cmd = event.get('cmd', '')
        output = event.get('output', '')
        base = command_base(cmd)
        if not base:
            continue
        if is_command_failure(output, base):
            total_fail += 1
            failure_rank[base] = failure_rank.get(base, 0) + 1
        else:
            total_success += 1
            success_rank[base] = success_rank.get(base, 0) + 1

    for event in blocked_events[-6:]:
        base = command_base(event.get('cmd', ''))
        if base:
            failure_rank[base] = failure_rank.get(base, 0) + 1
            total_fail += 1

    top_success = sorted(success_rank.items(), key=lambda x: x[1], reverse=True)[:3]
    top_fail = sorted(failure_rank.items(), key=lambda x: x[1], reverse=True)[:3]

    focus_terms = [task]
    focus_terms.extend(cmd for cmd, _ in top_fail)
    focus_query = ' '.join(t for t in focus_terms if t).strip()
    dynamic_skills = skills_context(focus_query, limit=5)
    mem_ctx = memory_context(mem)

    lines = [
        f'ROUND REVIEW @ turn {turn}',
        f'- Successes in recent window: {total_success}',
        f'- Failures in recent window: {total_fail}',
    ]
    if top_success:
        lines.append('- Ranked successes: ' + ', '.join(f'{cmd} ({count})' for cmd, count in top_success))
    if top_fail:
        lines.append('- Ranked failures: ' + ', '.join(f'{cmd} ({count})' for cmd, count in top_fail))

    if mem_ctx:
        lines.append('\nUse this memory to choose your next approach (prefer known-good methods):')
        lines.append(mem_ctx)

    if dynamic_skills:
        lines.append('\nUse these retrieved skills that match current failures/task:')
        lines.append(dynamic_skills)

    lines.append('\nNow pick ONE command that addresses the top-ranked failure using memory/skills evidence.')
    return '\n'.join(lines)


def summarize_resume_session(resume_data, task, mem=None):
    """Build a compact, safe summary for resuming into a fresh shell."""
    prior_task = resume_data.get('task', '(unknown)')
    previous_turns = resume_data.get('turns', 0)
    log = resume_data.get('log', []) or []
    last_execs = [e for e in log if e.get('type') == 'exec'][-3:]

    lines = [
        'PREVIOUS SESSION SUMMARY:',
        f'- Prior task: {prior_task}',
        f'- Turns completed: {previous_turns}',
        '- Important: the shell is fresh. Do not assume any previous shell state, temporary files, or environment variables still exist.',
        '- Use the prior session as reference only and continue with one new command.',
    ]

    if task and task != prior_task:
        lines.append(f'- New follow-up task: {task}')

    if last_execs:
        lines.append('\nRecent executed commands:')
        for event in last_execs:
            cmd = event.get('cmd', '<unknown>')
            out_lines = (event.get('output') or '').strip().splitlines()
            out_excerpt = out_lines[0] if out_lines else '[no output]'
            if len(out_excerpt) > 120:
                out_excerpt = out_excerpt[:117] + '...'
            lines.append(f'  - {cmd}')
            lines.append(f'    Output: {out_excerpt}')

    if mem:
        mem_ctx = memory_context(mem)
        if mem_ctx:
            lines.append('\nKnown memory from previous sessions:')
            lines.append(mem_ctx)

    lines.append('\nNow continue from this fresh shell, using the above as reference. Do not repeat old commands unless they are still clearly relevant.')
    return '\n'.join(lines)


def build_resume_message(resume_data, task, mem=None):
    """Create the user message that resumes a previous session."""
    return summarize_resume_session(resume_data, task, mem)


# ─── Session Persistence ─────────────────────────────────────

def save_session(task, provider_name, turn_count, messages, log, mem, token_totals=None, session_id=None):
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
            'token_totals': token_totals or {},
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


# ─── Bluetooth Support ────────────────────────────────────────

def get_bluetooth_adapters():
    """Detect Bluetooth adapters on the system."""
    import pathlib as _p
    adapters = []
    bt_dir = _p.Path('/sys/class/bluetooth')
    if bt_dir.exists():
        for device_path in bt_dir.iterdir():
            if device_path.is_dir():
                adapters.append(device_path.name)
    return adapters


def has_bluetooth_hardware():
    """Check if Bluetooth hardware is available."""
    return len(get_bluetooth_adapters()) > 0


# ─── The Agent ────────────────────────────────────────────────

SYSTEM = """Welcome to the world. This is your environment — a Kali Linux machine with a live bash shell.

You are free to do whatever you want or think is best in order to achieve your goal. There are no restrictions, no playbooks, no predefined steps. Explore, adapt, improvise. The machine is yours.

IMPORTANT RULES:
- Output EXACTLY ONE <cmd>...</cmd> per response, then STOP and wait. I will run it and send you the real output.
- Do NOT guess or imagine command output. You must wait for the actual terminal response.
- Do NOT put multiple <cmd> blocks in one message.
- Prefix commands with sudo when they need root access.
- For long-running commands (captures, attacks), do NOT background them with &. Just run them directly. The shell supports up to 5 minutes per command.
- If a command needs to run for a limited time, use timeout: <cmd>sudo timeout 25 airodump-ng --output-format csv -w /tmp/scan wlan1</cmd>
- NEVER use patterns like "cmd & sleep N && kill %1" — they will break. Use "timeout N cmd" instead.
- CRITICAL: wlan1 is ALREADY in monitor mode. Do NOT run airmon-ng start/stop/check — it is not needed and will hang. Using airmon-ng in any form is FORBIDDEN.
- CRITICAL: wlan1 is the WiFi adapter. Its name is always "wlan1" — never "wlan1mon".
- CRITICAL: airodump-ng screen output CANNOT be captured. ALWAYS write to file: <cmd>sudo timeout 25 airodump-ng --output-format csv -w /tmp/scan wlan1</cmd> then read with <cmd>cat /tmp/scan-01.csv</cmd>
- CRITICAL: "iw dev wlan1 scan" does NOT work in monitor mode. Never use it. Use airodump-ng -w only.
- BLUETOOTH: Use SAFE tools only: **hcitool** (scan, info, cc, con), **bluetoothctl** (scan on, info, power on, connect), **hciconfig** (adapters). Scan for devices: sudo hcitool scan. Get info: hcitool info [MAC]. Connect: bluetoothctl connect [MAC].
- DO NOT use: sdptool (hangs), rfcomm (hangs), gatttool (broken), obexftp (hangs), bluesnarfer (hangs), l2ping (hangs). If enumeration needed, use bluetoothctl info [MAC] to check services. Start adapter with: sudo hciconfig hci0 up
- If a command fails, do NOT retry the same command. Try a completely different approach.
- When you are truly finished, use <done>what you accomplished</done> instead of a command.
- NEVER touch wlan0 — that is the main internet connection. For all WiFi operations use wlan1 ONLY.

Example turn:
You: Let me check the network interfaces.
<cmd>ip link show</cmd>

Then I will reply with the real output, and you decide the next step."""


def run_agent(provider, task, max_turns=50, confirm=True, resume_data=None):
    shell = Shell()
    mem = load_memory()
    techniques = load_techniques()

    # Initialize skills DB and migrate techniques.json on first run
    init_skills_db()
    migrate_techniques_json(SCRIPT_DIR / 'techniques.json')

    # Build system prompt with skills from experience (search by task keywords)
    skill_str = skills_context(task, limit=5)
    full_system = SYSTEM + ('\n\n' + skill_str if skill_str else '')

    # Fall back to static techniques if no skills yet
    if not skill_str:
        techniques_str = techniques_context(techniques, task or '')
        full_system = SYSTEM + ('\n\n' + techniques_str if techniques_str else '')

    # Resume or fresh start
    if resume_data:
        log = resume_data.get('log', [])
        turn_count = resume_data.get('turns', 0)
        session_id = resume_data.get('timestamp')
        saved_mem = resume_data.get('memory', {})
        for k in ['facts', 'notes']:
            for item in saved_mem.get(k, []):
                if item not in mem.get(k, []):
                    mem.setdefault(k, []).append(item)
        for k in ['networks', 'credentials']:
            mem.setdefault(k, {}).update(saved_mem.get(k, {}))

        resume_task = task or resume_data.get('task', '')
        messages = [{'role': 'user', 'content': build_resume_message(resume_data, resume_task, mem)}]
        if task and task != resume_data.get('task', ''):
            messages.append({'role': 'user', 'content': f'New follow-up task: {task}'})
        print(f'\n  ♻️  Resumed session ({turn_count} previous turns, fresh shell)')
    else:
        messages = []
        log = []
        turn_count = 0
        session_id = None

    # Trigger periodic self-review every random 3-6 turns.
    next_review_turn = random.randint(3, 6)

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
        # Initialize token tracking
        token_totals = {'input_tokens': 0, 'output_tokens': 0}

        for turn in range(1, max_turns + 1):
            turn_count = turn
            print(f'\n{"─"*25} Turn {turn} {"─"*25}')

            # ── Between-turn steer check ──
            # Non-blocking: picks up anything the user typed while last command ran.
            if sys.stdin.isatty():
                import select as _select
                rlist, _, _ = _select.select([sys.stdin], [], [], 0)
                if rlist:
                    steer_line = sys.stdin.readline().strip()
                    if steer_line:
                        print(f'\n💬 Steering injected: {steer_line}')
                        messages.append({'role': 'user', 'content': steer_line})
                        log.append({'turn': turn, 'type': 'steer', 'content': steer_line, 'ts': time.time()})

            if turn >= next_review_turn:
                review = build_round_review(turn, log, mem, task)
                if review:
                    print('\n📊 Periodic review injected (ranked success/failure + memory/skills retrieval)')
                    messages.append({'role': 'user', 'content': review})
                next_review_turn = turn + random.randint(3, 6)

            # ── LLM thinks ──
            t_llm_start = time.time()
            try:
                response, usage = provider.chat(messages, full_system)
            except Exception as e:
                print(f'\n❌ Provider error: {e}')
                break
            t_thought = time.time()
            llm_inference = round(t_thought - t_llm_start, 1)

            # Accumulate token counts
            if usage:
                token_totals['input_tokens'] += usage.get('input_tokens', 0)
                token_totals['output_tokens'] += usage.get('output_tokens', 0)

            # Display agent response with token info
            tok_str = f" | {usage['input_tokens']}in/{usage['output_tokens']}out tok" if usage else ''
            print(f'\n🤖 Agent: [llm={llm_inference}s{tok_str}]\n{response}')
            messages.append({'role': 'assistant', 'content': response})
            log.append({'turn': turn, 'type': 'thought', 'content': response, 'tokens': usage, 'ts': t_thought, 'llm_s': llm_inference})

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

            # ── Repeat-command loop-breaker ──
            # Count consecutive failures for this specific tool at the tail of the log.
            # A success or a different command breaks the streak — prevents false positives
            # when a tool succeeds between failures.
            cmd_base = command_base(cmd)
            consecutive_failures = 0
            for entry in reversed(log):
                if entry.get('type') != 'exec' or not entry.get('cmd', '').strip():
                    continue
                entry_base = command_base(entry['cmd'])
                if entry_base != cmd_base:
                    break  # different command: streak ends
                if is_command_failure(entry.get('output', ''), entry_base):
                    consecutive_failures += 1
                else:
                    break  # success: streak resets to 0

            loop_threshold = 4 if cmd_base in ('aireplay-ng', 'aircrack-ng') else 3
            if cmd_base and consecutive_failures >= loop_threshold:
                print(f'\n⚠️  Loop detected: `{cmd_base}` failed {consecutive_failures}× in a row, injecting hard redirect')
                messages.append({
                    'role': 'user',
                    'content': (
                        f'STOP. `{cmd_base}` has failed {consecutive_failures} times consecutively. '
                        f'That tool is not working. Do NOT use `{cmd_base}` again. Try a completely different approach.'
                    ),
                })
                log.append({'turn': turn, 'type': 'loop_break', 'cmd': cmd, 'ts': time.time()})
                continue

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
                if not confirm:
                    # In YOLO mode, dangerous commands are auto-blocked (never auto-allowed)
                    print('  [auto-blocked in --no-confirm mode]')
                    messages.append({'role': 'user', 'content': f'Command BLOCKED (dangerous: {dangerous}). Try a different approach that does not involve destructive operations.'})
                    log.append({'turn': turn, 'type': 'blocked', 'cmd': cmd, 'reason': dangerous, 'ts': time.time()})
                    continue
                choice = input('  [Enter]=allow  [s]=skip  [t]=steer  [q]=quit  > ').strip().lower()
                if choice == 'q':
                    print('Aborted.')
                    break
                if choice == 't':
                    steer_line = input('  💬 Steer message: ').strip()
                    if steer_line:
                        messages.append({'role': 'user', 'content': steer_line})
                        log.append({'turn': turn, 'type': 'steer', 'content': steer_line, 'ts': time.time()})
                    continue  # re-run LLM with steer message
                if choice == 's' or choice != '':
                    messages.append({'role': 'user', 'content': f'Command BLOCKED (dangerous: {dangerous}). Try a different approach that does not involve destructive operations.'})
                    log.append({'turn': turn, 'type': 'blocked', 'cmd': cmd, 'reason': dangerous, 'ts': time.time()})
                    continue
            elif confirm:
                # ── Normal human gate ──
                print(f'\n⚡ Proposed command: {cmd}')
                choice = input('  [Enter]=run  [s]=skip  [t]=steer  [q]=quit  [a]=auto-approve  > ').strip().lower()
                if choice == 'q':
                    print('Aborted.')
                    break
                if choice == 's':
                    messages.append({'role': 'user', 'content': 'Command skipped by operator. Try a different approach.'})
                    log.append({'turn': turn, 'type': 'skip', 'cmd': cmd, 'ts': time.time()})
                    continue
                if choice == 't':
                    steer_line = input('  💬 Steer message: ').strip()
                    if steer_line:
                        messages.append({'role': 'user', 'content': steer_line})
                        log.append({'turn': turn, 'type': 'steer', 'content': steer_line, 'ts': time.time()})
                    continue  # re-run LLM with steer message before executing any command
                if choice == 'a':
                    confirm = False

            # ── wlan1 liveness check before wireless tools ──
            if re.search(r'\b(airodump-ng|aireplay-ng|aircrack-ng)\b', cmd):
                import pathlib as _pl
                wlan1_ok = _pl.Path('/sys/class/net/wlan1').exists()
                if not wlan1_ok:
                    print('\n⚠️  wlan1 interface not found — check USB adapter')
                    output = '[wlan1 interface missing. The USB WiFi adapter may have crashed or been unplugged. Run: sudo iw dev; and re-insert the adapter if needed.]'
                    t_exec_start = t_exec_end = time.time()
                    elapsed = 0.0
                    display = output
                    context = output
                    print(f'\n📟 Output: [exec=0s]\n{display}')
                    messages.append({'role': 'user', 'content': f'Terminal output:\n```\n{context}\n```'})
                    log.append({'turn': turn, 'type': 'exec', 'cmd': cmd, 'output': output, 'ts': time.time(), 'exec_s': 0.0})
                    continue

            # ── airodump-ng special handling ──
            # airodump-ng is a curses app — it never writes to stdout.
            # Ensure: (1) /tmp output path, (2) timeout wrapper, (3) file read directly via Python after.
            airodump_csv_path = None
            airodump_cap_only = False
            is_airodump = bool(re.search(r'\bairodump-ng\b', cmd))
            if is_airodump:
                # Extract -w path if present; default to /tmp/agent_scan
                w_m = re.search(r'-w\s+(\S+)', cmd)
                if w_m:
                    raw_path = re.sub(r'-0\d\.csv$', '', w_m.group(1))
                    # Force /tmp prefix so the file ends up in a known location
                    stem = os.path.basename(raw_path)
                    airodump_csv_path = f'/tmp/{stem}'
                    # Rewrite -w in the command to use absolute /tmp path
                    cmd = re.sub(r'-w\s+\S+', f'-w {airodump_csv_path}', cmd)
                else:
                    airodump_csv_path = '/tmp/agent_scan'
                    cmd = cmd.rstrip() + f' -w {airodump_csv_path}'
                # Ensure timeout wrapper — use 20s capture if not set
                if not re.search(r'\btimeout\s+\d+', cmd):
                    inner = re.sub(r'^sudo\s+', '', cmd)
                    cmd = f'sudo timeout 20 {inner}'
                    print(f'\n⏱️  airodump-ng: auto-wrapped → {cmd}')
                # Remove invalid channel flags (airodump-ng doesn't accept -c 0 or --channel 0)
                cmd = re.sub(r'\s+(?:-c|--channel)\s+0\b', '', cmd)
                # Detect cap-only mode (no CSV will be written)
                if re.search(r'--output-format\s+cap\b', cmd) and not re.search(r'--output-format.*csv', cmd):
                    airodump_cap_only = True
                # Ensure wlan1 is last arg (model sometimes omits it)
                if not re.search(r'\bwlan\d\b', cmd):
                    cmd = cmd.rstrip() + ' wlan1'
                    print(f'\n🔧 Auto-appended wlan1: {cmd}')

            # ── aireplay-ng special handling ──
            is_aireplay = bool(re.search(r'\baireplay-ng\b', cmd))

            # ── nmap special handling (scanner tool that hangs PTY) ──
            is_nmap = bool(re.search(r'\bnmap\b', cmd))
            if is_nmap:
                if not re.search(r'\btimeout\s+\d+', cmd):
                    inner = re.sub(r'^sudo\s+', '', cmd)
                    cmd = f'sudo timeout 30 {inner}'
                    print(f'\n⏱️  nmap: auto-wrapped with timeout → {cmd}')

            # ── Bluetooth-related command detection ──
            # Detect safe Bluetooth tools that work in subprocess
            is_bluetooth = bool(re.search(r'\b(hcitool|bluetoothctl|hciconfig|hcidump|bluelog|bluerange|crackle)\b', cmd))
            if is_bluetooth:
                adapters = get_bluetooth_adapters()
                if not adapters:
                    print(f'\n⚠️  No Bluetooth adapters found in /sys/class/bluetooth/')
                else:
                    print(f'\n📡 Bluetooth adapter online: {adapters[0]}')

            # ── Execute ──
            print(f'\n⚡ Executing: {cmd}')

            if is_aireplay:
                # aireplay-ng also hangs PTY (raw sockets + curses) — run via subprocess
                timeout_m = re.search(r'timeout\s+(\d+)', cmd)
                cap_s = int(timeout_m.group(1)) if timeout_m else 15
                t_exec_start = time.time()
                try:
                    result = subprocess.run(
                        cmd, shell=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        timeout=cap_s + 8,
                        env={**os.environ, 'TERM': 'xterm'},
                    )
                    output = result.stdout.decode('utf-8', errors='replace').strip() or '[aireplay-ng ran with no output]'
                except subprocess.TimeoutExpired:
                    output = f'[aireplay-ng timed out after {cap_s}s]'
                t_exec_end = time.time()
                elapsed = round(t_exec_end - t_exec_start, 1)
            elif is_nmap:
                # nmap hangs PTY when running network scans — run via subprocess
                timeout_m = re.search(r'timeout\s+(\d+)', cmd)
                scan_timeout = int(timeout_m.group(1)) if timeout_m else 30
                t_exec_start = time.time()
                try:
                    result = subprocess.run(
                        cmd, shell=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        timeout=scan_timeout + 8,
                        env={**os.environ, 'TERM': 'xterm'},
                    )
                    output = result.stdout.decode('utf-8', errors='replace').strip()
                    if not output:
                        output = '[nmap ran with no output — target may not be reachable]'
                except subprocess.TimeoutExpired:
                    output = f'[nmap timed out after {scan_timeout}s — scan may still be running]'
                except Exception as e:
                    output = f'[nmap error: {str(e)}]'
                t_exec_end = time.time()
                elapsed = round(t_exec_end - t_exec_start, 1)
            elif is_bluetooth:
                # Bluetooth tools (hcitool, bluetoothctl, hciconfig, hcidump, bluelog, crackle)
                # Run via subprocess to avoid PTY hangs that occur with interactive Bluetooth tools
                timeout_m = re.search(r'timeout\s+(\d+)', cmd)
                bt_timeout = int(timeout_m.group(1)) if timeout_m else 20
                t_exec_start = time.time()
                try:
                    result = subprocess.run(
                        cmd, shell=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        timeout=bt_timeout + 5,
                        env={**os.environ, 'TERM': 'xterm'},
                    )
                    output = result.stdout.decode('utf-8', errors='replace').strip()
                    if not output:
                        output = '[Bluetooth command completed with no output]'
                except subprocess.TimeoutExpired:
                    output = f'[Bluetooth command timed out after {bt_timeout}s — device may be slow or unreachable]'
                except Exception as e:
                    output = f'[Bluetooth command error: {str(e)}]'
                t_exec_end = time.time()
                elapsed = round(t_exec_end - t_exec_start, 1)
            elif is_airodump:
                # Run airodump-ng via subprocess, NOT the PTY.
                # PTY uses TERM=dumb which causes airodump-ng to exit immediately.
                timeout_m = re.search(r'timeout\s+(\d+)', cmd)
                cap_s = int(timeout_m.group(1)) if timeout_m else 20
                t_exec_start = time.time()
                try:
                    subprocess.run(
                        cmd, shell=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=cap_s + 8,
                        env={**os.environ, 'TERM': 'xterm'},
                    )
                except subprocess.TimeoutExpired:
                    pass
                t_exec_end = time.time()
                elapsed = round(t_exec_end - t_exec_start, 1)
                output = ''  # populated below
            else:
                # Detect if command uses timeout already, respect it; otherwise cap at 15s
                timeout_m = re.search(r'timeout\s+(\d+)', cmd)
                cmd_timeout = min(int(timeout_m.group(1)) + 5, 30) if timeout_m else 15
                t_exec_start = time.time()
                output = shell.run(cmd, timeout=cmd_timeout)
                t_exec_end = time.time()
                elapsed = round(t_exec_end - t_exec_start, 1)

            # ── Post-run: auto-read airodump output (direct Python read) ──
            if is_airodump:
                import pathlib
                if airodump_csv_path:
                    if airodump_cap_only:
                        # Cap-only mode: just report file size
                        cap_file = f'{airodump_csv_path}-01.cap'
                        p = pathlib.Path(cap_file)
                        if p.exists() and p.stat().st_size > 100:
                            output = f'[airodump-ng cap capture complete: {cap_file} ({p.stat().st_size} bytes). Use aircrack-ng to analyse.]'
                            print(f'\n📦 Cap written: {cap_file} ({p.stat().st_size}B)')
                        else:
                            output = f'[airodump-ng ran for {elapsed}s but no cap at {cap_file}. No handshake captured yet — try deauth with aireplay-ng first.]'
                    else:
                        csv_file = f'{airodump_csv_path}-01.csv'
                        p = pathlib.Path(csv_file)
                        if p.exists() and p.stat().st_size > 50:
                            print(f'\n📄 Auto-read CSV: {csv_file}')
                            output = p.read_text(errors='replace').strip()
                        else:
                            output = f'[airodump-ng ran for {elapsed}s but no CSV at {csv_file}. Networks may be out of range, or wlan1 is not in monitor mode.]'
                else:
                    output = f'[airodump-ng ran for {elapsed}s — no -w path specified, cannot read output]'

            # Detect empty/broken output — shell might be corrupted by ncurses
            elif not is_airodump and not is_aireplay and not is_bluetooth and not is_nmap:
                clean = output.replace('echo', '').replace('[command timed out]', '').strip()
                if not clean or clean == 'echo':
                    print('\n⚠️  Empty output — resetting shell')
                    shell.close()
                    shell = Shell()
                    output = f'[command returned no output after {cmd_timeout}s — the shell has been reset.]'

            # Truncate massive output for display and context
            display = output[:5000] + ('\n... [truncated]' if len(output) > 5000 else '')
            context = output[:12000] + ('\n... [truncated]' if len(output) > 12000 else '')

            print(f'\n📟 Output: [exec={elapsed}s]\n{display}')
            messages.append({'role': 'user', 'content': f'Terminal output:\n```\n{context}\n```'})
            log.append({'turn': turn, 'type': 'exec', 'cmd': cmd, 'output': output[:12000], 'ts': t_exec_start, 'exec_s': elapsed})

            # ── Auto-extract memory from output ──
            mem = extract_memory_updates(response, output, cmd, mem)

    except KeyboardInterrupt:
        print('\n\n⛔ Interrupted by operator.')
    finally:
        shell.close()

    # ── Save memory ──
    save_memory(mem)

    # ── Extract skills from successful session ──
    outcome = 'success' if turn_count > 0 else 'abandoned'
    extract_skills_from_session(messages, mem, session_id, provider, outcome=outcome)

    # ── Save session (for resume) ──
    session_file = save_session(task, provider.name, turn_count, messages, log, mem, token_totals, session_id)
    print(f'\n📝 Session saved: {session_file}')
    print(f'   Resume with: python agent.py --resume {session_file}')
    # Auto-extract learnings — runs silently after every session
    try:
        from extract_learnings import learn_from_session
        learn_from_session(session_file)
    except Exception:
        pass  # Never break agent execution due to learning errors


# ─── Entry ────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Bare Metal Agent — AI with raw shell access',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('--provider', choices=['claude', 'ollama', 'anthropic', 'copilot'], default='claude',
                    help='Model provider (default: claude)')
    ap.add_argument('--model', help='Model name override')
    ap.add_argument('--host', help='Ollama host URL (default: http://localhost:11434)')
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
    elif args.provider == 'copilot':
        provider = CopilotProvider(args.model or 'claude-sonnet-4.5')
    else:
        # Prefer local Ollama by default. Cloud is used if host is explicitly
        # set to ollama.com (or if host omitted but OLLAMA_API_KEY is present).
        default_ollama_model = 'gpt-oss:120b-cloud' if os.environ.get('OLLAMA_API_KEY') else 'llama3.2:latest'
        provider = OllamaProvider(
            model=args.model or default_ollama_model,
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
