#!/usr/bin/env python3
"""
Enhanced skill database with versioning and improvement tracking.
Supersedes the basic skills.py with more sophisticated ranking and feedback.
"""

import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

SKILLS_DB = Path(__file__).parent / 'skills.db'


def init_db():
    """Initialize skills database with enhanced schema."""
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
                version INTEGER DEFAULT 1,
                success_rate REAL DEFAULT 0.8,
                use_count INTEGER DEFAULT 0,
                best_session_turns INTEGER,
                preconditions TEXT,
                expected_output TEXT,
                failure_modes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                archived INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
                name, problem, solution, template, tags,
                content='skills', content_rowid='id'
            )
        """)

        # Schema migration: add missing columns to existing tables
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(skills)")
        columns = {row[1] for row in cursor.fetchall()}

        missing_columns = [
            ('version', 'INTEGER DEFAULT 1'),
            ('best_session_turns', 'INTEGER'),
            ('preconditions', 'TEXT'),
            ('expected_output', 'TEXT'),
            ('failure_modes', 'TEXT'),
            ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
            ('archived', 'INTEGER DEFAULT 0'),
        ]

        for col_name, col_def in missing_columns:
            if col_name not in columns:
                try:
                    conn.execute(f"ALTER TABLE skills ADD COLUMN {col_name} {col_def}")
                except sqlite3.OperationalError:
                    pass  # Column already exists or other error

        conn.commit()


def save_skill(skill: Dict[str, Any], source_session: str = None) -> int:
    """
    Save or update a skill with enhanced metadata.

    Args:
        skill: Skill dict with name, problem, solution, template, tags, etc.
        source_session: Session where skill was learned

    Returns:
        Skill ID
    """
    init_db()
    tags_str = ','.join(skill.get('tags', [])) if isinstance(skill.get('tags'), list) else skill.get('tags', '')

    with sqlite3.connect(SKILLS_DB) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO skills (
                name, problem, solution, template, tags, source_session,
                preconditions, expected_output, failure_modes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            skill.get('name', 'unnamed'),
            skill.get('problem', ''),
            skill.get('solution', ''),
            skill.get('template', ''),
            tags_str,
            source_session or datetime.now().isoformat(),
            skill.get('preconditions'),
            skill.get('expected_output'),
            skill.get('failure_modes')
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


def search_skills(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Full-text search on skills ranked by efficiency.

    Efficiency = (success_rate * use_count * 100) - best_session_turns
    Higher score = faster, more reliable skill.

    Args:
        query: Search query
        limit: Max results

    Returns:
        List of skill dicts sorted by efficiency
    """
    init_db()
    with sqlite3.connect(SKILLS_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Safe FTS5 query: escape special characters
        safe_query = re.sub(r'[":*]', '', query).strip()
        if not safe_query:
            return []

        cursor.execute("""
            SELECT
                s.id, s.name, s.problem, s.solution, s.template, s.tags,
                s.success_rate, s.use_count, s.best_session_turns,
                s.preconditions, s.expected_output, s.failure_modes,
                (s.success_rate * MAX(1, s.use_count) * 100) - COALESCE(s.best_session_turns, 999) as efficiency
            FROM skills s
            WHERE s.id IN (
                SELECT rowid FROM skills_fts WHERE skills_fts MATCH ?
            ) AND s.archived = 0
            ORDER BY efficiency DESC, s.success_rate DESC
            LIMIT ?
        """, (safe_query, limit))

        return [dict(row) for row in cursor.fetchall()]


def update_skill_feedback(skill_id: int, success: bool, session_turns: int) -> None:
    """
    Update skill feedback after use (EWMA update).

    Args:
        skill_id: Skill to update
        success: Whether the skill worked
        session_turns: How many turns it took
    """
    with sqlite3.connect(SKILLS_DB) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT success_rate, use_count, best_session_turns
            FROM skills
            WHERE id = ?
        """, (skill_id,))

        row = cursor.fetchone()
        if not row:
            return

        old_rate, use_count, best_turns = row
        new_count = use_count + 1
        success_val = 1.0 if success else 0.0

        # EWMA update (alpha=0.3)
        alpha = 0.3
        new_rate = old_rate * (1 - alpha) + success_val * alpha

        # Update best_turns if this was faster
        best_turns = min(best_turns or 999, session_turns) if success else best_turns

        cursor.execute("""
            UPDATE skills
            SET success_rate = ?, use_count = ?, best_session_turns = ?, updated_at = ?
            WHERE id = ?
        """, (new_rate, new_count, best_turns, datetime.now().isoformat(), skill_id))

        conn.commit()


def get_skill(skill_id: int) -> Optional[Dict[str, Any]]:
    """Get a skill by ID."""
    with sqlite3.connect(SKILLS_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM skills WHERE id = ?
        """, (skill_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_all_skills(archived: bool = False) -> List[Dict[str, Any]]:
    """List all skills, optionally including archived ones."""
    init_db()
    with sqlite3.connect(SKILLS_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM skills
            WHERE archived = ?
            ORDER BY success_rate DESC, use_count DESC
        """, (1 if archived else 0,))
        return [dict(row) for row in cursor.fetchall()]


def archive_skill(skill_id: int) -> None:
    """Archive a skill (hide from searches but keep in DB)."""
    with sqlite3.connect(SKILLS_DB) as conn:
        conn.execute("""
            UPDATE skills
            SET archived = 1, updated_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), skill_id))
        conn.commit()


def skills_context(task_description: str, limit: int = 5, is_haiku: bool = False) -> str:
    """
    Get skills context for agent prompt.

    Searches for relevant skills based on task and formats them
    for inclusion in the system prompt.

    Args:
        task_description: The task the agent is solving
        limit: Max skills to return (default: 5; reduced to 2 for Haiku)
        is_haiku: Whether using Haiku model (auto-adjusts limit)

    Returns:
        Formatted string of top N relevant skills
    """
    if is_haiku and limit == 5:
        limit = 2

    skills = search_skills(task_description, limit=limit)
    if not skills:
        return ''

    lines = ['[PROVEN SKILLS (from previous sessions)]']
    for skill in skills:
        lines.append(f"\n{skill['name']} (success: {skill['success_rate']:.0%}, used {skill['use_count']}x)")
        if skill['problem']:
            lines.append(f"  Problem: {skill['problem']}")
        if skill['solution']:
            lines.append(f"  Solution: {skill['solution']}")
        if skill['template']:
            lines.append(f"  Template: {skill['template']}")

    return '\n'.join(lines)


def extract_skills_from_session(session_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract learned skills from a completed session.

    Looks for [SKILL] markers in agent responses to auto-populate the database.

    Args:
        session_data: Session JSON dict

    Returns:
        List of extracted skills
    """
    extracted = []
    if 'messages' not in session_data:
        return extracted

    for message in session_data['messages']:
        if message.get('role') != 'assistant':
            continue

        content = message.get('content', '')
        # Look for [SKILL] blocks
        skill_blocks = re.findall(r'\[SKILL\](.*?)\[/SKILL\]', content, re.DOTALL)

        for block in skill_blocks:
            try:
                skill_data = json.loads(block.strip())
                if 'name' in skill_data and 'problem' in skill_data:
                    extracted.append(skill_data)
            except json.JSONDecodeError:
                pass

    return extracted


def migrate_techniques_json() -> None:
    """Migrate from old techniques.json to new skills.db (one-time)."""
    techniques_file = Path(__file__).parent / 'techniques.json'
    if not techniques_file.exists():
        return

    # Check if already migrated
    with sqlite3.connect(SKILLS_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM skills WHERE source_session = 'migrated-from-techniques'")
        if cursor.fetchone()[0] > 0:
            return  # Already migrated

    # Load and migrate
    with open(techniques_file, 'r') as f:
        techniques = json.load(f)

    for tech_id, tech_data in techniques.items():
        save_skill({
            'name': tech_data.get('name', tech_id),
            'problem': tech_data.get('problem', ''),
            'solution': tech_data.get('solution', ''),
            'template': tech_data.get('template', ''),
            'tags': tech_data.get('tags', [])
        }, source_session='migrated-from-techniques')


def seed_bandit_skills():
    """Seed database with foundational bandit strategies on first run."""
    init_db()
    with sqlite3.connect(SKILLS_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM skills WHERE tags LIKE '%bandit%'")
        if cursor.fetchone()[0] > 0:
            return

        bandit_skills = [
            {
                'name': 'SSH Bandit with sshpass',
                'problem': 'SSH into bandit level without interactive prompt',
                'solution': 'Use sshpass for non-interactive authentication',
                'template': "sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {user}@bandit.labs.overthewire.org -p 2220",
                'tags': ['bandit', 'ssh', 'sshpass'],
                'preconditions': 'sshpass installed; valid credentials known'
            },
            {
                'name': 'Read Files with Special Chars',
                'problem': 'File has dashes/special characters that confuse cat',
                'solution': 'Use ./ prefix or -- separator to prevent interpretation as flags',
                'template': "cat -- '{filename}'",
                'tags': ['bandit', 'filename', 'cat'],
                'failure_modes': 'Filename starts with dash; interpreted as flag'
            },
            {
                'name': 'Decompress Layered Archives',
                'problem': 'File is hex-encoded, gzipped, and tar-archived',
                'solution': 'Chain xxd, gunzip, and tar in pipeline',
                'template': "xxd -r {file} | gunzip | tar xf -",
                'tags': ['bandit', 'compression', 'archive']
            }
        ]

        for skill in bandit_skills:
            save_skill(skill, source_session='bandit-seed')
