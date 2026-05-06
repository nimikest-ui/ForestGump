"""Delegate tool for ForestGump: task delegation and subtask execution.

This module provides tools for delegating complex tasks to subagents,
managing task queues, and coordinating multi-step operations.
"""

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import time
import json
import uuid
from datetime import datetime


class TaskStatus(str, Enum):
    """Task execution status."""
    
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class TaskPriority(str, Enum):
    """Task priority levels."""
    
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Task:
    """Represents a delegated task."""
    
    task_id: str
    name: str
    description: str
    instructions: str
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    timeout: Optional[int] = None
    retry_count: int = 0
    max_retries: int = 3
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        data = asdict(self)
        data['priority'] = self.priority.value
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create task from dictionary."""
        data = data.copy()
        if isinstance(data.get('priority'), str):
            data['priority'] = TaskPriority(data['priority'])
        if isinstance(data.get('status'), str):
            data['status'] = TaskStatus(data['status'])
        return cls(**data)
    
    def get_duration(self) -> Optional[float]:
        """Get task execution duration in seconds."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return time.time() - self.started_at
        return None
    
    def is_runnable(self) -> bool:
        """Check if task is ready to run."""
        return self.status == TaskStatus.PENDING and self.retry_count < self.max_retries


@dataclass
class TaskResult:
    """Result of task execution."""
    
    task_id: str
    success: bool
    output: str
    error: Optional[str] = None
    duration: float = 0.0
    timestamp: float = field(default_factory=time.time)


class TaskQueue:
    """Queue for managing delegated tasks."""
    
    def __init__(self):
        """Initialize task queue."""
        self.tasks: Dict[str, Task] = {}
        self.results: Dict[str, TaskResult] = {}
        self.execution_order: List[str] = []
    
    def add_task(self, task: Task) -> str:
        """
        Add task to queue.
        
        Args:
            task: Task to add
            
        Returns:
            Task ID
            
        Raises:
            ValueError: If task ID already exists
        """
        if task.task_id in self.tasks:
            raise ValueError(f"Task '{task.task_id}' already exists")
        
        self.tasks[task.task_id] = task
        self._reorder_by_priority()
        return task.task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self.tasks.get(task_id)
    
    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[Any] = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Update task status.
        
        Args:
            task_id: Task ID
            status: New status
            result: Optional result
            error: Optional error message
            
        Returns:
            True if updated successfully
        """
        task = self.get_task(task_id)
        if not task:
            return False
        
        task.status = status
        
        if status == TaskStatus.RUNNING and not task.started_at:
            task.started_at = time.time()
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.TIMEOUT):
            task.completed_at = time.time()
        
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        
        return True
    
    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks."""
        return [
            task for task in self.tasks.values()
            if task.is_runnable()
        ]
    
    def get_runnable_tasks(self) -> List[Task]:
        """Get tasks ready to run (dependencies satisfied)."""
        pending = self.get_pending_tasks()
        runnable = []
        
        # Priority numeric mapping (higher = more urgent)
        priority_order = {
            TaskPriority.LOW: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.HIGH: 3,
            TaskPriority.CRITICAL: 4,
        }
        
        for task in pending:
            # Check if dependencies are satisfied
            deps_satisfied = all(
                self.tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
                if dep_id in self.tasks
            )
            
            if deps_satisfied:
                runnable.append(task)
        
        return sorted(runnable, key=lambda t: priority_order[t.priority], reverse=True)
    
    def get_task_results(self) -> Dict[str, TaskResult]:
        """Get all task results."""
        return self.results.copy()
    
    def add_result(self, result: TaskResult) -> None:
        """Add task result."""
        self.results[result.task_id] = result
    
    def _reorder_by_priority(self) -> None:
        """Reorder pending tasks by priority."""
        pending = [
            (task_id, task) for task_id, task in self.tasks.items()
            if task.status == TaskStatus.PENDING
        ]
        pending.sort(key=lambda x: x[1].priority.value, reverse=True)
        self.execution_order = [task_id for task_id, _ in pending]
    
    def clear_completed(self) -> int:
        """
        Remove completed and failed tasks.
        
        Returns:
            Number of tasks removed
        """
        removed = 0
        task_ids_to_remove = [
            task_id for task_id, task in self.tasks.items()
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)
        ]
        
        for task_id in task_ids_to_remove:
            del self.tasks[task_id]
            if task_id in self.results:
                del self.results[task_id]
            removed += 1
        
        return removed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        stats = {
            'total_tasks': len(self.tasks),
            'pending': len([t for t in self.tasks.values() if t.status == TaskStatus.PENDING]),
            'running': len([t for t in self.tasks.values() if t.status == TaskStatus.RUNNING]),
            'completed': len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]),
            'failed': len([t for t in self.tasks.values() if t.status == TaskStatus.FAILED]),
            'total_results': len(self.results),
        }
        return stats
    
    def to_json(self) -> str:
        """Export queue to JSON."""
        data = {
            'tasks': {
                task_id: task.to_dict()
                for task_id, task in self.tasks.items()
            },
            'results': {
                task_id: asdict(result)
                for task_id, result in self.results.items()
            },
            'stats': self.get_stats(),
        }
        return json.dumps(data, indent=2, default=str)


class TaskDelegate:
    """Delegate for managing task execution."""
    
    def __init__(self, executor: Optional[Callable] = None):
        """
        Initialize delegate.
        
        Args:
            executor: Optional callback for executing tasks
        """
        self.queue = TaskQueue()
        self.executor = executor
        self.max_parallel_tasks = 5
        self.active_tasks = set()
    
    def create_task(
        self,
        name: str,
        instructions: str,
        task_id: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> Task:
        """
        Create and queue a task.
        
        Args:
            name: Task name
            instructions: Task instructions
            task_id: Optional task ID (auto-generated if None)
            priority: Task priority
            dependencies: Optional list of dependency task IDs
            timeout: Optional execution timeout
            tags: Optional tags for categorization
            description: Optional task description
            
        Returns:
            Created Task object
        """
        if not task_id:
            task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        task = Task(
            task_id=task_id,
            name=name,
            description=description or instructions[:100],
            instructions=instructions,
            priority=priority,
            dependencies=dependencies or [],
            timeout=timeout,
            tags=tags or []
        )
        
        self.queue.add_task(task)
        return task
    
    def execute_task(self, task_id: str) -> TaskResult:
        """
        Execute a single task.
        
        Args:
            task_id: Task ID to execute
            
        Returns:
            TaskResult with execution output
            
        Raises:
            KeyError: If task not found
        """
        task = self.queue.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        
        # Update status
        self.queue.update_task_status(task_id, TaskStatus.RUNNING)
        
        try:
            start_time = time.time()
            
            # Execute task
            if self.executor:
                output = self.executor(task.instructions)
            else:
                output = f"Task '{task.name}' executed (no executor)"
            
            duration = time.time() - start_time
            
            # Check timeout
            if task.timeout and duration > task.timeout:
                self.queue.update_task_status(
                    task_id,
                    TaskStatus.TIMEOUT,
                    error=f"Execution exceeded timeout of {task.timeout}s"
                )
                result = TaskResult(
                    task_id=task_id,
                    success=False,
                    output="",
                    error=f"Timeout after {task.timeout}s",
                    duration=duration
                )
            else:
                # Mark as completed
                self.queue.update_task_status(task_id, TaskStatus.COMPLETED, result=output)
                result = TaskResult(
                    task_id=task_id,
                    success=True,
                    output=str(output),
                    duration=duration
                )
        
        except Exception as e:
            error_msg = str(e)
            self.queue.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error=error_msg
            )
            result = TaskResult(
                task_id=task_id,
                success=False,
                output="",
                error=error_msg,
                duration=time.time() - start_time
            )
        
        self.queue.add_result(result)
        return result
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status."""
        return {
            'stats': self.queue.get_stats(),
            'runnable_tasks': [
                {'id': t.task_id, 'name': t.name, 'priority': t.priority.value}
                for t in self.queue.get_runnable_tasks()
            ],
            'active_tasks': list(self.active_tasks),
        }
    
    def clear_queue(self) -> int:
        """Clear completed tasks from queue."""
        return self.queue.clear_completed()


def create_task(
    name: str,
    instructions: str,
    priority: str = "normal",
    dependencies: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create a delegated task.
    
    This is a convenience function for the tool registry.
    
    Args:
        name: Task name
        instructions: Task instructions
        priority: Task priority (low, normal, high, critical)
        dependencies: Optional dependency task IDs
        
    Returns:
        Dictionary with task details
    """
    delegate = TaskDelegate()
    task = delegate.create_task(
        name=name,
        instructions=instructions,
        priority=TaskPriority(priority),
        dependencies=dependencies
    )
    return task.to_dict()


def queue_task(
    name: str,
    instructions: str,
    task_id: Optional[str] = None,
    priority: str = "normal"
) -> Dict[str, Any]:
    """
    Queue a task for execution.
    
    This is a convenience function for the tool registry.
    
    Args:
        name: Task name
        instructions: Task instructions
        task_id: Optional task ID
        priority: Task priority
        
    Returns:
        Dictionary with queued task details
    """
    delegate = TaskDelegate()
    task = delegate.create_task(
        name=name,
        instructions=instructions,
        task_id=task_id,
        priority=TaskPriority(priority)
    )
    return {
        'task_id': task.task_id,
        'status': task.status.value,
        'priority': task.priority.value,
        'created_at': task.created_at
    }
