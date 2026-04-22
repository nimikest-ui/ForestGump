# Bare Metal Agent — Workspace Instructions

This is a **minimal, anti-framework LLM agent** for security tasks. No tool abstractions, no playbooks — just a model and a raw bash shell with safety guards.

## Core Principles

1. **Single responsibility**: Agent sends one command at a time to bash  
2. **Safety-first**: Dangerous patterns blocked at regex level (wlan0, rm -rf, reboot, etc.)  
3. **Memory systems**: Persistent facts, networks, credentials, and proven techniques across sessions  
4. **Multi-provider**: Claude CLI (OAuth), Ollama (local/cloud), Anthropic API  
5. **Session resumption**: Save/restore conversation state mid-task  

## Quick Start

### Run the agent (direct mode, no prompts)

```bash
# Claude CLI (uses Pro subscription, no API key)
python agent.py --provider claude "scan wifi networks on wlan1"

# Ollama local (uses http://localhost:11434)
python agent.py --provider ollama --model llama3.2:latest "enumerate nearby networks"

# Ollama Cloud (requires OLLAMA_API_KEY from ollama.com/settings/keys)
OLLAMA_API_KEY=<key> python agent.py --provider ollama --model qwen3.5:397b-cloud "next bandit challenge"

# Anthropic API (requires ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY=<key> python agent.py --provider anthropic "task here"
```

### Run the agent (interactive menu)

```bash
# New task with menu navigation (uses arrow keys, numbers, Enter to select)
python menu.py

# Direct execution with args (no confirmations, fastest)
python menu.py --provider ollama --model llama3.2:latest "your task"

# Resume a previous session
python agent.py --resume sessions/20260422_020023.json

# Resume and give new follow-up task
python agent.py --resume sessions/20260422_020023.json "now try bandit10"
```

## Memory Systems

### 1. Persistent Facts (`memory.json`)

Auto-detected across sessions:
- **Networks**: WiFi SSIDs, BSSIDs, encryption, channels
- **Credentials**: Passwords, WPA PSKs, pins (auto-extracted from output)  
- **Facts**: Important findings, landmarks, learnings
- **Notes**: Manual session notes

**Load automatically** in system prompt each agent invocation.

### 2. Technique Library (`techniques.json`)

Proven approaches that work — shown to model on Turn 1:
- **SSH via Paramiko base64**: Discovered in bandit challenge (Turn 18 → Turn 2)  
- **sshpass automation**: Alternative SSH method
- **Base64 encoding**: General obfuscation for blocked patterns

**Format**:
```json
{
  "techniques": {
    "ssh_paramiko_base64": {
      "name": "SSH via Paramiko + base64",
      "problem": "Direct ssh commands blocked by PTY safety",
      "solution": "Encode paramiko script in base64, decode and execute",
      "template": "base64 -d <<< 'CODE' | python3",
      "tags": ["ssh", "paramiko", "obfuscation"],
      "success_rate": "high"
    }
  }
}
```

**Update manually** after successful agent sessions:
1. Run agent, discover new technique
2. Edit `techniques.json`, add new entry
3. Next agent run shows technique immediately (saves ~17 turns)

## Safety System  

**Blocked commands** are regex-matched before execution. The agent sees feedback:
```
Command BLOCKED (dangerous: reason). Try a different approach.
```

### Current patterns (25+ total)

| Pattern | Reason |
|---------|--------|
| `wlan0` (anywhere) | wlan0 is protected (network interface) |
| `ssh user@host` | Interactive SSH hangs PTY → use `sshpass` or `paramiko` |
| `telnet` | Interactive, same as SSH |
| `rm -r /` | Recursive file deletion |
| `dd of=/` | Disk writes |
| `reboot`, `shutdown` | System reboot/shutdown |
| `airmon-ng` | airmon-ng not needed; wlan1 already monitor mode |
| `rfcomm`, `gatttool`, etc. | Bluetooth tools that hang PTY |

**Exception**: `sshpass -p 'pass' ssh host 'command'` is **allowed** (non-interactive).

### How to unblock

If a command is incorrectly blocked, edit `agent.py` lines 83-102 (DANGEROUS_PATTERNS).  
Pattern format: `(r'regex', 'reason_message')`

**Example: Allow a new tool**
```python
# Remove or comment this line
(r'\btool_name\b', 'reason'),
```

Then commit and test with next agent run.

## Architecture

```
agent.py          ← Main loop: Shell → Provider → Parse → Memory → Save
├─ Shell class    ← Raw PTY, command execution, Ctrl+C recovery
├─ Providers      ← Claude CLI, Ollama, Anthropic (abstracted)
├─ Safety         ← is_dangerous() regex checker
├─ Memory         ← Load/save facts, networks, credentials
├─ Techniques     ← Load/format proven approaches  
└─ Sessions       ← Save/resume conversation state

menu.py           ← Interactive CLI (arrow keys, numbers, Enter)
├─ Provider selector (10+ models)
├─ Model selector (30+ models via Ollama)
├─ Task entry
└─ Direct execution (no confirmations)

sessions/         ← Per-task execution logs (JSON)
20260422_020023.json
├─ Task description
├─ Provider + model
├─ Full conversation (user/assistant messages)
├─ Execution log (turn-by-turn)
├─ Memory state (facts, networks, creds)
└─ Timestamp

memory.json       ← Cross-session learnings (updated each session)
techniques.json   ← Proven techniques (manually added)
```

## Common Workflows

### Security Task (Bandit, CTF, Network Test)

1. **First run**: `python menu.py` → Select provider/model → Task → Auto-saved
2. **View result**: Session JSON shows full trace (messages, output, reasoning)
3. **Add technique if successful**: Edit `techniques.json`, commit to git  
4. **Next similar task**: Agent sees technique on Turn 1 (~90% reduction in turns)

### Resume a Challenge

```bash
# View recent sessions
python agent.py --list-sessions

# Resume with follow-up
python agent.py --resume sessions/20260422_031120.json "continue to next bandit level"
```

### Debug a Blocked Command

```bash
# Agent says "Command BLOCKED (dangerous: ...)"
# Check what matched:
grep "reason_substring" agent.py | head -1

# If false positive, remove pattern, re-test
# If intentional, use alternative approach (see techniques.json)
```

## Configuration

### Ollama Cloud

```bash
# 1. Get API key from https://ollama.com/settings/keys
# 2. Export or pass as env var:
export OLLAMA_API_KEY=your_key_here

# 3. Use cloud models:
python agent.py --provider ollama --model glm-5.1-cloud "task"
```

### Claude CLI (OAuth)

```bash
# 1. Install: npm install -g @anthropic-ai/claude
# 2. Authenticate: claude login
# 3. Uses your Pro subscription (no API key needed)
python agent.py --provider claude "task"
```

### Anthropic API

```bash
# 1. Get key from https://console.anthropic.com/
# 2. Export:
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Use:
python agent.py --provider anthropic "task"
```

## File Structure

```
.github/
├─ copilot-instructions.md    ← This file
└─ (future .instructions.md for specific workflows)

agent.py                       ← 2000+ lines, core loop
menu.py                        ← 350+ lines, interactive CLI
techniques.json                ← Technique library (auto-loaded)
memory.json                    ← Cross-session facts
sessions/                      ← Session logs (auto-created)
└─ 20260422_*.json             ← Per-execution conversation state
```

## Development Guidelines

### Adding a New Provider

Edit `agent.py` (lines 395-475):

1. Create a new class `YourProvider` with `chat(messages, system)` method
2. Add to provider dispatcher (search `--provider`)
3. Test: `python agent.py --provider yourname --model mymodel "test"`

### Adjusting Safety Rules

Edit `agent.py` lines 83-102 (DANGEROUS_PATTERNS):

```python
DANGEROUS_PATTERNS = [
    # Add new pattern:
    (r'your_regex_here', 'human-readable reason'),
    # Pattern format: raw string, so use r'...' not '...'
    # Test with: python agent.py --no-confirm "test command"
]
```

### Improving Memory Extraction

Edit `extract_memory_updates()` (lines 475+). Currently auto-detects:
- WPA PSK, WPS PIN, passwords from output  
- BSSIDs with SSIDs
- Extend with new regex patterns as needed

## Session Persistence

Each run saves to `sessions/TIMESTAMP.json`:

```json
{
  "task": "bandit challenge description",
  "provider": "ollama/qwen3.5:397b-cloud",
  "turns": 19,
  "messages": [{role, content}, ...],
  "log": [{turn, type, cmd, output}, ...],
  "memory": {facts, networks, credentials, notes},
  "timestamp": "20260422_020023"
}
```

**Use cases**:
- **Fork session**: Load JSON, modify task, continue with new memory state
- **Audit**: View exact model outputs, shell commands, and reasoning
- **Resume**: `python agent.py --resume sessions/20260422_020023.json`

## Known Limitations

1. **Interactive tools hang PTY**: nmap, airmon-ng, some Bluetooth tools → use subprocess mode or timeout
2. **PTY echo noise**: Some tools print extra output → regex-stripped automatically
3. **Large responses timeout**: If model talks for 5+ min, reads truncated → summarize the task
4. **SSH/telnet blocked**: By design (prevent interactive hangs) → use paramiko or sshpass

## Next Steps for Development

1. **Add MCP integrations** (e.g., for WiFi scanning APIs)
2. **Implement auto-technique detection** (ML-based pattern extraction from successful sessions)
3. **Multi-agent orchestration** (coordinator agent + specialist agents)
4. **Custom providers** (e.g., local vLLM, Together API, etc.)

---

**Last updated**: 2026-04-22  
**Agent version**: v1.0 (bare metal, 25+ safety patterns, 3-provider support)
