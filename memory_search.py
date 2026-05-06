#!/usr/bin/env python3
"""
Advanced memory search with semantic capabilities.
Supports full-text search, filtering, and similarity matching.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

import memory_manager


@dataclass
class SearchResult:
    """Result from a memory search."""

    memory_id: int
    type: str
    content: str
    confidence: float
    tags: str
    similarity_score: float  # 0.0-1.0
    created_at: str
    relevance_rank: int  # Rank in result set


class AdvancedMemorySearch:
    """Advanced search on persistent memory."""

    def __init__(self):
        """Initialize advanced search."""
        self.memory_db = memory_manager.MEMORY_DB

    def search_by_type(
        self,
        type_filter: str,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> List[SearchResult]:
        """Search memories by type."""
        with sqlite3.connect(self.memory_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, type, content, confidence, tags, created_at
                FROM memory
                WHERE type = ? AND confidence >= ?
                ORDER BY confidence DESC, last_used_at DESC
                LIMIT ?
            """, (type_filter, min_confidence, limit))

            results = []
            for rank, row in enumerate(cursor.fetchall(), 1):
                results.append(
                    SearchResult(
                        memory_id=row['id'],
                        type=row['type'],
                        content=row['content'],
                        confidence=row['confidence'],
                        tags=row['tags'] or '',
                        similarity_score=row['confidence'],  # Use confidence as initial score
                        created_at=row['created_at'],
                        relevance_rank=rank,
                    )
                )

            return results

    def search_by_tags(
        self,
        tags: List[str],
        limit: int = 10,
        match_all: bool = False,
    ) -> List[SearchResult]:
        """
        Search memories by tags.

        Args:
            tags: List of tags to search for
            limit: Max results
            match_all: If True, require ALL tags; if False, require ANY tag

        Returns:
            List of search results
        """
        with sqlite3.connect(self.memory_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build query
            tag_conditions = []
            for tag in tags:
                tag_conditions.append(f"tags LIKE '%{tag}%'")

            if match_all:
                where_clause = ' AND '.join(tag_conditions)
            else:
                where_clause = ' OR '.join(tag_conditions)

            query = f"""
                SELECT id, type, content, confidence, tags, created_at
                FROM memory
                WHERE {where_clause}
                ORDER BY confidence DESC
                LIMIT ?
            """

            cursor.execute(query, (limit,))

            results = []
            for rank, row in enumerate(cursor.fetchall(), 1):
                results.append(
                    SearchResult(
                        memory_id=row['id'],
                        type=row['type'],
                        content=row['content'],
                        confidence=row['confidence'],
                        tags=row['tags'] or '',
                        similarity_score=row['confidence'],
                        created_at=row['created_at'],
                        relevance_rank=rank,
                    )
                )

            return results

    def search_by_recency(
        self,
        days: int = 7,
        type_filter: Optional[str] = None,
        limit: int = 10,
    ) -> List[SearchResult]:
        """Search for memories created in the last N days."""
        cutoff = datetime.now() - timedelta(days=days)

        with sqlite3.connect(self.memory_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if type_filter:
                cursor.execute("""
                    SELECT id, type, content, confidence, tags, created_at
                    FROM memory
                    WHERE type = ? AND created_at >= ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (type_filter, cutoff.isoformat(), limit))
            else:
                cursor.execute("""
                    SELECT id, type, content, confidence, tags, created_at
                    FROM memory
                    WHERE created_at >= ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (cutoff.isoformat(), limit))

            results = []
            for rank, row in enumerate(cursor.fetchall(), 1):
                results.append(
                    SearchResult(
                        memory_id=row['id'],
                        type=row['type'],
                        content=row['content'],
                        confidence=row['confidence'],
                        tags=row['tags'] or '',
                        similarity_score=row['confidence'],
                        created_at=row['created_at'],
                        relevance_rank=rank,
                    )
                )

            return results

    def search_high_confidence(
        self,
        min_confidence: float = 0.8,
        limit: int = 20,
    ) -> List[SearchResult]:
        """Search for high-confidence memories."""
        with sqlite3.connect(self.memory_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, type, content, confidence, tags, created_at
                FROM memory
                WHERE confidence >= ?
                ORDER BY confidence DESC, last_used_at DESC
                LIMIT ?
            """, (min_confidence, limit))

            results = []
            for rank, row in enumerate(cursor.fetchall(), 1):
                results.append(
                    SearchResult(
                        memory_id=row['id'],
                        type=row['type'],
                        content=row['content'],
                        confidence=row['confidence'],
                        tags=row['tags'] or '',
                        similarity_score=row['confidence'],
                        created_at=row['created_at'],
                        relevance_rank=rank,
                    )
                )

            return results

    def search_unused(
        self,
        days_since_use: int = 30,
        limit: int = 10,
    ) -> List[SearchResult]:
        """Find memories that haven't been used in N days (good candidates for updating)."""
        cutoff = datetime.now() - timedelta(days=days_since_use)

        with sqlite3.connect(self.memory_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, type, content, confidence, tags, created_at
                FROM memory
                WHERE last_used_at IS NULL OR last_used_at < ?
                ORDER BY last_used_at ASC
                LIMIT ?
            """, (cutoff.isoformat(), limit))

            results = []
            for rank, row in enumerate(cursor.fetchall(), 1):
                results.append(
                    SearchResult(
                        memory_id=row['id'],
                        type=row['type'],
                        content=row['content'],
                        confidence=row['confidence'],
                        tags=row['tags'] or '',
                        similarity_score=row['confidence'],
                        created_at=row['created_at'],
                        relevance_rank=rank,
                    )
                )

            return results

    def compound_search(
        self,
        query: Optional[str] = None,
        type_filter: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> List[SearchResult]:
        """
        Compound search with multiple criteria.

        Args:
            query: Full-text search query
            type_filter: Filter by memory type
            tags: Filter by tags (any tag)
            min_confidence: Minimum confidence threshold
            limit: Max results

        Returns:
            Ranked list of results
        """
        with sqlite3.connect(self.memory_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build WHERE clause
            where_parts = [f"confidence >= {min_confidence}"]

            if type_filter:
                where_parts.append(f"type = '{type_filter}'")

            if tags:
                tag_conditions = [f"tags LIKE '%{tag}%'" for tag in tags]
                where_parts.append(f"({' OR '.join(tag_conditions)})")

            where_clause = " AND ".join(where_parts)

            # Query
            if query:
                # FTS5 search + additional filters
                cursor.execute(f"""
                    SELECT m.id, m.type, m.content, m.confidence, m.tags, m.created_at
                    FROM memory m
                    WHERE m.id IN (
                        SELECT rowid FROM memory_fts WHERE memory_fts MATCH ?
                    ) AND {where_clause}
                    ORDER BY m.confidence DESC
                    LIMIT ?
                """, (query, limit))
            else:
                cursor.execute(f"""
                    SELECT id, type, content, confidence, tags, created_at
                    FROM memory
                    WHERE {where_clause}
                    ORDER BY confidence DESC
                    LIMIT ?
                """, (limit,))

            results = []
            for rank, row in enumerate(cursor.fetchall(), 1):
                results.append(
                    SearchResult(
                        memory_id=row['id'],
                        type=row['type'],
                        content=row['content'],
                        confidence=row['confidence'],
                        tags=row['tags'] or '',
                        similarity_score=row['confidence'],
                        created_at=row['created_at'],
                        relevance_rank=rank,
                    )
                )

            return results

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics on memory database."""
        with sqlite3.connect(self.memory_db) as conn:
            cursor = conn.cursor()

            # Total count
            cursor.execute("SELECT COUNT(*) FROM memory")
            total = cursor.fetchone()[0]

            # By type
            cursor.execute("""
                SELECT type, COUNT(*) as count
                FROM memory
                GROUP BY type
            """)
            by_type = {row[0]: row[1] for row in cursor.fetchall()}

            # Confidence distribution
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN confidence >= 0.9 THEN 1 ELSE 0 END) as high_conf,
                    SUM(CASE WHEN confidence >= 0.7 AND confidence < 0.9 THEN 1 ELSE 0 END) as med_conf,
                    SUM(CASE WHEN confidence < 0.7 THEN 1 ELSE 0 END) as low_conf,
                    AVG(confidence) as avg_conf
                FROM memory
            """)
            row = cursor.fetchone()
            confidence = {
                'high': row[0] or 0,
                'medium': row[1] or 0,
                'low': row[2] or 0,
            }

            return {
                'total_memories': total,
                'by_type': by_type,
                'confidence_distribution': confidence,
                'avg_confidence': row[3] or 0.0,
            }

    def print_stats(self) -> str:
        """Print memory statistics."""
        stats = self.get_memory_stats()

        lines = [
            theme.banner("📊 Memory Statistics"),
            f"  Total memories: {stats['total_memories']}",
        ]

        if stats['by_type']:
            lines.append("  By type:")
            for type_, count in stats['by_type'].items():
                lines.append(f"    • {type_}: {count}")

        conf = stats['confidence_distribution']
        lines.append(f"  Confidence distribution:")
        lines.append(f"    • High (≥0.9): {conf['high']}")
        lines.append(f"    • Medium (0.7-0.9): {conf['medium']}")
        lines.append(f"    • Low (<0.7): {conf['low']}")

        return "\n".join(lines)
