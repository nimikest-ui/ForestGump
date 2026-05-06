#!/usr/bin/env python3
"""
Enhanced memory system for ForestGump with FTS5 search and AI-driven synthesis.
Extends the flat memory.json with searchable, confidence-scored entries.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

MEMORY_DB = Path(__file__).parent / 'memory.db'
MEMORY_JSON = Path(__file__).parent / 'memory.json'


def init_db():
    """Initialize memory database with schema if not present."""
    with sqlite3.connect(MEMORY_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL DEFAULT 0.8,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                summary TEXT,
                source_session TEXT
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                content, tags, type,
                content='memory', content_rowid='id'
            )
        """)
        conn.commit()


def save_memory(
    content: str,
    type_: str = 'fact',
    confidence: float = 0.8,
    tags: Optional[List[str]] = None,
    summary: Optional[str] = None,
    source_session: Optional[str] = None,
) -> int:
    """
    Save a memory entry to the database.

    Args:
        content: The memory content
        type_: Type of memory (fact, network, credential, insight, technique)
        confidence: Confidence score (0.0-1.0)
        tags: List of tag strings
        summary: AI-generated summary of the entry
        source_session: Session ID where this was learned

    Returns:
        Memory ID
    """
    init_db()
    tags_str = ','.join(tags) if tags else ''

    with sqlite3.connect(MEMORY_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory (type, content, confidence, tags, summary, source_session, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (type_, content, confidence, tags_str, summary, source_session, datetime.now().isoformat()))

        mem_id = cursor.lastrowid

        # Insert into FTS table
        cursor.execute("""
            INSERT INTO memory_fts (rowid, content, tags, type)
            VALUES (?, ?, ?, ?)
        """, (mem_id, content, tags_str, type_))

        conn.commit()
        return mem_id


def search_memory(query: str, limit: int = 10, type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Full-text search on memory entries.

    Args:
        query: Search query
        limit: Max results
        type_filter: Filter by type (fact, network, credential, etc.)

    Returns:
        List of memory entry dicts
    """
    init_db()
    with sqlite3.connect(MEMORY_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        where_clause = 'WHERE memory_fts MATCH ?' if query else ''
        if type_filter:
            where_clause += f" {'AND' if where_clause else 'WHERE'} type = ?"

        if query and type_filter:
            cursor.execute(f"""
                SELECT m.id, m.type, m.content, m.confidence, m.tags, m.summary, m.created_at
                FROM memory m
                JOIN memory_fts f ON m.id = f.rowid
                {where_clause}
                ORDER BY m.confidence DESC, m.last_used_at DESC
                LIMIT ?
            """, (query, type_filter, limit))
        elif query:
            cursor.execute(f"""
                SELECT m.id, m.type, m.content, m.confidence, m.tags, m.summary, m.created_at
                FROM memory m
                JOIN memory_fts f ON m.id = f.rowid
                {where_clause}
                ORDER BY m.confidence DESC, m.last_used_at DESC
                LIMIT ?
            """, (query, limit))
        elif type_filter:
            cursor.execute(f"""
                SELECT id, type, content, confidence, tags, summary, created_at
                FROM memory
                {where_clause}
                ORDER BY confidence DESC, last_used_at DESC
                LIMIT ?
            """, (type_filter, limit))
        else:
            cursor.execute("""
                SELECT id, type, content, confidence, tags, summary, created_at
                FROM memory
                ORDER BY confidence DESC, last_used_at DESC
                LIMIT ?
            """, (limit,))

        return [dict(row) for row in cursor.fetchall()]


def update_confidence(memory_id: int, new_confidence: float) -> None:
    """Update confidence score for a memory entry."""
    with sqlite3.connect(MEMORY_DB) as conn:
        conn.execute("""
            UPDATE memory
            SET confidence = ?, last_used_at = ?
            WHERE id = ?
        """, (new_confidence, datetime.now().isoformat(), memory_id))
        conn.commit()


def touch_memory(memory_id: int) -> None:
    """Update last_used_at timestamp for a memory entry."""
    with sqlite3.connect(MEMORY_DB) as conn:
        conn.execute("""
            UPDATE memory
            SET last_used_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), memory_id))
        conn.commit()


def get_memory(memory_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a specific memory entry by ID."""
    init_db()
    with sqlite3.connect(MEMORY_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, type, content, confidence, tags, summary, created_at, last_used_at
            FROM memory
            WHERE id = ?
        """, (memory_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_by_type(type_: str) -> List[Dict[str, Any]]:
    """Get all memory entries of a specific type."""
    init_db()
    with sqlite3.connect(MEMORY_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, type, content, confidence, tags, summary, created_at
            FROM memory
            WHERE type = ?
            ORDER BY confidence DESC, last_used_at DESC
        """, (type_,))
        return [dict(row) for row in cursor.fetchall()]


def load_legacy_memory() -> Dict[str, Any]:
    """Load legacy memory.json for migration."""
    if MEMORY_JSON.exists():
        with open(MEMORY_JSON, 'r') as f:
            return json.load(f)
    return {}


def migrate_from_json() -> None:
    """Migrate from legacy memory.json to new memory.db."""
    legacy = load_legacy_memory()
    if not legacy:
        return

    # Only migrate if database is empty
    with sqlite3.connect(MEMORY_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memory")
        if cursor.fetchone()[0] > 0:
            return  # Already migrated

    # Migrate facts
    for fact in legacy.get('facts', []):
        save_memory(fact, type_='fact', source_session='migration')

    # Migrate networks
    for ssid, net_data in legacy.get('networks', {}).items():
        content = f"{ssid}: {json.dumps(net_data)}"
        save_memory(content, type_='network', tags=[ssid], source_session='migration')

    # Migrate credentials
    for target, cred_data in legacy.get('credentials', {}).items():
        content = f"{target}: {json.dumps(cred_data)}"
        save_memory(content, type_='credential', tags=[target], source_session='migration')

    # Migrate notes
    for note in legacy.get('notes', []):
        save_memory(note, type_='insight', source_session='migration')


def get_memory_context() -> str:
    """
    Get a human-readable memory summary for agent prompts.

    Returns:
        Formatted string of all memories for inclusion in system prompt
    """
    init_db()
    with sqlite3.connect(MEMORY_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT type, content, confidence
            FROM memory
            ORDER BY type, confidence DESC
        """)

        memories = {}
        for row in cursor.fetchall():
            type_ = row['type']
            if type_ not in memories:
                memories[type_] = []
            memories[type_].append((row['content'], row['confidence']))

    if not memories:
        return ''

    lines = ['[PERSISTENT MEMORY]']
    for type_, entries in sorted(memories.items()):
        lines.append(f'\n{type_.upper()}:')
        for content, conf in entries:
            lines.append(f'  - {content} (confidence: {conf:.1f})')

    return '\n'.join(lines)
