# Skill Database System

The skill database (`skills.db`) is an SQLite FTS5 (full-text search) database that grows automatically from session experience. Instead of manually updating `techniques.json`, the agent now learns reusable skills from successful runs and makes them available to future sessions.

## How It Works

### 1. During a Session
- Agent executes commands and learns from the shell
- Memory is updated (networks, credentials, facts)

### 2. After a Successful Session
- The agent asks the LLM to extract reusable skills from the conversation
- Skills are saved to `skills.db` with metadata: name, problem, solution, template, tags
- Each skill stores its source session and success rate

### 3. In the Next Session
- Agent searches `skills.db` for relevant skills using FTS5
- Top 5 matching skills are injected into the LLM's system prompt
- The LLM can reference and build on proven techniques

## Database Schema

```sql
CREATE TABLE skills (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,                  -- e.g. "SSH with sshpass"
    problem TEXT,                        -- e.g. "Interactive SSH blocks PTY"
    solution TEXT,                       -- e.g. "Use sshpass for non-interactive auth"
    template TEXT,                       -- e.g. "sshpass -p {password} ssh {user}@{host}"
    tags TEXT,                           -- e.g. "ssh,automation,sshpass"
    source_session TEXT,                 -- timestamp of the session that discovered it
    success_rate REAL DEFAULT 0.8,       -- EWMA score for ranking
    use_count INTEGER DEFAULT 0,         -- how many times this skill was used
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE skills_fts USING fts5(  -- Full-text search index
    name, problem, solution, template, tags,
    content='skills', content_rowid='id'
);
```

## Files

| File | Purpose |
|------|---------|
| `skills.db` | SQLite database (auto-created on first run) |
| `skills.py` | Skill DB API: CRUD, FTS search, extraction, migration |
| `agent.py` | Modified to initialize skills DB and extract skills at session end |
| `test_skills_extraction.py` | Demo script showing skill creation and search |

## API Reference

### Initialize DB
```python
from skills import init_db
init_db()  # creates skills.db with schema
```

### Save a Skill
```python
from skills import save_skill
skill = {
    'name': 'WPA2 Handshake Capture',
    'problem': 'Capture WPA2 4-way handshake for cracking',
    'solution': 'Use airodump-ng + aireplay-ng deauth',
    'template': 'airodump-ng -w capture -c {channel} {interface}',
    'tags': ['wifi', 'wpa2', 'handshake']
}
skill_id = save_skill(skill, source_session='20260422_150000')
```

### Search Skills
```python
from skills import search_skills
results = search_skills('wifi cracking', limit=5)
for skill in results:
    print(skill['name'], f"({skill['success_rate']:.0%})")
```

### Get All Skills
```python
from skills import get_all_skills
all_skills = get_all_skills(limit=20)
```

### Format for LLM Prompt
```python
from skills import skills_context
prompt_block = skills_context(task='wifi assessment', limit=5)
# Returns formatted string ready to inject into system prompt
```

### Extract Skills from Session
```python
from skills import extract_skills_from_session
new_skills = extract_skills_from_session(
    messages=conversation_history,
    memory=agent_memory,
    session_id='20260422_150000',
    provider=llm_provider,
    outcome='success'
)
```

### Migrate from techniques.json
```python
from pathlib import Path
from skills import migrate_techniques_json
migrate_techniques_json(Path('techniques.json'))
# One-time import of existing techniques into skills.db
```

## Usage Examples

### Run the Test Script
```bash
python test_skills_extraction.py
# Output: ✓ Created skill ID: 1
#         ✓ Found 1 results for 'WPA2 handshake'
#         ✓ Total skills in database: 4
#         ✓ Generated skill context: ...
```

### Query Skills via SQLite
```bash
sqlite3 skills.db "SELECT name, tags, success_rate FROM skills ORDER BY success_rate DESC;"
sqlite3 skills.db "SELECT * FROM skills WHERE id=1;"
```

### Search Skills
```bash
python -c "from skills import search_skills; results = search_skills('ssh automation', limit=3); [print(s['name']) for s in results]"
```

## How Skill Extraction Works

After a successful session, `extract_skills_from_session()`:

1. Builds a compact summary of the session (last 10 messages + learned memory)
2. Sends an extraction prompt to the same LLM provider:
   ```
   Based on this session, extract 1-3 reusable skills as JSON:
   [{ "name": "...", "problem": "...", "solution": "...", 
      "template": "...", "tags": [...] }]
   ```
3. Parses the JSON response and saves each skill via `save_skill()`
4. Prints confirmation: `✓ Learned skill: SSH with sshpass`

The extraction is **best-effort**:
- If the LLM doesn't produce valid JSON, the extraction silently fails
- Outcome is logged to the console but doesn't block session completion
- Skills are only saved if extraction succeeds

## Backward Compatibility

When `agent.py` first runs:
1. `init_skills_db()` creates an empty `skills.db` if needed
2. `migrate_techniques_json()` imports existing `techniques.json` entries
3. Future sessions use skills from `skills.db` instead of the static file

Existing `techniques.json` is untouched and can coexist.

## Next Steps

- Run `python agent.py --provider claude "your task"` normally
- After a successful session, check `skills.db`: `sqlite3 skills.db "SELECT * FROM skills;"`
- Start a new session and observe the LLM receiving relevant skills in the system prompt
- Over time, the agent will accumulate a library of proven techniques specific to your workflows
