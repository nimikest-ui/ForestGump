#!/usr/bin/env python3
"""
Task scheduling system for ForestGump.
Supports natural language schedule parsing and cron-based execution.
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict


@dataclass
class ScheduledTask:
    """Represents a scheduled task."""

    id: str
    name: str
    task_description: str
    schedule: str  # Natural language: "every day at 6am", "every Monday at 8am", etc.
    provider: str  # "claude", "ollama", "anthropic", "copilot"
    model: Optional[str] = None
    enabled: bool = True
    created_at: str = None
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0


class Scheduler:
    """Task scheduler with natural language schedule parsing."""

    SCHEDULE_FILE = Path(__file__).parent / 'schedules.json'

    def __init__(self):
        """Initialize scheduler."""
        self.tasks: Dict[str, ScheduledTask] = {}
        self.load_schedules()

    def load_schedules(self) -> None:
        """Load scheduled tasks from file."""
        if not self.SCHEDULE_FILE.exists():
            return

        try:
            with open(self.SCHEDULE_FILE, 'r') as f:
                data = json.load(f)
                for task_id, task_data in data.items():
                    self.tasks[task_id] = ScheduledTask(**task_data)
        except Exception:
            pass

    def save_schedules(self) -> None:
        """Save scheduled tasks to file."""
        try:
            with open(self.SCHEDULE_FILE, 'w') as f:
                tasks_dict = {
                    task_id: asdict(task) for task_id, task in self.tasks.items()
                }
                json.dump(tasks_dict, f, indent=2)
        except Exception:
            pass

    def parse_schedule(self, natural_schedule: str) -> Dict[str, Any]:
        """
        Parse natural language schedule into cron fields.

        Supports:
        - "every day at 6am" → 0 6 * * *
        - "every Monday at 8am" → 0 8 * * 1
        - "every 5 minutes" → */5 * * * *
        - "hourly" → 0 * * * *
        - "weekly on Wednesday" → 0 0 * * 3

        Args:
            natural_schedule: Natural language schedule string

        Returns:
            Dict with cron fields (minute, hour, dom, month, dow) and next_run_at
        """
        schedule = natural_schedule.lower().strip()

        # Parse minute
        minute = '0'
        if 'minute' in schedule:
            match = re.search(r'every (\d+) minutes?', schedule)
            if match:
                minute = f'*/{match.group(1)}'
            else:
                minute = '0'

        # Parse hour
        hour = '*'
        if 'day' in schedule or 'daily' in schedule:
            hour = self._extract_hour(schedule) or '0'
        elif 'hour' in schedule or 'hourly' in schedule:
            minute = '0'
            hour = '*'
        elif 'week' in schedule:
            hour = self._extract_hour(schedule) or '0'

        # Parse day of week
        dow = '*'
        day_map = {
            'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4,
            'friday': 5, 'saturday': 6, 'sunday': 0,
        }
        for day_name, day_num in day_map.items():
            if day_name in schedule:
                dow = str(day_num)
                break

        # Parse day of month
        dom = '*'
        match = re.search(r'on the (\d+)(?:st|nd|rd|th)?', schedule)
        if match:
            dom = match.group(1)

        # Parse month
        month = '*'
        month_map = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12,
        }
        for month_name, month_num in month_map.items():
            if month_name in schedule:
                month = str(month_num)
                break

        cron = f'{minute} {hour} {dom} {month} {dow}'

        return {
            'cron': cron,
            'minute': minute,
            'hour': hour,
            'dom': dom,
            'month': month,
            'dow': dow,
            'natural': natural_schedule,
        }

    def _extract_hour(self, schedule: str) -> Optional[str]:
        """Extract hour from schedule string."""
        # "at 6am" → 6
        match = re.search(r'at (\d{1,2})\s*(?:am|pm)?', schedule)
        if match:
            hour = int(match.group(1))
            if 'pm' in schedule and hour != 12:
                hour += 12
            elif 'am' in schedule and hour == 12:
                hour = 0
            return str(hour)
        return None

    def add_task(
        self,
        name: str,
        task_description: str,
        schedule: str,
        provider: str,
        model: Optional[str] = None,
    ) -> str:
        """
        Add a scheduled task.

        Args:
            name: Task name
            task_description: Task to execute
            schedule: Natural language schedule
            provider: LLM provider (claude, ollama, anthropic, copilot)
            model: Model override

        Returns:
            Task ID
        """
        import uuid

        task_id = str(uuid.uuid4())[:8]
        parsed = self.parse_schedule(schedule)

        task = ScheduledTask(
            id=task_id,
            name=name,
            task_description=task_description,
            schedule=schedule,
            provider=provider,
            model=model,
            created_at=datetime.now().isoformat(),
        )

        self.tasks[task_id] = task
        self.save_schedules()
        return task_id

    def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.save_schedules()
            return True
        return False

    def list_tasks(self) -> List[ScheduledTask]:
        """List all scheduled tasks."""
        return list(self.tasks.values())

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def enable_task(self, task_id: str) -> bool:
        """Enable a task."""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = True
            self.save_schedules()
            return True
        return False

    def disable_task(self, task_id: str) -> bool:
        """Disable a task."""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = False
            self.save_schedules()
            return True
        return False

    def mark_success(self, task_id: str) -> None:
        """Mark a task run as successful."""
        if task_id in self.tasks:
            self.tasks[task_id].last_run_at = datetime.now().isoformat()
            self.tasks[task_id].success_count += 1
            self.save_schedules()

    def mark_failure(self, task_id: str) -> None:
        """Mark a task run as failed."""
        if task_id in self.tasks:
            self.tasks[task_id].last_run_at = datetime.now().isoformat()
            self.tasks[task_id].failure_count += 1
            self.save_schedules()
