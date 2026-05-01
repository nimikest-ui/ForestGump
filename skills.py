#!/usr/bin/env python3
"""
Skill database: persistent, searchable, auto-learned from session experience.
Replaces the static techniques.json with a dynamic SQLite FTS5 database.
"""

import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime

SKILLS_DB = Path(__file__).parent / 'skills.db'


def init_db():
    """Initialize skills.db with schema if not present."""
    with sqlite3.connect(SKILLS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                problem TEXT,
                solution TEXT,
                template TEXT,
                tags TEXT,
                source_session TEXT,
                success_rate REAL DEFAULT 0.8,
                use_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
                name, problem, solution, template, tags,
                content='skills', content_rowid='id'
            )
        """)
        conn.commit()


def seed_bandit_skills():
    """Seed database with foundational bandit strategies on first run."""
    init_db()
    with sqlite3.connect(SKILLS_DB) as conn:
        cursor = conn.cursor()
        # Check if bandit skills already exist
        cursor.execute("SELECT COUNT(*) FROM skills WHERE tags LIKE '%bandit%'")
        if cursor.fetchone()[0] > 0:
            return  # Already seeded

        bandit_skills = [
            {
                'name': 'SSH to Bandit Level with sshpass',
                'problem': 'Log into bandit challenge with SSH',
                'solution': 'Use sshpass for non-interactive password auth, disable host key checking',
                'template': "sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {user}@bandit.labs.overthewire.org -p 2220 '{command}'",
                'tags': 'bandit,ssh,sshpass,challenge'
            },
            {
                'name': 'Read File with Special Characters in Filename',
                'problem': 'File has dashes or special chars that confuse cat/shell',
                'solution': 'Use ./ prefix for dashes, or -- option separator',
                'template': "cat -- '{filename}'  # or cat ./{filename}",
                'tags': 'bandit,filename,special-chars,cat'
            },
            {
                'name': 'Find File by Size and Properties',
                'problem': 'Need to locate file matching specific size/permissions/type',
                'solution': 'Use find with -size, -type, -perm filters; pipe to file command to check content type',
                'template': "find . -type f -size {size}c ! -executable -exec file {} \\; | grep ASCII",
                'tags': 'bandit,find,file-hunting,permissions'
            },
            {
                'name': 'Decompress Layered Archives',
                'problem': 'File is hex-dumped or multiply compressed (gzip, bzip2, tar)',
                'solution': 'Use xxd -r to reverse hexdump, then decompress layer by layer with gunzip, bzip2 -d, tar',
                'template': "xxd -r data.txt | gunzip | bzip2 -d | tar xf - # Repeat as needed",
                'tags': 'bandit,compression,archive,decompression'
            },
            {
                'name': 'Extract Password from Readme or Special File',
                'problem': 'Password is in a readme or hidden file in home directory',
                'solution': 'Always check for readme, .secret, or other text files; read with cat',
                'template': "cat readme  # or cat .secret or ls -la to find hidden files",
                'tags': 'bandit,password,readme,text-extraction'
            }
        ]

        for skill in bandit_skills:
            cursor.execute("""
                INSERT INTO skills (name, problem, solution, template, tags, source_session)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                skill.get('name'),
                skill.get('problem'),
                skill.get('solution'),
                skill.get('template'),
                skill.get('tags'),
                'bandit-seed'
            ))
            skill_id = cursor.lastrowid
            cursor.execute("""
                INSERT INTO skills_fts (rowid, name, problem, solution, template, tags)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                skill_id,
                skill.get('name'),
                skill.get('problem'),
                skill.get('solution'),
                skill.get('template'),
                skill.get('tags')
            ))
        conn.commit()


def save_skill(skill: dict, source_session: str = None) -> int:
    """
    Save a skill to the database.
    Returns the skill ID.
    """
    init_db()
    with sqlite3.connect(SKILLS_DB) as conn:
        cursor = conn.cursor()
        tags_str = ','.join(skill.get('tags', [])) if isinstance(skill.get('tags'), list) else skill.get('tags', '')
        cursor.execute("""
            INSERT INTO skills (name, problem, solution, template, tags, source_session)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            skill.get('name', 'unnamed'),
            skill.get('problem', ''),
            skill.get('solution', ''),
            skill.get('template', ''),
            tags_str,
            source_session or datetime.now().isoformat()
        ))
        skill_id = cursor.lastrowid
        # Insert into FTS table
        cursor.execute("""
            INSERT INTO skills_fts (rowid, name, problem, solution, template, tags)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            skill_id,
            skill.get('name', 'unnamed'),
            skill.get('problem', ''),
            skill.get('solution', ''),
            skill.get('template', ''),
            tags_str
        ))
        conn.commit()
        return skill_id


def search_skills(query: str, limit: int = 5) -> list[dict]:
    """
    Full-text search on skills by name/problem/solution/template/tags.
    Returns list of skill dicts.
    """
    init_db()
    with sqlite3.connect(SKILLS_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Escape special FTS5 characters and build a safe query
        # Remove problematic characters and use word-based search
        safe_query = re.sub(r'[^\w\s]', ' ', query).strip()
        if not safe_query:
            # If query is all special chars, return top skills
            cursor.execute("""
                SELECT id, name, problem, solution, template, tags, source_session, success_rate, use_count, created_at
                FROM skills
                ORDER BY success_rate DESC, use_count DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

        # Split into words and search for any match
        words = safe_query.split()
        or_clauses = ' OR '.join(f'{word}*' for word in words)

        try:
            cursor.execute(f"""
                SELECT id, name, problem, solution, template, tags, source_session, success_rate, use_count, created_at
                FROM skills
                WHERE id IN (
                    SELECT rowid FROM skills_fts WHERE skills_fts MATCH '{or_clauses}'
                )
                ORDER BY success_rate DESC, use_count DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            # Fallback to simple LIKE search if FTS5 fails
            cursor.execute("""
                SELECT id, name, problem, solution, template, tags, source_session, success_rate, use_count, created_at
                FROM skills
                WHERE name LIKE ? OR tags LIKE ?
                ORDER BY success_rate DESC, use_count DESC
                LIMIT ?
            """, (f'%{safe_query}%', f'%{safe_query}%', limit))
            return [dict(row) for row in cursor.fetchall()]


def get_all_skills(limit: int = 20) -> list[dict]:
    """
    Retrieve all skills, most-used first.
    """
    init_db()
    with sqlite3.connect(SKILLS_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, problem, solution, template, tags, source_session, success_rate, use_count, created_at
            FROM skills
            ORDER BY use_count DESC, success_rate DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def skills_context(query: str = '', limit: int = 5) -> str:
    """
    Format skills into a readable prompt context.
    If query is provided, search first; otherwise return top skills.
    """
    if query:
        skills = search_skills(query, limit=limit)
    else:
        skills = get_all_skills(limit=limit)

    if not skills:
        return ''

    lines = ['PROVEN SKILLS (from previous successful sessions):']
    for skill in skills:
        lines.append(f"\n[{skill['name']}]")
        if skill['problem']:
            lines.append(f"  Problem: {skill['problem']}")
        if skill['solution']:
            lines.append(f"  Solution: {skill['solution']}")
        if skill['template']:
            lines.append(f"  Template: {skill['template']}")
        if skill['tags']:
            lines.append(f"  Tags: {skill['tags']}")
        lines.append(f"  Success rate: {skill['success_rate']:.0%} (used {skill['use_count']} times)")

    return '\n'.join(lines)


def extract_skills_from_session(messages: list, memory: dict, session_id: str, provider, outcome: str = 'success') -> list[dict]:
    """
    Extract reusable skills from a successful session.
    Ask the LLM to summarize the successful steps as reusable techniques.
    """
    if outcome == 'abandoned':
        return []

    # Build a concise summary of the session for the LLM
    session_summary = f"Session: {session_id}\nOutcome: {outcome}\n\n"
    session_summary += "Conversation:\n"
    for msg in messages[-10:]:  # last 10 messages for context
        role = msg['role'].upper()
        content = msg['content'][:300]  # truncate long responses
        session_summary += f"{role}: {content}\n"

    if memory.get('networks') or memory.get('credentials'):
        session_summary += "\nLearned state:\n"
        if memory.get('networks'):
            session_summary += f"Networks: {json.dumps(memory['networks'])}\n"
        if memory.get('credentials'):
            session_summary += f"Credentials: {len(memory.get('credentials', {}))} found\n"

    extraction_prompt = f"""{session_summary}

Based on this session, extract 1-3 reusable skills as JSON.
Return ONLY valid JSON array (no markdown, no explanation):
[
  {{
    "name": "skill name",
    "problem": "what problem it solves",
    "solution": "how it solves it",
    "template": "shell command or code template with {{placeholders}}",
    "tags": ["tag1", "tag2"]
  }}
]

If no reusable skills, return [].
"""

    try:
        response = provider.chat(
            [{'role': 'user', 'content': extraction_prompt}],
            system="You are a cybersecurity expert. Extract reusable attack/defense techniques from security sessions."
        )

        # Try to extract JSON from response
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            skills_data = json.loads(json_match.group(0))
            saved_skills = []
            for skill in skills_data:
                skill_id = save_skill(skill, source_session=session_id)
                saved_skills.append(skill)
                print(f"✓ Learned skill: {skill.get('name', 'unnamed')}")
            return saved_skills
    except (json.JSONDecodeError, AttributeError, Exception) as e:
        pass  # Silent fail: skill extraction is a bonus, not critical

    return []


def migrate_techniques_json(techniques_file: Path):
    """
    One-time migration: import existing techniques.json into skills.db.
    """
    if not techniques_file.exists():
        return

    try:
        with open(techniques_file, 'r') as f:
            data = json.load(f)

        techniques = data.get('techniques', {})
        init_db()

        with sqlite3.connect(SKILLS_DB) as conn:
            cursor = conn.cursor()
            for tech_id, tech_data in techniques.items():
                cursor.execute("""
                    INSERT OR IGNORE INTO skills (name, problem, solution, template, tags, source_session, success_rate)
                    VALUES (?, ?, ?, ?, ?, 'migrated_from_techniques.json', ?)
                """, (
                    tech_data.get('name', tech_id),
                    tech_data.get('problem', ''),
                    tech_data.get('solution', ''),
                    tech_data.get('template', ''),
                    ','.join(tech_data.get('tags', [])) if isinstance(tech_data.get('tags'), list) else '',
                    0.8 if tech_data.get('success_rate') == 'high' else 0.6
                ))
                skill_id = cursor.lastrowid
                # Insert into FTS table
                cursor.execute("""
                    INSERT INTO skills_fts (rowid, name, problem, solution, template, tags)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    skill_id,
                    tech_data.get('name', tech_id),
                    tech_data.get('problem', ''),
                    tech_data.get('solution', ''),
                    tech_data.get('template', ''),
                    ','.join(tech_data.get('tags', [])) if isinstance(tech_data.get('tags'), list) else ''
                ))
            conn.commit()

        print(f"✓ Migrated {len(techniques)} techniques from techniques.json to skills.db")
    except Exception as e:
        print(f"Migration warning: {e}")


if __name__ == '__main__':
    # Test
    init_db()
    print(f"Skills DB at: {SKILLS_DB}")
    print(f"Total skills: {len(get_all_skills(999))}")
