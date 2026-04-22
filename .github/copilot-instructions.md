# Bare Metal Agent — ForestGump

Minimalist AI pentesting agent: one LLM + one raw bash PTY + safety guards. No tool abstractions, no playbooks.

See [CLAUDE.md](../CLAUDE.md) for full architecture, data flow, and design decisions.

## Quick Start

```bash
# Interactive menu (arrow keys, select provider/model/task)
python menu.py

# Direct run — no prompts
python agent.py --provider claude "scan wifi networks on wlan1"
python agent.py --provider ollama --model llama3.2:latest "enumerate nearby networks"
OLLAMA_API_KEY=<key> python agent.py --provider ollama --model glm-5.1-cloud "bandit challenge"
ANTHROPIC_API_KEY=<key> python agent.py --provider anthropic "task here"

# Session management
python agent.py --list-sessions
python agent.py --resume sessions/20260422_020023.json
python agent.py --resume sessions/20260422_020023.json "now try bandit10"
```

## File Map

| File | Purpose |
|------|---------|
| `agent.py` | Core loop: PTY shell, providers, safety, memory, sessions |
| `menu.py` | Interactive CLI wrapper (arrow keys, 30+ models) |
| `skills.py` | Skill DB API — CRUD, FTS5 search, LLM extraction |
| `skills.db` | SQLite FTS5 database; auto-grows each session (primary) |
| `techniques.json` | Legacy technique store; migrated into `skills.db` on startup |
| `memory.json` | Cross-session facts, networks, credentials, notes |
| `sessions/` | Per-run JSON logs with full conversation + memory state |

## Safety Rules (agent.py lines 64–102)

**Hard rule**: any command containing `wlan0` is unconditionally blocked.

Regex-blocked patterns (edit `DANGEROUS_PATTERNS` to change):

| Pattern | Reason |
|---------|--------|
| `rm -r` / `rm /` | Recursive/absolute deletion |
| `mkfs`, `dd of=/` | Disk format/overwrite |
| `reboot`, `shutdown`, `poweroff` | System shutdown |
| `systemctl stop/disable/mask` | Disable services |
| `airmon-ng` | Forbidden — wlan1 is already in monitor mode |
| `rfcomm`, `gatttool`, `l2ping`, etc. | Bluetooth tools that hang PTY |
| `wlan0` (hard rule) | Protected primary interface |

**SSH/telnet**: currently **not blocked** (was previously commented out). Direct `ssh` may hang the PTY — prefer `sshpass -p 'pass' ssh user@host 'command'` for non-interactive runs.

**Sanitizer**: background patterns (`cmd & ; sleep N && kill`) are auto-rewritten to `timeout N cmd`. Max timeout is capped at 35s.

To unblock a pattern: comment out the matching line in `DANGEROUS_PATTERNS`, then test with `--no-confirm`.

## Skills System

Skills are learned automatically from successful sessions and injected into Turn 1 of future runs.

```
Session ends → LLM extracts reusable skills → saved to skills.db (FTS5)
Next session  → top 5 matching skills → injected into system prompt
```

- **Search**: `skills.py:search_skills(query)` — FTS5 full-text over name/problem/solution/template/tags
- **Migrate**: `migrate_techniques_json()` runs on startup to import legacy `techniques.json` entries
- See [SKILLS_README.md](../SKILLS_README.md) for the full DB schema and API reference

## Memory System

`memory.json` — persists across all sessions:
- **facts** (cap 20): key findings, e.g. `"WPA2 cracked on Fiber-4k"`
- **networks**: `{ssid: {bssid, channel, security}}`
- **credentials**: `{target: {username, password, method}}`
- **notes** (cap 10): manual insights

LLM sees this as a text block every turn. After each turn, `[MEMORY UPDATE]` tags in the response are parsed and merged.

## Session Inspect

```bash
cat sessions/TIMESTAMP.json | python3 -m json.tool | grep -A2 '"role"'
cat sessions/TIMESTAMP.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d['memory'], indent=2))"
```

## Adding a Provider

1. Create class with `.chat(messages, system) → str` in `agent.py`
2. Wire into provider dispatcher (search `--provider` in `agent.py`)
3. Test: `python agent.py --provider yourname "hello"`

## Environment Variables

| Variable | Required for |
|----------|-------------|
| `ANTHROPIC_API_KEY` | `--provider anthropic` |
| `OLLAMA_API_KEY` | Ollama cloud models (`-cloud` suffix) |
