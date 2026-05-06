#!/usr/bin/env python3
"""
Monitoring and metrics dashboard for ForestGump.
Tracks agent performance, resource usage, and success rates.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from collections import defaultdict, deque

import theme


@dataclass
class MetricPoint:
    """Single data point for a metric."""

    timestamp: float
    value: float


@dataclass
class SessionMetrics:
    """Metrics from a single session."""

    session_id: str
    task: str
    provider: str
    model: str
    start_time: float
    end_time: Optional[float] = None
    duration_seconds: float = 0.0
    total_turns: int = 0
    tokens_used: int = 0
    commands_executed: int = 0
    success: bool = False
    error_message: Optional[str] = None


class MetricsCollector:
    """Collect and aggregate metrics from agent sessions."""

    METRICS_FILE = Path(__file__).parent / 'metrics.json'
    MAX_HISTORY = 1000  # Keep last N sessions

    def __init__(self):
        """Initialize metrics collector."""
        self.sessions: deque[SessionMetrics] = deque(maxlen=self.MAX_HISTORY)
        self.current_session: Optional[SessionMetrics] = None
        self.load_metrics()

    def start_session(
        self,
        session_id: str,
        task: str,
        provider: str,
        model: str,
    ) -> None:
        """Start tracking a new session."""
        self.current_session = SessionMetrics(
            session_id=session_id,
            task=task,
            provider=provider,
            model=model,
            start_time=time.time(),
        )

    def end_session(self, success: bool = True, error: Optional[str] = None) -> None:
        """End current session tracking."""
        if not self.current_session:
            return

        self.current_session.end_time = time.time()
        self.current_session.duration_seconds = (
            self.current_session.end_time - self.current_session.start_time
        )
        self.current_session.success = success
        self.current_session.error_message = error

        self.sessions.append(self.current_session)
        self.save_metrics()
        self.current_session = None

    def record_turn(self, turn: int) -> None:
        """Record a turn completion."""
        if self.current_session:
            self.current_session.total_turns = turn

    def record_tokens(self, tokens: int) -> None:
        """Record token usage."""
        if self.current_session:
            self.current_session.tokens_used = tokens

    def record_command(self) -> None:
        """Record command execution."""
        if self.current_session:
            self.current_session.commands_executed += 1

    def get_success_rate(self, hours: int = 24) -> float:
        """Get success rate for last N hours."""
        cutoff = time.time() - (hours * 3600)
        recent = [s for s in self.sessions if s.end_time and s.end_time > cutoff]

        if not recent:
            return 0.0

        successes = sum(1 for s in recent if s.success)
        return successes / len(recent)

    def get_avg_duration(self, hours: int = 24) -> float:
        """Get average session duration for last N hours."""
        cutoff = time.time() - (hours * 3600)
        recent = [
            s
            for s in self.sessions
            if s.end_time and s.end_time > cutoff and s.duration_seconds > 0
        ]

        if not recent:
            return 0.0

        return sum(s.duration_seconds for s in recent) / len(recent)

    def get_provider_stats(self, hours: int = 24) -> Dict[str, Dict[str, Any]]:
        """Get stats per provider."""
        cutoff = time.time() - (hours * 3600)
        recent = [s for s in self.sessions if s.end_time and s.end_time > cutoff]

        stats = defaultdict(
            lambda: {"count": 0, "success": 0, "avg_duration": 0, "avg_tokens": 0}
        )

        for session in recent:
            provider = session.provider
            stats[provider]["count"] += 1
            if session.success:
                stats[provider]["success"] += 1
            stats[provider]["avg_duration"] += session.duration_seconds
            stats[provider]["avg_tokens"] += session.tokens_used

        # Calculate averages
        for provider, data in stats.items():
            if data["count"] > 0:
                data["avg_duration"] /= data["count"]
                data["avg_tokens"] /= data["count"]
                data["success_rate"] = data["success"] / data["count"]

        return dict(stats)

    def get_task_frequency(self, hours: int = 24, limit: int = 10) -> List[tuple]:
        """Get most frequent task types."""
        cutoff = time.time() - (hours * 3600)
        recent = [s for s in self.sessions if s.end_time and s.end_time > cutoff]

        task_counts = defaultdict(int)
        for session in recent:
            task_counts[session.task[:50]] += 1  # Truncate for grouping

        return sorted(task_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

    def get_error_summary(self, hours: int = 24) -> Dict[str, int]:
        """Get summary of errors in last N hours."""
        cutoff = time.time() - (hours * 3600)
        recent = [
            s
            for s in self.sessions
            if s.end_time and s.end_time > cutoff and s.error_message
        ]

        errors = defaultdict(int)
        for session in recent:
            # Truncate error message for grouping
            error_type = session.error_message[:40] if session.error_message else "unknown"
            errors[error_type] += 1

        return dict(errors)

    def load_metrics(self) -> None:
        """Load metrics from disk."""
        if not self.METRICS_FILE.exists():
            return

        try:
            with open(self.METRICS_FILE, 'r') as f:
                data = json.load(f)
                for item in data[-self.MAX_HISTORY:]:
                    session = SessionMetrics(**item)
                    self.sessions.append(session)
        except Exception:
            pass

    def save_metrics(self) -> None:
        """Save metrics to disk."""
        try:
            with open(self.METRICS_FILE, 'w') as f:
                data = [asdict(s) for s in self.sessions]
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def print_dashboard(self, hours: int = 24) -> str:
        """Print a metrics dashboard."""
        lines = [theme.banner(f"📊 Metrics Dashboard (Last {hours}h)")]

        # Success rate
        sr = self.get_success_rate(hours)
        sr_icon = "✅" if sr >= 0.8 else "⚠️" if sr >= 0.5 else "❌"
        lines.append(f"\n{sr_icon} Success Rate: {sr:.1%}")

        # Avg duration
        avg_dur = self.get_avg_duration(hours)
        lines.append(f"⏱️  Avg Duration: {avg_dur:.1f}s")

        # Provider stats
        provider_stats = self.get_provider_stats(hours)
        if provider_stats:
            lines.append("\n📡 Provider Stats:")
            for provider, stats in sorted(provider_stats.items()):
                lines.append(
                    f"  • {provider}: {stats['count']} runs, "
                    f"{stats['success_rate']:.0%} success, "
                    f"{stats['avg_duration']:.1f}s avg"
                )

        # Top tasks
        top_tasks = self.get_task_frequency(hours, limit=5)
        if top_tasks:
            lines.append("\n🎯 Top Tasks:")
            for task, count in top_tasks:
                lines.append(f"  • {task}: {count} times")

        # Errors
        errors = self.get_error_summary(hours)
        if errors:
            lines.append("\n⚠️  Recent Errors:")
            for error, count in sorted(errors.items(), key=lambda x: x[1], reverse=True)[
                :5
            ]:
                lines.append(f"  • {error}: {count} times")
        else:
            lines.append("\n✅ No errors!")

        return "\n".join(lines)


# Global collector instance
_collector: Optional[MetricsCollector] = None


def get_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
