# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview: Bare Metal Agent (Forest Gump)

**Bare Metal Agent** is a minimalist AI-powered pentesting tool with direct shell access. It trades frameworks and abstractions for raw capability: the model sees real shell output, executes real commands, and learns from successful techniques.

### Philosophy

- **No tools layer** — commands are generated directly, not looked up from a database
- **No playbooks** — each task starts fresh (learning comes from persistent memory, not pre-built scripts)
- **Raw shell + LLM** — the only abstractions are:
  1. A persistent PTY shell (for interactive tools like `airodump-ng`, `aireplay-ng`, `nmap`)
  2. Safety guards (block dangerous patterns; sanitize background processes and timeouts)
  3. LLM providers (pluggable: Claude CLI, Anthropic API, Ollama local/cloud)
  4. Memory persistence (facts, networks, credentials, discovered techniques)

## Architecture

### Core Components

**`agent.py`** (1007 lines) — The main loop
- **Shell class**: Pseudo-terminal wrapper using `pty.openpty()` with sentinel-based output capture
  - Handles interactive tools that hang or produce curses output
  - Non-blocking reads with select polling
  - Automatic Ctrl+C + recovery on timeout
- **Providers** (`AnthropicProvider`, `OllamaProvider`, `ClaudeCliProvider`)
  - Each has `.chat(messages, system) → text` interface
  - Claude CLI uses subprocess + OAuth (no API key)
  - Ollama supports local (http://localhost:11434) and cloud (ollama.com with API key)
  - Anthropic uses direct API calls
- **Safety guards** (`is_dangerous()`, `sanitize_command()`)
  - Blocks destructive patterns: `rm -rf`, `dd`, filesystem format, service kills, etc.
  - Blocks interactive hangs: bare `ssh`, `telnet` (not `sshpass`)
  - Blocks broken Bluetooth tools: `sdptool browse`, `rfcomm`, `gatttool`, `obexftp`, `bluesnarfer`, `l2ping`
  - Hard rule: `wlan0` protected; `airmon-ng` forbidden (use `airodump-ng` on already-monitored `wlan1`)
  - Rewrites background process patterns: `cmd & ; sleep N && kill → timeout N cmd`
  - Caps timeout durations (max 35s to allow `airodump-ng` 25s captures)
- **Special command handling**
  - `airodump-ng` → subprocess (TERM=xterm, not dumb PTY which exits immediately); auto-reads CSV/cap output
  - `aireplay-ng` → subprocess (raw sockets + curses hang PTY)
  - `nmap` → subprocess (network scans hang PTY without this)
  - Bluetooth tools (`hcitool`, `bluetoothctl`, `hciconfig`, etc.) → subprocess, checks `/sys/class/bluetooth/` for adapters
- **run_agent()** — Main loop (up to 50 turns by default)
  1. Load persistent memory + techniques
  2. Build system prompt (safety rules, memory context, available shell)
  3. Call LLM with conversation history
  4. Parse command from response (regex: backticks or `<cmd>...</cmd>`)
  5. Confirm with user (unless `--no-confirm`)
  6. Execute and capture output (timeout enforcement, ANSI stripping)
  7. Extract memory updates from response (facts, credentials, networks, notes)
  8. Append to memory + techniques
  9. Continue until task marked done or max turns hit
- **Memory system** (`memory.json`)
  - Structured: `{facts, networks, credentials, notes}`
  - Converted to human-readable context block fed back to LLM each turn
  - Persists across sessions
- **Technique system** (`techniques.json`)
  - Stores discovered attack patterns: `{technique_id: {name, steps, success_rate}}`
  - Built from successful command sequences
- **Session persistence**
  - Each run saved to `sessions/YYYYMMDDThhmmss.json`
  - Stores: task, provider, turn-by-turn messages, full log, memory state
  - Resume with `--resume` + optional new follow-up task

**`menu.py`** (333 lines) — Interactive CLI wrapper
- **MenuSystem class**
  - Providers: ollama (cloud + local), claude, anthropic
  - Models: dropdown of ~25 options per provider (cloud GLMs, Kimi, MiniMax, local Llama/Mistral/etc.)
  - Color output + arrow key navigation (fallback to simple input)
  - Task history (last 20 entries with timestamps)
- **Direct mode**: `python menu.py --provider ollama --model llama3.2:latest "task"` skips the menu
- **Execution**: spawns `agent.py` with selected provider/model/task

### Data Flow

```
User task (CLI/menu)
    ↓
Load memory.json + techniques.json
    ↓
System prompt: safety rules + memory context + available shell
    ↓
LLM call (messages history)
    ↓
Parse command (regex: backticks or <cmd>)
    ↓
Confirm with user (show command before execution)
    ↓
Sanitize (timeout, background pattern rewrite)
    ↓
Detect special tool (airodump-ng, nmap, aireplay-ng, Bluetooth)
    ↓
Execute (PTY shell for normal cmds, subprocess for special ones)
    ↓
Capture output (timeout handling, ANSI stripping, auto-read files)
    ↓
Extract memory updates (facts, credentials, networks, notes)
    ↓
Append to memory.json + techniques.json
    ↓
Save session JSON
    ↓
Next turn (unless done or max turns)
```

## Commands

### Running the Agent

```bash
# Interactive menu (select provider/model/task via arrows/numbers)
python menu.py

# Direct run (skip menu)
python menu.py --provider ollama --model llama3.2:latest "scan the wifi networks"

# Via agent.py directly
python agent.py --provider claude "write a security report"
python agent.py --provider ollama --model gpt-oss:120b-cloud "task here"
python agent.py --provider anthropic "task here"  # needs ANTHROPIC_API_KEY

# Advanced options
python agent.py --provider ollama --host https://ollama.com --model glm-5-cloud "task"  # cloud Ollama
python agent.py --provider claude --no-confirm "dangerous task"  # YOLO mode (no confirmation)
python agent.py --max-turns 100 --provider claude "long-running task"
python agent.py --list-sessions  # show recent sessions
python agent.py --resume sessions/20260422_150000.json  # resume + same task
python agent.py --resume sessions/20260422_150000.json "new follow-up"  # resume + new task
```

### Development

```bash
# Run linter/formatter (optional — code is straightforward)
python -m py_compile agent.py menu.py

# Test a specific provider
ANTHROPIC_API_KEY=your_key python agent.py --provider anthropic "test"
python agent.py --provider ollama "test"  # local Ollama
OLLAMA_API_KEY=your_key python agent.py --provider ollama --host https://ollama.com "test"  # cloud

# Debug session: inspect a saved session
cat sessions/20260422_150000.json | jq '.messages'  # see conversation
cat sessions/20260422_150000.json | jq '.memory'    # see final memory state
```

### Environment Variables

```bash
# For Anthropic provider
export ANTHROPIC_API_KEY=sk-...

# For Ollama cloud
export OLLAMA_API_KEY=your_key
# Then: python agent.py --provider ollama --host https://ollama.com ...
# Or let it auto-detect cloud if you set the API key (default is local Ollama)

# Local Ollama (default)
# No env vars needed; uses http://localhost:11434
```

## Key Design Patterns

### Safety-First Execution

The agent blocks dangerous patterns before they touch the shell. `is_dangerous()` returns a reason string if any pattern matches; dangerous commands are **rejected immediately** without confirmation prompt.

```python
# Examples of blocked patterns:
# ✗ rm -rf /
# ✗ mkfs /dev/sda
# ✗ airmon-ng (use airodump-ng on pre-monitored wlan1)
# ✗ ssh user@host (interactive; use sshpass -p password ssh user@host)
# ✗ sdptool browse (hang-prone; use hcitool info)
# ✗ wlan0 (protected; use wlan1)
```

### Persistent Memory

Memory is **not** a vector store or embedding DB; it's a simple JSON dict:
- **facts**: list of observations (`"WPA2 cracked on Fiber-4k"`), capped at 20 entries
- **networks**: `{ssid: {bssid, channel, security, ...}}` dict
- **credentials**: `{target: {username, password, method, ...}}` dict
- **notes**: list of insights, capped at 10 entries

The LLM sees this as a text block in every turn's system prompt. After each turn, the LLM's response is parsed for memory updates:
```
[MEMORY UPDATE]
- fact: WEP key cracked with aircrack-ng
- network: MyWifi {bssid: AA:BB:CC:DD:EE:FF, channel: 6}
- credential: router {username: admin, password: admin}
```

### Technique Learning

Similar pattern: after successful execution, the LLM is prompted to produce a technique entry:
```
[TECHNIQUE]
technique_id: wifi_handshake_capture_2025
name: WPA2 Handshake Capture via Deauth
steps:
  1. airodump-ng wlan1 -w handshake_1
  2. aireplay-ng -0 1 -a <bssid> wlan1
  3. Wait for handshake in airodump output
success_rate: 0.9
```

### PTY Shell vs. Subprocess

**PTY Shell** (for normal, interactive commands):
- Maintains state across commands (cd changes persist)
- Handles interactive prompts (y/n answers)
- Slower (PTY overhead + polling)
- Used by: general shell commands, Python REPL, git, etc.

**Subprocess** (for special tools):
- Faster, no PTY overhead
- Each command is isolated (no state)
- Required for tools that use raw sockets or curses: `airodump-ng`, `aireplay-ng`, `nmap`, Bluetooth tools
- Automatically selected by `run_agent()` based on regex detection

### Command Confirmation

Before executing any command, the agent:
1. Prints the command for user review
2. Waits for `y/n` input (unless `--no-confirm`)
3. If user says no, retries with LLM ("user rejected, try alternative")

Dangerous commands are rejected **before** the confirmation prompt (blocking happens in `is_dangerous()`).

## Output Format Conventions

The LLM is instructed to emit commands in one of two formats:

**Format A** (backticks, preferred):
```
The best approach is to scan with nmap:
`nmap -sV 192.168.1.0/24`
```

**Format B** (XML-style):
```
Let me run a port scan:
<cmd>nmap -sV 192.168.1.0/24</cmd>
```

The agent uses regex to extract the first command found in either format. If multiple commands exist in one response, only the first is executed (the LLM is prompted to continue in the next turn if more steps are needed).

## File Organization

```
forestgump/
├── agent.py              # Main agent loop + shell + providers + memory
├── menu.py               # Interactive CLI wrapper
├── CLAUDE.md             # This file
├── memory.json           # Persistent state: facts, networks, credentials, notes
├── techniques.json       # Learned attack patterns + success rates
├── sessions/             # Session logs (YYYYMMDD_hhmmss.json)
│   └── 20260422_150000.json
└── .gitignore            # Exclude __pycache__, *.pyc, .env, nohup.out
```

## Common Tasks & Debugging

### Check a Previous Session

```bash
# List sessions
python agent.py --list-sessions

# Inspect conversation
cat sessions/20260422_150000.json | jq '.messages[] | {role, content: .content[:100]}'

# Check memory learned
cat sessions/20260422_150000.json | jq '.memory'

# Check which commands ran
cat sessions/20260422_150000.json | jq '.log'
```

### Resume & Continue

```bash
# Same task, fresh continuation
python agent.py --resume sessions/20260422_150000.json

# New task building on prior session state
python agent.py --resume sessions/20260422_150000.json "now try cracking the password"
```

### Disable Safety Guards (Not Recommended)

The safety guards are hard-coded in `is_dangerous()`. To test or debug a blocked command:
1. Temporarily comment out the pattern in `DANGEROUS_PATTERNS`
2. Restart the agent
3. **Restore immediately after testing**

### Local Ollama Troubleshooting

```bash
# Check if Ollama is running
curl -s http://localhost:11434/api/tags | jq .

# Pull a model
ollama pull llama3.2:latest

# Test a provider
python agent.py --provider ollama --model llama3.2:latest "hello"
```

### Claude CLI Provider Setup

The `claude` provider uses the Claude Code CLI with OAuth (no API key). Prerequisites:
```bash
# 1. Install Claude Code CLI
pip install claude-code  # or use system package manager

# 2. Authenticate (opens browser)
claude login

# 3. Verify
claude --version

# 4. Use
python agent.py --provider claude "task here"
```

## Important Notes

- **Sessions are immutable**: Each run creates a new session file. To modify history, edit `sessions/file.json` directly (JSON format).
- **Memory is global**: All sessions read/write the same `memory.json` and `techniques.json`. Secrets in memory are **not encrypted**; store responsibly.
- **Provider is fixed per run**: Pick `claude`, `ollama`, or `anthropic` at startup; cannot switch mid-session.
- **Timeouts are strict**: Commands exceeding timeout are killed with Ctrl+C + recovery attempt. `airodump-ng` captures are limited to 25s; general commands to 15s.
- **PTY limitations**: Commands that require user input (passwords, interactive menus) work in PTY shell but may hang if the LLM doesn't provide input.
- **Bluetooth requires hardware**: Bluetooth commands validate `/sys/class/bluetooth/` for adapters before running.

## Verification Checklist

- ✓ `python menu.py` launches interactive menu with arrow keys
- ✓ `python agent.py --provider claude "hello"` runs using Claude CLI
- ✓ `python agent.py --list-sessions` shows recent runs
- ✓ `python agent.py --resume sessions/[file].json` resumes correctly
- ✓ Dangerous commands (e.g., `rm -rf /`) are blocked before confirmation
- ✓ `airodump-ng` with `-w` creates CSV files that are auto-read
- ✓ Memory is saved after each turn and visible in next session
- ✓ Technique entries are created and logged in `techniques.json`
- ✓ Subprocess tools (`nmap`, `aireplay-ng`) execute without hanging PTY
