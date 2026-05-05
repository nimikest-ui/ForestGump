"""Memory data types and structures."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class Credential:
    """Credential entry for targets."""
    target: str
    username: str
    password: str
    method: str = "unknown"
    timestamp: datetime = field(default_factory=datetime.now)
    notes: str = ""

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "target": self.target,
            "username": self.username,
            "password": self.password,
            "method": self.method,
            "timestamp": self.timestamp.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data):
        """Create from dictionary."""
        data = data.copy()
        if "timestamp" in data:
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class Network:
    """Network entry discovered."""
    name: str
    bssid: str
    channel: int
    security: str = "unknown"
    signal_strength: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
    notes: str = ""

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "bssid": self.bssid,
            "channel": self.channel,
            "security": self.security,
            "signal_strength": self.signal_strength,
            "timestamp": self.timestamp.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data):
        """Create from dictionary."""
        data = data.copy()
        if "timestamp" in data:
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class MemoryEntry:
    """Base memory entry type."""
    content: str
    type: str  # "fact", "note", etc.
    timestamp: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "content": self.content,
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data):
        """Create from dictionary."""
        data = data.copy()
        if "timestamp" in data:
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)
