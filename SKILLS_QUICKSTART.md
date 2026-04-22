# Skill DB Quick Start

## One-Minute Overview

The agent now learns from experience. Every successful session extracts reusable "skills" (attack techniques) and stores them in `skills.db`. Future sessions automatically find and use these learned skills.

## Usage

### Run Normally (Skills Happen Automatically)
```bash
python agent.py --provider claude "penetration test target.com"
```

**What happens:**
1. Agent searches `skills.db` for relevant skills based on your task
2. Top 5 matching skills are injected into the system prompt
3. Agent executes commands
4. After success, LLM extracts reusable skills from the conversation
5. New skills are saved to `skills.db`

### Query Your Learned Skills
```bash
sqlite3 skills.db "SELECT name, tags, success_rate FROM skills;"
```

### Search for Specific Skills
```bash
python -c "from skills import search_skills; import json; print(json.dumps([{k:s[k] for k in ['name','problem','solution']} for s in search_skills('ssh')], indent=2))"
```

### Run the Demo
```bash
python test_skills_extraction.py
```

## What Gets Saved

Each skill captures:
- **name** — Brief title (e.g., "SSH with sshpass")
- **problem** — What problem it solves
- **solution** — How it solves it
- **template** — Command template with placeholders (e.g., `sshpass -p {password} ssh {user}@{host}`)
- **tags** — Keywords for searching (e.g., `ssh,automation,sshpass`)
- **source_session** — When it was discovered
- **success_rate** — How often it works (0.6–0.9)

## Example: After Learning SSH Techniques

```bash
$ python agent.py --provider claude "ssh into a remote server"

# System prompt now includes:
PROVEN SKILLS (from previous successful sessions):

[SSH with sshpass]
  Problem: Need to automate SSH login with password
  Solution: Use sshpass tool to provide password non-interactively
  Template: sshpass -p '{password}' ssh {user}@{host} -p {port}
  Tags: ssh,automation,sshpass
  Success rate: 60%

[SSH via Paramiko with Base64 Encoding]
  Problem: SSH connection that blocks interactive shells
  Solution: Use paramiko with base64-encoded payloads
  Template: base64 -d <<< '{base64_code}' | python3
  Tags: ssh,automation,paramiko
  Success rate: 80%
```

The agent can now reference these proven techniques instead of starting from scratch.

## Files

| File | Purpose |
|------|---------|
| `skills.db` | Auto-created SQLite database |
| `skills.py` | API for CRUD, search, extraction |
| `agent.py` | Modified to use skills DB |
| `SKILLS_README.md` | Full documentation |
| `IMPLEMENTATION_SUMMARY.md` | Architecture details |

## Troubleshooting

### "No skills found" on first run
**Normal.** The database is empty until you run successful sessions. After a few runs, skills will accumulate.

### Skills not being extracted
**Check:**
```bash
cat sessions/LATEST.json | jq '.log[-5:]'  # See last 5 log entries
```
Extraction is best-effort; if the LLM doesn't produce JSON, it silently fails (non-blocking).

### Want to use old `techniques.json`?
Already done. On first run, all techniques are auto-migrated to `skills.db`.

### Want to manually add a skill?
```python
from skills import save_skill
skill = {
    'name': 'My Custom Technique',
    'problem': 'solve X',
    'solution': 'use Y',
    'template': 'cmd {arg}',
    'tags': ['custom', 'test']
}
save_skill(skill, source_session='manual')
```

## Advanced: Check What Skills Are Used

Each session's memories and logs are saved:
```bash
cat sessions/20260422_150000.json | jq '.log | map(select(.type == "exec")) | .[0]'
```

## What's Next?

- Run your normal workflows with `python agent.py --provider <provider> "<task>"`
- Skills will automatically accumulate from successful sessions
- Over time, you'll build a personal library of proven techniques specific to your targets
- The agent gets smarter each session as it reuses successful patterns
