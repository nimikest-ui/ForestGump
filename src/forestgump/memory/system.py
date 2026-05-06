"""Hermes-compatible memory system with add/replace/remove interface."""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from .types import Credential, Network, MemoryEntry


class MemorySystem:
    """Hermes-compatible memory system for managing facts, credentials, networks, and notes."""

    def __init__(self, memory_file: Optional[Path] = None):
        """Initialize memory system.
        
        Args:
            memory_file: Optional path to memory file. If None, uses ~/.forestgump/memory.json
        
        """
        if memory_file is None:
            memory_file = Path.home() / ".forestgump" / "memory.json"
        
        self.memory_file = Path(memory_file)
        self.facts: List[MemoryEntry] = []
        self.notes: List[MemoryEntry] = []
        self.credentials: List[Credential] = []
        self.networks: Dict[str, Network] = {}
        
        self._load()

    def _load(self):
        """Load memory from disk if file exists."""
        if not self.memory_file.exists():
            return
        
        try:
            with open(self.memory_file, "r") as f:
                data = json.load(f)
            
            # Load facts
            self.facts = [MemoryEntry.from_dict(f) for f in data.get("facts", [])]
            
            # Load notes
            self.notes = [MemoryEntry.from_dict(n) for n in data.get("notes", [])]
            
            # Load credentials
            self.credentials = [Credential.from_dict(c) for c in data.get("credentials", [])]
            
            # Load networks
            self.networks = {
                name: Network.from_dict(net) 
                for name, net in data.get("networks", {}).items()
            }
        except (json.JSONDecodeError, KeyError, ValueError):
            # If file is corrupted, start fresh
            pass

    def _save(self):
        """Persist memory to disk with atomic writes and backup."""
        import os
        import tempfile
        
        # Create directory if needed
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "facts": [f.to_dict() for f in self.facts],
            "notes": [n.to_dict() for n in self.notes],
            "credentials": [c.to_dict() for c in self.credentials],
            "networks": {name: net.to_dict() for name, net in self.networks.items()},
        }
        
        # Atomic write with backup: write to temp file first, then move
        try:
            # Write to temporary file
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.memory_file.parent,
                prefix=".memory_tmp_",
                suffix=".json"
            )
            
            with os.fdopen(temp_fd, "w") as f:
                json.dump(data, f, indent=2)
            
            # Set safe permissions on temp file before moving
            os.chmod(temp_path, 0o600)
            
            # Create backup if file exists
            if self.memory_file.exists():
                backup_path = self.memory_file.with_suffix(".json.bak")
                self.memory_file.replace(backup_path) if backup_path.exists() else None
                Path(temp_path).replace(self.memory_file)
                # Ensure proper permissions on final file
                os.chmod(str(self.memory_file), 0o600)
            else:
                Path(temp_path).replace(self.memory_file)
                os.chmod(str(self.memory_file), 0o600)
        except Exception as e:
            # Clean up temp file on error
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise e

    # ============ FACTS INTERFACE ============
    
    def add_fact(self, content: str, tags: Optional[List[str]] = None):
        """Add a fact to memory.
        
        Args:
            content: The fact content
            tags: Optional tags for the fact
        """
        if tags is None:
            tags = []
        
        entry = MemoryEntry(content=content, type="fact", tags=tags)
        self.facts.append(entry)
        
        # Cap at 20 entries (keep newest)
        if len(self.facts) > 20:
            self.facts = self.facts[-20:]
        
        self._save()

    def list_facts(self) -> List[str]:
        """List all facts.
        
        Returns:
            List of fact content strings
        """
        return [f.content for f in self.facts]

    def replace_fact(self, old_text: str, new_text: str):
        """Replace a fact by substring match.
        
        Args:
            old_text: Substring to find and replace
            new_text: New text to replace with
        """
        for entry in self.facts:
            if old_text in entry.content:
                entry.content = entry.content.replace(old_text, new_text)
                break
        
        self._save()

    def remove_fact(self, text: str):
        """Remove a fact by substring match.
        
        Args:
            text: Substring to find and remove
        """
        self.facts = [f for f in self.facts if text not in f.content]
        self._save()

    # ============ CREDENTIALS INTERFACE ============
    
    def add_credential(
        self,
        target: str,
        username: str,
        password: str,
        method: str = "unknown",
        notes: str = "",
    ):
        """Add credentials for a target.
        
        Args:
            target: Target name/IP
            username: Username
            password: Password
            method: Method used to obtain credentials
            notes: Additional notes
        """
        cred = Credential(
            target=target,
            username=username,
            password=password,
            method=method,
            notes=notes,
        )
        self.credentials.append(cred)
        self._save()

    def get_credentials(self, target: str) -> Optional[Dict]:
        """Get first credential for a target.
        
        Args:
            target: Target name/IP
            
        Returns:
            Dictionary with username, password, method, notes or None if not found
        """
        for cred in self.credentials:
            if cred.target == target:
                return {
                    "username": cred.username,
                    "password": cred.password,
                    "method": cred.method,
                    "notes": cred.notes,
                    "timestamp": cred.timestamp.isoformat(),
                }
        return None

    def remove_credential(self, target: str, username: str):
        """Remove a specific credential.
        
        Args:
            target: Target name/IP
            username: Username to remove
        """
        self.credentials = [
            c for c in self.credentials
            if not (c.target == target and c.username == username)
        ]
        self._save()

    # ============ NETWORKS INTERFACE ============
    
    def add_network(
        self,
        name: str,
        bssid: str,
        channel: int,
        security: str = "unknown",
        notes: str = "",
    ):
        """Add a network to memory.
        
        Args:
            name: Network name (SSID)
            bssid: BSSID of network
            channel: Channel number
            security: Security type (WPA2, WEP, etc.)
            notes: Additional notes
        """
        net = Network(
            name=name,
            bssid=bssid,
            channel=channel,
            security=security,
            notes=notes,
        )
        self.networks[name] = net
        self._save()

    def get_network(self, name: str) -> Optional[Dict]:
        """Get network by name.
        
        Args:
            name: Network name
            
        Returns:
            Dictionary with network details or None if not found
        """
        if name in self.networks:
            net = self.networks[name]
            return {
                "name": net.name,
                "bssid": net.bssid,
                "channel": net.channel,
                "security": net.security,
                "signal_strength": net.signal_strength,
                "timestamp": net.timestamp.isoformat(),
                "notes": net.notes,
            }
        return None

    def list_networks(self) -> List[str]:
        """List all network names.
        
        Returns:
            List of network names
        """
        return list(self.networks.keys())
    
    def remove_network(self, name: str):
        """Remove a network by name.
        
        Args:
            name: Network name to remove
        """
        if name in self.networks:
            del self.networks[name]
            self._save()

    # ============ NOTES INTERFACE ============
    
    def add_note(self, content: str, tags: Optional[List[str]] = None):
        """Add a note to memory.
        
        Args:
            content: Note content
            tags: Optional tags for the note
        """
        if tags is None:
            tags = []
        
        entry = MemoryEntry(content=content, type="note", tags=tags)
        self.notes.append(entry)
        
        # Cap at 10 entries (keep newest)
        if len(self.notes) > 10:
            self.notes = self.notes[-10:]
        
        self._save()

    def list_notes(self) -> List[str]:
        """List all notes.
        
        Returns:
            List of note content strings
        """
        return [n.content for n in self.notes]

    # ============ CONTEXT EXPORT (for LLM) ============
    
    def export_as_context(self) -> str:
        """Export memory as formatted context for LLM.
        
        Returns:
            Formatted memory context string
        """
        lines = []
        
        # Facts section
        if self.facts:
            lines.append("=== FACTS ===")
            for fact in self.facts:
                lines.append(f"- {fact.content}")
            lines.append("")
        
        # Notes section
        if self.notes:
            lines.append("=== NOTES ===")
            for note in self.notes:
                tags_str = f" [{', '.join(note.tags)}]" if note.tags else ""
                lines.append(f"- {note.content}{tags_str}")
            lines.append("")
        
        # Networks section
        if self.networks:
            lines.append("=== NETWORKS ===")
            for name, net in self.networks.items():
                lines.append(f"- {name} ({net.bssid})")
                lines.append(f"  Channel: {net.channel}, Security: {net.security}")
                if net.signal_strength is not None:
                    lines.append(f"  Signal: {net.signal_strength}")
                if net.notes:
                    lines.append(f"  Notes: {net.notes}")
            lines.append("")
        
        # Credentials section
        if self.credentials:
            lines.append("=== CREDENTIALS ===")
            by_target = {}
            for cred in self.credentials:
                if cred.target not in by_target:
                    by_target[cred.target] = []
                by_target[cred.target].append(cred)
            
            for target, creds in by_target.items():
                lines.append(f"- {target}:")
                for cred in creds:
                    lines.append(f"  User: {cred.username} | Method: {cred.method}")
                    if cred.notes:
                        lines.append(f"  Notes: {cred.notes}")
            lines.append("")
        
        return "\n".join(lines).strip()
