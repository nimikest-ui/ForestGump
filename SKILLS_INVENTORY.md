# Skill Database Inventory

Auto-generated inventory of learned skills from session logs.

## Quick Stats

- **Total Skills**: 75+ (growing)
- **Unique Categories**: 40+
- **Source**: 
  - Manual techniques from `techniques.json` (3 original)
  - Pattern extraction from 50+ session logs
  - LLM-guided extraction from successful sessions

## Skills by Category

### SSH & Remote Access (38 skills)
Techniques for secure shell authentication, command execution, and key-based access.

**Top Skills:**
- SSH via Paramiko with Base64 Encoding
- sshpass non-interactive SSH
- SSH password auth with sshpass
- SSH command chaining through levels
- SSH_ASKPASS password injection
- Paramiko SSH Remote Command Execution

### CTF & Capture The Flag (28 skills)
Specific techniques learned from CTF challenges (Bandit, OverTheWire, etc).

**Top Skills:**
- SSH password auth with sshpass
- Read large CSV without pager
- cat with -- for filenames starting with dashes
- ROT13 Decode via tr
- Hexdump Reverse with xxd
- Iterative Decompression Chain

### Automation & Scripting (25 skills)
Automation patterns for repeatable tasks.

**Top Skills:**
- Base64 Encoding for Shell Bypass
- Base64 decode credential extraction
- Iterative Decompression Chain
- Non-interactive SSH command execution

### Reconnaissance & Enumeration (14 skills)
Information gathering and target discovery.

**Top Skills:**
- Nmap scan with sV
- Nmap scan with sn
- Airodump-ng CSV parse
- WPA2 Handshake Capture

### Bandit Level Solutions (11 skills)
Solutions to specific Bandit challenges.

**Top Skills:**
- Bandit level password auth techniques
- File reading with special characters
- CSV processing and parsing

## Search Examples

```bash
# Find SSH techniques
python -c "from skills import search_skills; [print(s['name']) for s in search_skills('ssh', limit=5)]"

# Find reconnaissance skills
python -c "from skills import search_skills; [print(s['name']) for s in search_skills('nmap', limit=5)]"

# Find WiFi techniques
python -c "from skills import search_skills; [print(s['name']) for s in search_skills('wifi')]"

# Find password/credential techniques
python -c "from skills import search_skills; [print(s['name']) for s in search_skills('password')]"
```

## How Skills Are Created

### Method 1: Pattern Extraction (Fast)
Parses session logs for command patterns:
- SSH commands → SSH techniques
- nmap commands → port scanning techniques
- Aircrack tools → WiFi techniques
- Web tools → web enumeration techniques

**Run:**
```bash
python extract_skills_from_logs_fast.py
```

### Method 2: LLM Extraction (Slower, Smarter)
Asks the LLM to extract reusable techniques from session conversation:
- Understands context and problem-solving approach
- Captures nuanced techniques
- Can extract multi-step attack chains

**Run:**
```bash
python extract_skills_from_logs.py
```

## Skill Structure

Each skill contains:

```json
{
  "name": "SSH with sshpass",
  "problem": "Need to automate SSH login with password",
  "solution": "Use sshpass tool to provide password non-interactively",
  "template": "sshpass -p '{password}' ssh {user}@{host} -p {port}",
  "tags": ["ssh", "automation", "sshpass"],
  "source_session": "20260422_150000",
  "success_rate": 0.8,
  "use_count": 5,
  "created_at": "2026-04-22T15:00:00"
}
```

## Continuous Learning

Skills automatically grow as you run the agent:

1. Every successful session triggers skill extraction
2. New skills saved with source session ID
3. FTS5 index updated automatically
4. Future sessions search for and use relevant skills
5. Closing feedback loop: successful patterns compound

## Skill Ranking

Skills are ranked by:
1. **Success Rate** (EWMA: 0.0–1.0)
   - Successful use: rate += (1 - rate) × 0.1
   - Failed use: rate -= rate × 0.1
2. **Use Count**
   - Higher = proven effective
3. **Recency**
   - Recently discovered skills prioritized

## Next Steps

- Run `python agent.py --provider claude "<task>"` normally
- Skills will be automatically extracted and learned
- Over time, the skill library becomes personalized to your workflows
- Revisit sessions that worked well to extract more sophisticated patterns

## Management

### Query the Database
```bash
# List all skills
sqlite3 skills.db "SELECT name, tags FROM skills ORDER BY use_count DESC LIMIT 20;"

# Find skills by tag
sqlite3 skills.db "SELECT name FROM skills WHERE tags LIKE '%ssh%';"

# Check success rates
sqlite3 skills.db "SELECT name, success_rate, use_count FROM skills ORDER BY success_rate DESC LIMIT 10;"
```

### Clear/Reset Database
```bash
# Backup
cp skills.db skills.db.backup

# Reset
rm skills.db
python -c "from skills import init_db; init_db()"
```

## Statistics

- **Average skill length**: ~60 characters (compact, reusable)
- **Most common tags**: ssh, automation, recon, ctf, bandit
- **Extraction rate**: ~1 skill per 10 lines of successful commands
- **FTS5 index size**: ~50KB for 75 skills

## Future Enhancements

- [ ] Skill chaining (dependencies between skills)
- [ ] Success rate feedback from user
- [ ] Skill merging (consolidate similar techniques)
- [ ] Time-based decay (remove low-use skills)
- [ ] Skill difficulty ratings
- [ ] Skill prerequisites and recommendations
