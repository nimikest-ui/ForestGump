#!/usr/bin/env python3
"""
Memory system for ForestGump — persists facts, credentials, networks, and notes.
Injects context into system prompts for multi-turn conversations.
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime


class MemoryManager:
    """Manage conversation memory and context injection."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.memory_dir = Path.home() / ".forestgump" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.memory_dir / f"{session_id}.json"
        
        # Memory structure (caps for unbounded growth)
        self.max_facts = 20
        self.max_notes = 10
        
        self.memory = {
            "facts": [],
            "credentials": {},
            "networks": {},
            "notes": []
        }
        
        self.load()
    
    def load(self) -> None:
        """Load memory from disk if it exists."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r') as f:
                    loaded = json.load(f)
                    self.memory = loaded
            except Exception as e:
                print(f"[!] Could not load memory: {e}")
                self.memory = {"facts": [], "credentials": {}, "networks": {}, "notes": []}
    
    def save(self) -> None:
        """Save memory to disk."""
        try:
            with open(self.memory_file, 'w') as f:
                json.dump(self.memory, f, indent=2)
            # Secure permissions
            import os
            os.chmod(self.memory_file, 0o600)
        except Exception as e:
            print(f"[!] Could not save memory: {e}")
    
    def add_fact(self, fact: str) -> None:
        """Add a fact (capped at max_facts)."""
        if fact and fact not in self.memory["facts"]:
            self.memory["facts"].append(fact)
            if len(self.memory["facts"]) > self.max_facts:
                self.memory["facts"].pop(0)  # Remove oldest
    
    def add_credential(self, target: str, username: str, password: str, method: str = "unknown") -> None:
        """Store credential by target."""
        self.memory["credentials"][target] = {
            "username": username,
            "password": password,
            "method": method,
            "timestamp": datetime.now().isoformat()
        }
    
    def add_network(self, ssid: str, bssid: str = None, channel: int = None, security: str = None) -> None:
        """Store discovered network."""
        self.memory["networks"][ssid] = {
            "bssid": bssid,
            "channel": channel,
            "security": security,
            "timestamp": datetime.now().isoformat()
        }
    
    def add_note(self, note: str) -> None:
        """Add a note (capped at max_notes)."""
        if note and note not in self.memory["notes"]:
            self.memory["notes"].append(note)
            if len(self.memory["notes"]) > self.max_notes:
                self.memory["notes"].pop(0)  # Remove oldest
    
    def get_context(self) -> str:
        """
        Return formatted memory context for system prompt injection.
        """
        parts = []
        
        if self.memory["facts"]:
            parts.append("FACTS:")
            for fact in self.memory["facts"]:
                parts.append(f"  - {fact}")
        
        if self.memory["credentials"]:
            parts.append("\nCREDENTIALS:")
            for target, cred in self.memory["credentials"].items():
                parts.append(f"  - {target}: {cred['username']} / {'*' * 4} (method: {cred['method']})")
        
        if self.memory["networks"]:
            parts.append("\nNETWORKS:")
            for ssid, net in self.memory["networks"].items():
                channel = f"ch{net['channel']}" if net['channel'] else "unknown"
                parts.append(f"  - {ssid}: {net['bssid']} ({channel}, {net['security']})")
        
        if self.memory["notes"]:
            parts.append("\nNOTES:")
            for note in self.memory["notes"]:
                parts.append(f"  - {note}")
        
        return "\n".join(parts) if parts else ""
    
    def parse_memory_updates(self, response: str) -> None:
        """
        Parse [MEMORY UPDATE] blocks from agent response and update memory.
        Expected format:
        [MEMORY UPDATE]
        - fact: WEP key cracked with aircrack-ng
        - credential: router {username: admin, password: admin123, method: ssh}
        - network: MyWifi {bssid: AA:BB:CC:DD:EE:FF, channel: 6, security: WPA2}
        - note: Found Bluetooth device on hci0
        """
        pattern = r'\[MEMORY UPDATE\](.*?)(?:\[|$)'
        match = re.search(pattern, response, re.DOTALL)
        
        if not match:
            return
        
        updates = match.group(1)
        for line in updates.split('\n'):
            line = line.strip()
            if not line or not line.startswith('-'):
                continue
            
            line = line[1:].strip()  # Remove leading '-'
            
            try:
                if line.startswith('fact:'):
                    fact = line[5:].strip()
                    self.add_fact(fact)
                
                elif line.startswith('credential:'):
                    # Format: credential: target {username: user, password: pass, method: ssh}
                    match = re.match(r'credential:\s*(\S+)\s*\{(.*?)\}', line)
                    if match:
                        target = match.group(1)
                        attrs = match.group(2)
                        
                        # Parse attributes
                        username = re.search(r'username:\s*(\S+)', attrs)
                        password = re.search(r'password:\s*(\S+)', attrs)
                        method = re.search(r'method:\s*(\S+)', attrs)
                        
                        username = username.group(1) if username else "unknown"
                        password = password.group(1) if password else "unknown"
                        method = method.group(1) if method else "unknown"
                        
                        self.add_credential(target, username, password, method)
                
                elif line.startswith('network:'):
                    # Format: network: SSID {bssid: AA:BB:CC:DD:EE:FF, channel: 6, security: WPA2}
                    match = re.match(r'network:\s*(\S+)\s*\{(.*?)\}', line)
                    if match:
                        ssid = match.group(1)
                        attrs = match.group(2)
                        
                        bssid = re.search(r'bssid:\s*([A-Fa-f0-9:]+)', attrs)
                        channel = re.search(r'channel:\s*(\d+)', attrs)
                        security = re.search(r'security:\s*(\S+)', attrs)
                        
                        bssid = bssid.group(1) if bssid else None
                        channel = int(channel.group(1)) if channel else None
                        security = security.group(1) if security else None
                        
                        self.add_network(ssid, bssid, channel, security)
                
                elif line.startswith('note:'):
                    note = line[5:].strip()
                    self.add_note(note)
            
            except Exception as e:
                # Silently skip malformed updates
                pass
    
    def clear(self) -> None:
        """Clear all memory (safety feature)."""
        self.memory = {"facts": [], "credentials": {}, "networks": {}, "notes": []}
        self.save()
    
    def summary(self) -> str:
        """Return a short summary of memory state."""
        return f"Facts: {len(self.memory['facts'])}, Credentials: {len(self.memory['credentials'])}, Networks: {len(self.memory['networks'])}, Notes: {len(self.memory['notes'])}"
