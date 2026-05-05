"""Per-session memory manager with context injection and memory update parsing."""

import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from .system import MemorySystem


class MemoryManager:
    """Manages per-session memory with persistence and context injection.
    
    - Loads memory for a session_id
    - Persists memory to ~/.forestgump/memory/{session_id}.json
    - Provides context injection for system prompts
    - Parses [MEMORY UPDATE] blocks from provider responses
    """
    
    def __init__(self, session_id: str):
        """Initialize memory manager for a session.
        
        Args:
            session_id: Unique session identifier
        """
        self.session_id = session_id
        self.memory_file = Path.home() / ".forestgump" / "memory" / f"{session_id}.json"
        self.memory = MemorySystem(memory_file=self.memory_file)
    
    def save(self) -> bool:
        """Persist memory to disk.
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Ensure directory exists
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            # MemorySystem._save() is already called on updates, but we can ensure it
            self.memory._save()
            return True
        except Exception as e:
            print(f"[!] Failed to save memory: {e}")
            return False
    
    def add_fact(self, fact: str) -> bool:
        """Add a fact to memory (capped at 20).
        
        Args:
            fact: Fact content
            
        Returns:
            True if added successfully
        """
        try:
            self.memory.add_fact(fact)
            return True
        except Exception as e:
            print(f"[!] Failed to add fact: {e}")
            return False
    
    def add_credential(self, target: str, username: str, password: str, method: str = "unknown") -> bool:
        """Add a credential scoped to target.
        
        Args:
            target: Target name/IP
            username: Username
            password: Password
            method: Method used to obtain credentials
            
        Returns:
            True if added successfully
        """
        try:
            self.memory.add_credential(target, username, password, method=method)
            return True
        except Exception as e:
            print(f"[!] Failed to add credential: {e}")
            return False
    
    def add_network(self, ssid: str, bssid: str, channel: int, security: str = "unknown") -> bool:
        """Add a discovered network.
        
        Args:
            ssid: Network name
            bssid: BSSID (MAC address)
            channel: Channel number
            security: Security type (WPA2, WEP, etc.)
            
        Returns:
            True if added successfully
        """
        try:
            self.memory.add_network(ssid, bssid, channel, security=security)
            return True
        except Exception as e:
            print(f"[!] Failed to add network: {e}")
            return False
    
    def add_note(self, note: str) -> bool:
        """Add a note/insight (capped at 10).
        
        Args:
            note: Note content
            
        Returns:
            True if added successfully
        """
        try:
            self.memory.add_note(note)
            return True
        except Exception as e:
            print(f"[!] Failed to add note: {e}")
            return False
    
    def get_context(self) -> str:
        """Get formatted context for system prompt injection.
        
        Returns:
            Formatted memory context string
        """
        return self.memory.export_as_context()
    
    def clear(self) -> bool:
        """Clear all memory (safety feature).
        
        Returns:
            True if cleared successfully
        """
        try:
            self.memory.facts = []
            self.memory.notes = []
            self.memory.credentials = []
            self.memory.networks = {}
            self.memory._save()
            return True
        except Exception as e:
            print(f"[!] Failed to clear memory: {e}")
            return False
    
    def parse_memory_updates(self, response_text: str) -> Dict[str, Any]:
        """Parse [MEMORY UPDATE] blocks from provider response.
        
        Expected format:
        [MEMORY UPDATE]
        - fact: WEP key cracked with aircrack-ng
        - credential: router {username: admin, password: admin123, method: ssh}
        - network: MyWifi {bssid: AA:BB:CC:DD:EE:FF, channel: 6, security: WPA2}
        - note: Found Bluetooth device on hci0
        
        Args:
            response_text: Provider response text
            
        Returns:
            Dictionary with parsed updates: {"facts": [...], "credentials": [...], "networks": [...], "notes": [...]}
        """
        updates = {
            "facts": [],
            "credentials": [],
            "networks": [],
            "notes": []
        }
        
        # Find all [MEMORY UPDATE] blocks
        pattern = r"\[MEMORY UPDATE\](.*?)(?:\[|$)"
        matches = re.findall(pattern, response_text, re.DOTALL)
        
        for block in matches:
            lines = block.strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or not line.startswith("-"):
                    continue
                
                # Remove leading dash and whitespace
                line = line[1:].strip()
                
                try:
                    if line.startswith("fact:"):
                        fact = line[5:].strip()
                        if fact:
                            updates["facts"].append(fact)
                    
                    elif line.startswith("credential:"):
                        # Format: credential: target {username: user, password: pass, method: ssh}
                        cred_text = line[11:].strip()
                        cred = self._parse_credential(cred_text)
                        if cred:
                            updates["credentials"].append(cred)
                    
                    elif line.startswith("network:"):
                        # Format: network: SSID {bssid: AA:BB:CC:DD:EE:FF, channel: 6, security: WPA2}
                        net_text = line[8:].strip()
                        net = self._parse_network(net_text)
                        if net:
                            updates["networks"].append(net)
                    
                    elif line.startswith("note:"):
                        note = line[5:].strip()
                        if note:
                            updates["notes"].append(note)
                
                except Exception as e:
                    # Silently skip malformed lines
                    continue
        
        return updates
    
    def _parse_credential(self, cred_text: str) -> Optional[Dict[str, str]]:
        """Parse credential from text format: target {username: user, password: pass, method: ssh}.
        
        Args:
            cred_text: Credential text
            
        Returns:
            Dictionary with target, username, password, method or None if parse fails
        """
        try:
            # Split target and attributes
            if "{" not in cred_text or "}" not in cred_text:
                return None
            
            parts = cred_text.split("{", 1)
            target = parts[0].strip()
            attrs_str = parts[1].split("}", 1)[0]
            
            # Parse attributes
            attrs = {}
            for attr in attrs_str.split(","):
                if ":" in attr:
                    key, val = attr.split(":", 1)
                    attrs[key.strip()] = val.strip()
            
            if not all(k in attrs for k in ["username", "password"]):
                return None
            
            return {
                "target": target,
                "username": attrs["username"],
                "password": attrs["password"],
                "method": attrs.get("method", "unknown")
            }
        except Exception:
            return None
    
    def _parse_network(self, net_text: str) -> Optional[Dict[str, Any]]:
        """Parse network from text format: SSID {bssid: AA:BB:CC:DD:EE:FF, channel: 6, security: WPA2}.
        
        Args:
            net_text: Network text
            
        Returns:
            Dictionary with ssid, bssid, channel, security or None if parse fails
        """
        try:
            # Split SSID and attributes
            if "{" not in net_text or "}" not in net_text:
                return None
            
            parts = net_text.split("{", 1)
            ssid = parts[0].strip()
            attrs_str = parts[1].split("}", 1)[0]
            
            # Parse attributes
            attrs = {}
            for attr in attrs_str.split(","):
                if ":" in attr:
                    key, val = attr.split(":", 1)
                    attrs[key.strip()] = val.strip()
            
            if not all(k in attrs for k in ["bssid", "channel"]):
                return None
            
            # Parse channel as int
            try:
                channel = int(attrs["channel"])
            except ValueError:
                return None
            
            return {
                "ssid": ssid,
                "bssid": attrs["bssid"],
                "channel": channel,
                "security": attrs.get("security", "unknown")
            }
        except Exception:
            return None
    
    def apply_updates(self, updates: Dict[str, Any]) -> bool:
        """Apply parsed updates to memory.
        
        Args:
            updates: Dictionary from parse_memory_updates()
            
        Returns:
            True if all updates applied successfully
        """
        try:
            # Apply facts
            for fact in updates.get("facts", []):
                self.add_fact(fact)
            
            # Apply credentials
            for cred in updates.get("credentials", []):
                self.add_credential(
                    cred["target"],
                    cred["username"],
                    cred["password"],
                    cred.get("method", "unknown")
                )
            
            # Apply networks
            for net in updates.get("networks", []):
                self.add_network(
                    net["ssid"],
                    net["bssid"],
                    net["channel"],
                    net.get("security", "unknown")
                )
            
            # Apply notes
            for note in updates.get("notes", []):
                self.add_note(note)
            
            return True
        except Exception as e:
            print(f"[!] Failed to apply memory updates: {e}")
            return False
