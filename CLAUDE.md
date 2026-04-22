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
  3. LLM providers (pluggable: Claude CLI, Anthropic API, Ollama local/cloud, GitHub Copilot)
  4. Memory persistence (facts, networks, credentials, discovered techniques)
  5. Skill database (SQLite FTS5 for learned attack patterns with efficiency ranking)

## Architecture

### Core Components

**`agent.py`** (1314 lines) — The main loop
- **Shell class**: Pseudo-terminal wrapper using `pty.openpty()` with sentinel-based output capture
  - Handles interactive tools that hang or produce curses output
  - Non-blocking reads with select polling
  - Automatic Ctrl+C + recovery on timeout
- **Providers** (`AnthropicProvider`, `OllamaProvider`, `ClaudeCliProvider`, `CopilotProvider`)
  - Each has `.chat(messages, system) → text` interface
  - Claude CLI uses subprocess + OAuth (no API key)
  - Ollama supports local (http://localhost:11434) and cloud (ollama.com with API key); includes 25+ cloud models (GLM, Kimi, MiniMax, DeepSeek, etc.)
  - Anthropic uses direct API calls
  - GitHub Copilot CLI uses `gh copilot` with OAuth (no API key); denies shell/write tools
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

**`skills.py`** (289 lines) — Skill database & learning
- **SQLite FTS5 database** (`skills.db`)
  - Stores learned attack patterns: `{name, problem, solution, template, tags, success_rate}`
  - Full-text search on problem/solution/tags for fast relevance matching
  - Efficiency scoring: prioritizes skills by `(use_count * 100) - best_session_turns` (fewer turns = higher priority)
- **Auto-extraction from sessions**
  - After successful runs, LLM produces JSON-formatted skill entries
  - Skills are searchable by task keywords; top 5 relevant skills injected into system prompt
  - Success rates (0.6–0.9) updated via EWMA after each use
- **Migration from old format**
  - On first run, `techniques.json` is auto-imported into `skills.db`
  - New techniques are learned and stored only in the database

**`menu.py`** (350 lines) — Interactive CLI wrapper
- **MenuSystem class**
  - Providers: ollama (25+ cloud + 15+ local models), claude, anthropic, copilot
  - Cloud models: GLM 5.1/5, Kimi K2.6/K2.5, MiniMax M2.7/M2.5, Devstral, DeepSeek, Mistral, Gemma, Nemotron
  - Local models: Llama 3.2/3.1, Mistral, Gemma, QwenQwenq, TinyLlama, DeepSeek-R1, Code Llama, and vision models
  - Color output + arrow key navigation (fallback to simple input)
  - Task history (last 20 entries with timestamps)
  - No-confirmation mode (skip user prompts for all commands)
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

# Via agent.py directly (with automatic skill injection from skills.db)
python agent.py --provider claude "write a security report"
python agent.py --provider ollama --model glm-5-cloud "task here"  # cloud Ollama
python agent.py --provider anthropic "task here"  # needs ANTHROPIC_API_KEY
python agent.py --provider copilot --model claude-sonnet-4.5 "task here"  # GitHub Copilot CLI

# Advanced options
python agent.py --provider claude --no-confirm "dangerous task"  # YOLO mode (no confirmation)
python agent.py --max-turns 100 --provider ollama --model llama3.2:latest "long-running task"
python agent.py --list-sessions  # show recent sessions
python agent.py --resume sessions/20260422_150000.json  # resume + same task
python agent.py --resume sessions/20260422_150000.json "new follow-up"  # resume + new task
```

**Note on skills**: On each run, the agent automatically searches `skills.db` for relevant techniques and injects the top 5 matching skills into the system prompt. Skills are ranked by efficiency (fewer turns to success = higher priority). After successful completion, new skills are extracted and stored.

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

# For Ollama (local or cloud)
export OLLAMA_API_KEY=your_key  # For ollama.com cloud (if using --host https://ollama.com)
# Local Ollama (default): http://localhost:11434 — no env vars needed

# For GitHub Copilot provider
# No env vars needed; uses existing `gh auth` session (run `gh auth login` if needed)

# Optional: speed up queries if skills.db gets large
export SKILLS_FTS_LIMIT=5  # Default top 5 skills per query
```

## Learning System: Skills Database

The agent learns from experience. After each successful run, reusable attack patterns are extracted and stored in `skills.db`. On subsequent runs, relevant skills are automatically retrieved and injected into the system prompt.

### Workflow

1. **Skill Retrieval** (start of each run): FTS5 search on task keywords → top 5 skills ranked by efficiency score
2. **Skill Injection**: Proven techniques added to system prompt under "PROVEN SKILLS (from previous sessions)"
3. **Execution**: Agent generates commands, executes them, collects output
4. **Skill Extraction** (on success): LLM produces structured JSON entries for new techniques discovered
5. **Skill Storage**: New skills saved to `skills.db` with success_rate ≈ 0.8, updated via EWMA on reuse

### Example Skill Entry

```json
{
  "name": "WiFi Handshake Capture via Deauth",
  "problem": "Capture WPA2 four-way handshake from air",
  "solution": "Use airodump-ng to monitor, aireplay-ng to trigger deauth",
  "template": "airodump-ng wlan1 -w handshake_1; aireplay-ng -0 1 -a {bssid} wlan1",
  "tags": ["wifi", "wireless", "handshake", "wpa2"],
  "success_rate": 0.85
}
```

### Skill Ranking

Efficiency score = `(use_count * 100) - best_session_turns`. Skills that solved problems in fewer turns rank higher. This prioritizes proven-effective, fast solutions over slow or unreliable ones.

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
├── Core Components
│   ├── agent.py              # Main agent loop + shell + providers + memory
│   ├── menu.py               # Interactive CLI + model selection
│   ├── skills.py             # Skill database (SQLite FTS5) + CRUD
│
├── Persistent State
│   ├── memory.json           # Facts, networks, credentials, notes (global across sessions)
│   ├── techniques.json       # Legacy (auto-migrated to skills.db on first run)
│   ├── skills.db             # SQLite FTS5 database of learned attack patterns
│
├── Session History
│   ├── sessions/             # Session logs (YYYYMMDD_hhmmss.json)
│   │   └── 20260422_150000.json  # Includes task, messages, log, memory state
│
├── Documentation & Config
│   ├── CLAUDE.md             # This file
│   ├── SKILLS_README.md      # Full skill system documentation
│   ├── SKILLS_QUICKSTART.md  # Quick start for skill database
│   ├── .gitignore            # Exclude __pycache__, *.pyc, .env, nohup.out
│
├── Utilities
│   ├── extract_skills_from_logs.py     # Batch skill extraction from old sessions
│   ├── extract_skills_from_logs_fast.py # Optimized batch extractor
│   ├── test_skills_extraction.py       # Demo of skill system
```

## Common Tasks & Debugging

### Working with Skills Database

```bash
# List all learned skills
sqlite3 skills.db "SELECT id, name, tags, success_rate FROM skills ORDER BY success_rate DESC;"

# Search for a specific skill
python -c "from skills import search_skills; import json; print(json.dumps([{k:s[k] for k in ['name','problem','solution']} for s in search_skills('wifi')], indent=2))"

# Manually add a skill
python -c "from skills import save_skill; save_skill({'name': 'My Technique', 'problem': 'Problem X', 'solution': 'Use Y', 'template': 'cmd {arg}', 'tags': ['custom']}, source_session='manual')"

# Export skills to JSON for backup
sqlite3 skills.db -json "SELECT * FROM skills;" > skills_backup.json

# Reimport from old techniques.json (runs on first startup automatically)
python agent.py --provider claude "test"  # First run triggers migration
```

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

# Resume preserves memory + skills knowledge
# On resume, learned skills are injected again, and new skills can be learned from the follow-up
```

**Improvements (as of latest commits)**:
- Resume now better handles **partial command failures** — if a command only partially succeeded, the agent can continue working rather than getting stuck
- **Repeated command logic** — the agent detects when it's retrying the same command and suggests alternatives instead of looping

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

### GitHub Copilot Provider Setup

The `copilot` provider uses `gh copilot` (GitHub's CLI-based LLM interface). Prerequisites:
```bash
# 1. Install GitHub CLI
# macOS: brew install gh
# Linux: https://github.com/cli/cli/releases
# Or: apt-get install gh

# 2. Authenticate (opens browser)
gh auth login

# 3. Install Copilot CLI extension
curl -fsSL https://gh.io/copilot-install | bash

# 4. Verify
gh copilot --version

# 5. Use
python agent.py --provider copilot --model claude-sonnet-4.5 "task here"
# Available models: claude-sonnet-4.5 (default), claude-sonnet-4.6, gpt-5.4, etc.
```

**Note**: Copilot CLI denies `shell` and `write` tools, so ForestGump's PTY stays in control of all command execution.

## Best Practices

### Using Skills Effectively
- **On first run**: Don't expect skills to be available; the database is empty until you run successful sessions
- **Build a skill library**: Run diverse tasks and let the agent extract patterns; over time, the library becomes more valuable
- **Skill decay**: If a technique stops working, its success_rate decreases; consider re-learning with a newer approach
- **Search skills manually**: Before running a new task, check if relevant skills exist: `python -c "from skills import search_skills; ..."`
- **Tag your skills**: Use descriptive tags (`ssh`, `wifi`, `decode`, etc.) so the search works well

### Session Management
- **Use `--no-confirm` sparingly**: Great for long batch runs, but disable for dangerous tasks
- **Resume strategically**: After each successful phase, save the session; resume lets you build on prior knowledge
- **Inspect session logs**: Check `sessions/[file].json` if results seem odd; logs show every command executed and output received

### Memory & Credentials
- **Don't store sensitive data in memory**: Facts/notes are plain JSON, not encrypted
- **Credential scope**: Store credentials by target (e.g., `router.wifi`, `target.com`), not globally
- **Clear memory periodically**: Trim `memory.json` if it grows too large (> 1MB)

## Important Notes

- **Sessions are immutable**: Each run creates a new session file. To modify history, edit `sessions/file.json` directly (JSON format).
- **Memory is global**: All sessions read/write the same `memory.json`. Secrets in memory are **not encrypted**; store responsibly.
- **Skills are also global**: All sessions read/write `skills.db`. Learned skills persist across projects.
- **Provider is fixed per run**: Pick `claude`, `ollama`, `anthropic`, or `copilot` at startup; cannot switch mid-session.
- **Timeouts are strict**: Commands exceeding timeout are killed with Ctrl+C + recovery attempt. `airodump-ng` captures are limited to 25s; general commands to 15s.
- **PTY limitations**: Commands that require user input (passwords, interactive menus) work in PTY shell but may hang if the LLM doesn't provide input.
- **Bluetooth requires hardware**: Bluetooth commands validate `/sys/class/bluetooth/` for adapters before running.
- **Skills auto-extraction is best-effort**: If the LLM doesn't produce properly formatted JSON, skill extraction silently fails (non-blocking); the run still succeeds.

## Verification Checklist

**Core Functionality**
- ✓ `python menu.py` launches interactive menu with arrow keys and 4 providers
- ✓ `python agent.py --provider claude "hello"` runs using Claude CLI
- ✓ `python agent.py --provider copilot --model claude-sonnet-4.5 "hello"` uses GitHub Copilot
- ✓ `python agent.py --list-sessions` shows recent runs with timestamps
- ✓ `python agent.py --resume sessions/[file].json` resumes correctly with memory + skills
- ✓ Resume with new task: `--resume sessions/[file].json "follow-up task"` works

**Safety & Execution**
- ✓ Dangerous commands (e.g., `rm -rf /`) are blocked before confirmation
- ✓ `airodump-ng` with `-w` creates CSV files that are auto-read
- ✓ Subprocess tools (`nmap`, `aireplay-ng`, Bluetooth) execute without hanging PTY
- ✓ Partial command failures are detected and don't cause infinite loops
- ✓ Repeated command attempts suggest alternatives instead of retrying

**Memory & Learning**
- ✓ Memory is saved after each turn and visible in next session
- ✓ Skills database (`skills.db`) is created on first run
- ✓ Successful sessions extract reusable skills and save them
- ✓ On next run, relevant skills are found and injected into system prompt
- ✓ Skills are ranked by efficiency (fewer turns = higher priority)
- ✓ Old `techniques.json` is auto-migrated to `skills.db` on first startup
