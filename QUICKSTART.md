# ForestGump Quick Start

**Bare Metal Agent** — minimalist AI pentesting with token-optimized execution.

## 🚀 Run the Agent

### Interactive Menu
```bash
python menu.py
```
Select provider, model, and task via arrow keys.

### Direct Command
```bash
# Using Claude Code CLI (Pro subscription, no API key)
python agent.py --provider claude "scan wifi networks"

# Using Anthropic API (with token caching + 41% savings)
export ANTHROPIC_API_KEY=sk-...
python agent.py --provider anthropic "task here"

# Local Ollama
python agent.py --provider ollama --model llama3.2:latest "task"

# GitHub Copilot
python agent.py --provider copilot --model claude-sonnet-4.5 "task"
```

### Options
```bash
# Skip confirmation prompts (YOLO mode)
python agent.py --provider claude --no-confirm "task"

# Increase max turns (default 50)
python agent.py --provider anthropic --max-turns 100 "task"

# Resume a previous session
python agent.py --resume sessions/20260430_123456.json
python agent.py --resume sessions/20260430_123456.json "follow-up task"

# List recent sessions
python agent.py --list-sessions
```

## 💰 Token Optimization (41% Savings)

The Anthropic provider automatically:
- **Caches system prompt** (90% discount on cached reads after turn 1)
- **Trims message history** (keeps last 10 turns, not full history)
- **Compresses outputs** (truncates large command results)
- **Retrieves skills once** (not every turn)

**Example session (25 turns):**
```
Input:         180 tokens (prompt messages)
Output:      5,029 tokens (LLM responses)
Cache hits: 160,228 tokens @ 90% discount = ~16K billed
Total cost: $0.0063 (~$0.0002 per command)
```

See [`TOKEN_OPTIMIZATION.md`](TOKEN_OPTIMIZATION.md) for tuning parameters.

## 📚 Memory & Skills

**Persistent Memory** (reused across sessions):
```bash
cat memory.json  # facts, networks, credentials, notes
```

**Learned Skills** (SQLite FTS5 database):
```bash
sqlite3 skills.db "SELECT name, success_rate FROM skills ORDER BY success_rate DESC;"
```

Skills are auto-retrieved at session start and injected into the system prompt.

## 🎯 Safety Rules

Hard-coded protections:
- ✗ `rm -rf` / `mkfs` (destructive)
- ✗ `airmon-ng` (use `airodump-ng` on pre-monitored `wlan1`)
- ✗ `wlan0` (protected; use `wlan1`)
- ✗ `sdptool browse`, `rfcomm`, `gatttool` (hang-prone)
- ✗ Interactive SSH/telnet (use `sshpass` instead)

## 🔧 Configuration

**Claude Code permissions** (reduces prompts):
```json
.claude/settings.json  # read-only tool allowlist (git, grep, jq, etc.)
```

**Environment variables:**
```bash
export ANTHROPIC_API_KEY=sk-...       # For Anthropic provider
export OLLAMA_API_KEY=your_key        # For Ollama cloud (ollama.com)
# Local Ollama: http://localhost:11434 (no env var needed)
```

## 📋 Common Tasks

### WiFi Pentesting
```bash
python agent.py --provider anthropic "scan for wifi networks and list them"
python agent.py --resume sessions/xxx.json "crack WPA2 handshake"
```

### Security Audit
```bash
python agent.py --provider anthropic --max-turns 50 "port scan and service enumeration"
```

### Code Analysis
```bash
python agent.py --provider anthropic "analyze this codebase for security issues"
```

## 📊 Session Inspection

View recent sessions:
```bash
python agent.py --list-sessions
```

Inspect a session:
```bash
cat sessions/20260430_123456.json | jq '.log[] | select(.type == "exec") | {cmd, output: (.output[:100])}'
cat sessions/20260430_123456.json | jq '.token_totals'
```

## 🛠️ Development

**Run tests:**
```bash
python3 test_token_optimizations.py
```

**Check syntax:**
```bash
python3 -m py_compile agent.py menu.py
```

**Extract skills from old sessions:**
```bash
python extract_skills_from_logs_fast.py
```

## 📚 Full Documentation

- **[TOKEN_OPTIMIZATION.md](TOKEN_OPTIMIZATION.md)** — Token reduction strategies, benchmarks, tuning
- **[CLAUDE.md](CLAUDE.md)** — Architecture, safety guards, providers, memory system
- **[SKILLS_README.md](SKILLS_README.md)** — Skill database, learning system
- **[SKILLS_QUICKSTART.md](SKILLS_QUICKSTART.md)** — Quick skill examples

## 💡 Tips

1. **Use Anthropic provider for cost efficiency** — prompt caching saves 70-80% after turn 5
2. **Resume sessions strategically** — build on prior knowledge, memory persists
3. **Inspect session logs** — `sessions/` directory stores full transcripts for debugging
4. **Monitor cache hits** — token summary shows cache_creation vs cache_read metrics
5. **Let skills accumulate** — first few runs populate the skills database, then you see benefits

## ⚠️ Warnings

- Sessions are immutable JSON files (don't edit directly)
- Memory is **not encrypted** — don't store sensitive data
- Bluetooth requires hardware (`/sys/class/bluetooth/` must exist)
- wlan1 must be in monitor mode before wifi commands
- Timeouts capped at 35s (airodump-ng captures get 25s max)

---

**Ready?** Run `python menu.py` or `python agent.py --provider anthropic "your task"`
