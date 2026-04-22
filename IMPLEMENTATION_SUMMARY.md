# Skill Database Implementation Summary

## What Was Built

A **persistent, searchable skill database** (`skills.db`) that grows automatically from agent session experience. The system replaces manual technique updates with LLM-guided skill extraction and FTS5 full-text search.

## Files Created / Modified

### New Files
- **`skills.py`** (240 lines) — Complete skill DB API
  - `init_db()` — Create/initialize skills.db with FTS5 schema
  - `save_skill()` — Store a skill with FTS indexing
  - `search_skills()` — Full-text search by name/problem/solution/template/tags
  - `get_all_skills()` — Retrieve top skills by use count
  - `skills_context()` — Format skills into LLM prompt block
  - `extract_skills_from_session()` — Ask LLM to extract reusable skills from conversation
  - `migrate_techniques_json()` — One-time import of existing techniques.json

- **`test_skills_extraction.py`** (40 lines) — Demo script showing skill creation and search

- **`SKILLS_README.md`** — Complete user documentation with API reference and examples

### Modified Files
- **`agent.py`**
  - Line 47: Import skills module functions
  - Lines 549–550: Initialize skills DB and migrate techniques on startup
  - Lines 553–559: Search skills DB for relevant skills, inject into system prompt
  - Lines 946–947: Extract skills from successful sessions at the end

## Architecture

```
┌─────────────────────────────────────────────┐
│  Session Starts                             │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │ init_skills_db()            │
        │ migrate_techniques.json     │
        │ (one-time)                  │
        └─────────────┬───────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │ Search skills.db by task    │
        │ keywords (FTS5)             │
        └─────────────┬───────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │ Inject top 5 skills into    │
        │ LLM system prompt           │
        └─────────────┬───────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│  Agent executes commands, learns from shell │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│  Session Ends (success/abandoned)           │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │ If outcome == 'success':    │
        │   extract_skills_from_session
        │   - Build session summary   │
        │   - Ask LLM for JSON list   │
        │   - save_skill() each one   │
        └─────────────┬───────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │ Skills stored in skills.db  │
        │ (FTS indexed, tagged,       │
        │  timestamped)               │
        └─────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │ Next session searches DB    │
        │ for relevant skills...      │
        └─────────────────────────────┘
```

## Database Schema

```sql
-- Persistent skill storage
CREATE TABLE skills (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    problem TEXT,
    solution TEXT,
    template TEXT,
    tags TEXT,                    -- comma-separated
    source_session TEXT,          -- timestamp of discovery
    success_rate REAL DEFAULT 0.8,
    use_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Full-text search index
CREATE VIRTUAL TABLE skills_fts USING fts5(
    name, problem, solution, template, tags,
    content='skills', content_rowid='id'
);
```

## Example Output

### Initial Session
```
$ python agent.py --provider claude "test ssh connection"
Task: test ssh connection
Loading skills from experience...
✓ Loaded 4 proven skills from database

SYSTEM PROMPT INCLUDES:
PROVEN SKILLS (from previous successful sessions):

[SSH via Paramiko with Base64 Encoding]
  Problem: SSH connection that blocks interactive shells or times out
  Solution: Use base64-encoded Python paramiko script to execute SSH programmatically
  Template: base64 -d <<< '{base64_code}' | python3
  Tags: ssh,automation,paramiko,bypass-interactive
  Success rate: 80% (used 0 times)

[SSH with sshpass]
  Problem: Need to automate SSH login with password
  Solution: Use sshpass tool to provide password non-interactively
  Template: sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {user}@{host} -p {port} '{command}'
  Tags: ssh,automation,sshpass
  Success rate: 60% (used 0 times)

...
```

### After Session Completes
```
...
✓ Learned skill: WPA2 Handshake Capture via airodump-ng
✓ Learned skill: Password cracking with hashcat
✓ Learned skill: Post-exploitation data exfil via base64

📝 Session saved: sessions/20260422_150000.json
   Resume with: python agent.py --resume sessions/20260422_150000.json
```

## How It Works

### 1. Skill Extraction
After a successful session:
```python
extract_skills_from_session(messages, memory, session_id, provider)
```
- Takes the full conversation history + learned memory
- Sends compact summary to the LLM:
  ```
  Based on this session, extract 1-3 reusable skills as JSON:
  [{name, problem, solution, template, tags}]
  Only include steps that succeeded. Return [] if nothing reusable.
  ```
- Parses response and saves each skill to `skills.db`

### 2. Skill Search & Injection
At session start:
```python
skill_str = skills_context(task, limit=5)  # FTS5 search by task keywords
full_system = SYSTEM + '\n\n' + skill_str   # Injected into system prompt
```
- Searches `skills.db` using FTS5 (name, problem, solution, template, tags)
- Returns top 5 matching skills ordered by success_rate and use_count
- Formats as human-readable block for the LLM

### 3. Fallback to Static Techniques
If no relevant skills found:
```python
if not skill_str:
    techniques_str = techniques_context(techniques)  # static techniques.json
    full_system = SYSTEM + '\n\n' + techniques_str
```

## Key Design Decisions

1. **FTS5 Search, Not Vector DB** — Full-text search is sufficient for skill discovery; no embedding overhead
2. **Best-Effort Extraction** — If LLM doesn't produce valid JSON, extraction silently fails; session completes normally
3. **No Backpressure** — Skills don't block session completion; extraction is async-friendly
4. **Backward Compatible** — `techniques.json` auto-migrated on first run; old workflows still work
5. **Session-Scoped Learning** — Skills extracted from individual sessions, not cross-session aggregation

## Testing

### Run the Demo
```bash
python test_skills_extraction.py
# Output:
# ✓ Created skill ID: 4
# ✓ Found 1 results for 'WPA2 handshake'
# ✓ Total skills in database: 4
# ✓ Generated skill context:
# [PROVEN SKILLS section...]
```

### Query the Database
```bash
sqlite3 skills.db "SELECT name, tags, success_rate FROM skills ORDER BY success_rate DESC LIMIT 5;"

# Output:
# SSH via Paramiko with Base64 Encoding|ssh,automation,paramiko,bypass-interactive|0.8
# SSH with sshpass|ssh,automation,sshpass|0.6
# ...
```

### Search for Specific Skills
```bash
python -c "from skills import search_skills; print([s['name'] for s in search_skills('wifi cracking')])"
# Output: ['WPA2 Handshake Capture']
```

## Integration Points

- **agent.py line 47** — Import skills functions
- **agent.py lines 549–550** — Initialize DB on session start
- **agent.py lines 553–559** — Search and inject skills into system prompt
- **agent.py lines 946–947** — Extract skills from conversation at session end

## Future Enhancements

1. **Success Rate Updates** — Track which skills are actually used and update EWMA scores
2. **Skill Merging** — Detect duplicate skills and consolidate
3. **Decay & Pruning** — Remove low-success-rate skills after N months
4. **Skill Chaining** — Store dependencies between skills (e.g., "requires recon first")
5. **Tag-Based Filtering** — Let agent choose which skill categories to use
6. **Skill Rating** — Allow user feedback: `rate_skill(skill_id, rating)`

## Verification Checklist

- ✓ `skills.py` implements full CRUD + FTS search
- ✓ `agent.py` imports and initializes skills DB on startup
- ✓ `techniques.json` auto-migrated to `skills.db` on first run
- ✓ Skills injected into LLM system prompt (top 5 by FTS relevance)
- ✓ Skill extraction runs at session end for successful sessions
- ✓ Test script validates skill creation, search, and formatting
- ✓ Database persists across sessions
- ✓ Backward compatible with existing `techniques.json`
- ✓ No breaking changes to agent.py execution flow
