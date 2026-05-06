#!/usr/bin/env python3
"""
Subagent spawning system for parallel task execution.
Allows the main agent to spawn child agents for concurrent work.
"""

import threading
import uuid
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime

import theme


class SubagentStatus(Enum):
    """Status of a subagent execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class SubagentTask:
    """Represents a subagent task."""

    id: str
    parent_task: str
    description: str
    provider: str
    model: Optional[str] = None
    priority: int = 0  # 0 = normal, 1 = high, -1 = low
    status: str = SubagentStatus.PENDING.value
    created_at: str = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    tokens_used: int = 0


class SubagentManager:
    """Manage parallel subagent execution."""

    MAX_CONCURRENT = 5  # Limit concurrent subagents
    TIMEOUT_SECONDS = 300  # 5 minutes per subagent

    def __init__(self):
        """Initialize manager."""
        self.tasks: Dict[str, SubagentTask] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.results: Dict[str, Any] = {}
        self.lock = threading.Lock()
        self.active_count = 0

    def spawn(
        self,
        parent_task: str,
        description: str,
        provider: str,
        model: Optional[str] = None,
        priority: int = 0,
        callback: Optional[Callable] = None,
    ) -> Optional[str]:
        """
        Spawn a subagent for a task.

        Args:
            parent_task: ID of parent task
            description: Task description for subagent
            provider: LLM provider (claude, ollama, anthropic, copilot)
            model: Model override
            priority: Task priority (0=normal, 1=high, -1=low)
            callback: Optional callback when task completes

        Returns:
            Subagent task ID, or None if unable to spawn
        """
        task_id = None

        with self.lock:
            # Check if we can spawn
            if self.active_count >= self.MAX_CONCURRENT:
                return None  # Can't spawn; at limit

            task_id = str(uuid.uuid4())[:8]

            task = SubagentTask(
                id=task_id,
                parent_task=parent_task,
                description=description,
                provider=provider,
                model=model,
                priority=priority,
                created_at=datetime.now().isoformat(),
            )

            self.tasks[task_id] = task
            self.active_count += 1

        # Spawn thread outside lock
        thread = threading.Thread(
            target=self._run_subagent,
            args=(task_id, callback),
            daemon=True,
        )
        thread.start()
        self.threads[task_id] = thread

        return task_id

    def _run_subagent(self, task_id: str, callback: Optional[Callable]) -> None:
        """Run a subagent in a thread."""
        try:
            task = self.tasks[task_id]

            # Mark as running
            with self.lock:
                task.status = SubagentStatus.RUNNING.value
                task.started_at = datetime.now().isoformat()

            # Import agent here to avoid circular dependency
            from agent import run_agent

            # Run the agent
            result = run_agent(
                task=task.description,
                provider=task.provider,
                model=task.model,
                max_turns=20,  # Limit turns for subagents
            )

            # Mark as completed
            with self.lock:
                task.status = SubagentStatus.COMPLETED.value
                task.completed_at = datetime.now().isoformat()
                task.result = str(result) if result else "completed"
                self.results[task_id] = result

        except Exception as e:
            # Mark as failed
            with self.lock:
                task.status = SubagentStatus.FAILED.value
                task.completed_at = datetime.now().isoformat()
                task.error = str(e)
                self.results[task_id] = None

        finally:
            # Decrement active count
            with self.lock:
                self.active_count -= 1

            # Call callback if provided
            if callback:
                try:
                    callback(task_id, self.tasks[task_id])
                except Exception:
                    pass

    def wait_for(self, task_id: str, timeout: Optional[float] = None) -> Optional[SubagentTask]:
        """
        Wait for a subagent to complete.

        Args:
            task_id: Subagent task ID
            timeout: Max wait time in seconds

        Returns:
            Completed task, or None if timeout
        """
        if task_id not in self.threads:
            return None

        self.threads[task_id].join(timeout=timeout or self.TIMEOUT_SECONDS)

        if self.threads[task_id].is_alive():
            # Timeout
            with self.lock:
                self.tasks[task_id].status = SubagentStatus.TIMEOUT.value
            return None

        return self.tasks.get(task_id)

    def wait_all(self, timeout: Optional[float] = None) -> List[SubagentTask]:
        """Wait for all subagents to complete."""
        for thread in self.threads.values():
            thread.join(timeout=timeout or self.TIMEOUT_SECONDS)

        return list(self.tasks.values())

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending subagent."""
        with self.lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                if task.status == SubagentStatus.PENDING.value:
                    task.status = SubagentStatus.CANCELLED.value
                    return True

        return False

    def get_task(self, task_id: str) -> Optional[SubagentTask]:
        """Get a subagent task."""
        return self.tasks.get(task_id)

    def list_tasks(self, parent_task: Optional[str] = None) -> List[SubagentTask]:
        """List all subagent tasks, optionally filtered by parent."""
        with self.lock:
            if parent_task:
                return [t for t in self.tasks.values() if t.parent_task == parent_task]
            return list(self.tasks.values())

    def get_active_count(self) -> int:
        """Get number of currently running subagents."""
        with self.lock:
            return self.active_count

    def get_result(self, task_id: str) -> Optional[Any]:
        """Get result from completed subagent."""
        return self.results.get(task_id)

    def print_status(self, task_id: Optional[str] = None) -> str:
        """Print status of subagent(s)."""
        if task_id:
            task = self.get_task(task_id)
            if not task:
                return f"Task {task_id} not found"

            status_icon = {
                SubagentStatus.PENDING.value: "⏳",
                SubagentStatus.RUNNING.value: "🏃",
                SubagentStatus.COMPLETED.value: "✅",
                SubagentStatus.FAILED.value: "❌",
                SubagentStatus.TIMEOUT.value: "⏱️",
                SubagentStatus.CANCELLED.value: "⛔",
            }.get(task.status, "❓")

            return f"{status_icon} {task.id}: {task.description[:40]}... [{task.status}]"

        # Print all tasks
        lines = [theme.banner("📋 Subagent Status")]
        for task in sorted(self.list_tasks(), key=lambda t: t.created_at):
            lines.append(self.print_status(task.id))

        return "\n".join(lines)

    def merge_results(self) -> Dict[str, Any]:
        """Merge all subagent results into a single dict."""
        return dict(self.results)


# Global manager instance
_manager: Optional[SubagentManager] = None


def get_manager() -> SubagentManager:
    """Get the global subagent manager."""
    global _manager
    if _manager is None:
        _manager = SubagentManager()
    return _manager
