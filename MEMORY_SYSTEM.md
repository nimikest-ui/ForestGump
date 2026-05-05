# ForestGump Memory System Documentation

## Overview

The ForestGump memory system provides persistent conversation history and context injection for multi-turn pentesting sessions. Memory is stored per-session and automatically loaded when resuming sessions.

## Architecture

### Components

1. **MemorySystem** (`src/forestgump/memory/system.py`)
   - Base memory storage with facts, credentials, networks, and notes
   - Persists to `~/.forestgump/memory.json`
   - Handles serialization/deserialization
   - Caps facts at 20 and notes at 10 to prevent unbounded growth

2. **MemoryManager** (`src/forestgump/memory/manager.py`)
   - Per-session memory wrapper built on top of MemorySystem
   - Loads/saves memory to `~/.forestgump/memory/{session_id}.json`
   - Parses `[MEMORY UPDATE]` blocks from provider responses
   - Injects memory context into system prompts

3. **ForestGumpCLI Integration** (`forestgump_cli.py`)
   - Session management with memory resumption
   - System prompt building with memory context injection
   - Memory update parsing after provider calls
   - Session persistence with memory snapshots

## Data Structure

### Memory File Format

Each session stores memory in `~/.forestgump/memory/{session_id}.json`:

```json
{
  "facts": [
    {
      "content": "WPA2 network detected on channel 6",
      "type": "fact",
      "timestamp": "2026-05-05T21:29:25.770357",
      "tags": []
    }
  ],
  "credentials": [
    {
      "target": "router",
      "username": "admin",
      "password": "***",
      "method": "ssh",
      "timestamp": "2026-05-05T21:29:25.772590",
      "notes": ""
    }
  ],
  "networks": {
    "MyWifi": {
      "name": "MyWifi",
      "bssid": "AA:BB:CC:DD:EE:FF",
      "channel": 6,
      "security": "WPA2",
      "signal_strength": null,
      "timestamp": "2026-05-05T21:29:25.773389",
      "notes": ""
    }
  },
  "notes": [
    {
      "content": "Bluetooth adapter on hci0",
      "type": "note",
      "timestamp": "2026-05-05T21:29:25.774172",
      "tags": []
    }
  ]
}
```

## Usage

### Session Initialization with Memory

When starting a new chat session:

```bash
forestgump chat -q "scan the network"
```

A new `session_id` is generated and memory directory `~/.forestgump/memory/{session_id}/` is created.

### Session Resumption with Memory Context

Resume previous session with all memory context injected:

```bash
forestgump chat -q "continue scanning" --resume SESSION_ID
```

Or resume most recent session:

```bash
forestgump chat -q "continue" -c
```

### Memory Context Injection

When a session is resumed, the system prompt automatically includes:

```
You are a pentesting agent running on Kali Linux. You have access to:
[... tools list ...]

Memory Context (Previous Session Information):
=== FACTS ===
- WPA2 network detected on channel 6
- Router firmware version 3.2.1

=== CREDENTIALS ===
- router: admin / ****
- target.com: root / ****

=== NETWORKS ===
- MyWifi (AA:BB:CC:DD:EE:FF), channel 6, WPA2

=== NOTES ===
- Bluetooth adapter on hci0
```

## Memory Update Parsing

Provider responses can include `[MEMORY UPDATE]` blocks to add observations:

### Format

```
[MEMORY UPDATE]
- fact: WEP key cracked with aircrack-ng
- credential: router {username: admin, password: admin123, method: ssh}
- network: MyWifi {bssid: AA:BB:CC:DD:EE:FF, channel: 6, security: WPA2}
- note: Found Bluetooth device on hci0
```

### Supported Update Types

- **fact**: Observations about targets/networks (max 20 per session)
- **credential**: Access credentials with target scope
- **network**: Discovered WiFi networks with BSSID and security
- **note**: Important insights/findings (max 10 per session)

### Parsing Features

- Graceful handling of malformed entries (parse failures don't crash)
- Skips invalid entries silently
- Supports multiple `[MEMORY UPDATE]` blocks per response
- Properly handles special characters and spaces

## API

### MemoryManager

```python
from forestgump.memory import MemoryManager

# Initialize for a session
memory = MemoryManager("session_id_123")

# Add observations
memory.add_fact("Important finding")
memory.add_credential("target", "user", "pass", method="ssh")
memory.add_network("WiFi-Name", "AA:BB:CC:DD:EE:FF", 6, security="WPA2")
memory.add_note("Follow-up action needed")

# Get formatted context for prompt injection
context = memory.get_context()

# Parse provider response for updates
updates = memory.parse_memory_updates(provider_response_text)

# Apply updates to memory
memory.apply_updates(updates)

# Save memory to disk
memory.save()

# Clear all memory (safety feature)
memory.clear()
```

## Key Features

### Per-Session Isolation

Each session has completely separate memory files:
- Session A: `~/.forestgump/memory/SESSION_A.json`
- Session B: `~/.forestgump/memory/SESSION_B.json`

Sessions never interfere with each other.

### Persistence

Memory persists across:
- CLI restarts
- Provider changes (can switch from Groq to Claude mid-session)
- Multiple resumptions
- Tool usage changes

### Bounded Memory Growth

- **Facts**: Capped at 20 (keeps newest)
- **Notes**: Capped at 10 (keeps newest)
- **Credentials**: Unlimited (by target)
- **Networks**: Unlimited (by SSID)

### Security

- Memory NOT encrypted (security boundary: trust user's home directory)
- Credentials stored in plaintext (same security model as `.ssh/config`)
- Each session isolated from others
- File permissions respected by OS

## Testing

Run comprehensive memory tests:

```bash
PYTHONPATH=/root/ForestGump/src pytest tests/unit/memory/ -v
```

Tests cover:
- Memory Manager initialization
- Adding/retrieving all data types
- Session isolation and persistence
- Credential and network parsing
- Memory update extraction from responses
- Graceful error handling

## Integration with Providers

When implementing provider integration:

1. **Before API call**: Build system prompt with `memory.get_context()`
2. **After API call**: Parse response with `memory.parse_memory_updates(response)`
3. **Apply updates**: Use `memory.apply_updates(updates)`
4. **Save session**: Include memory snapshot in session JSON

### Example Implementation

```python
def chat_with_memory(provider, query, session_id):
    memory = MemoryManager(session_id)
    
    # Build system prompt with context
    system_prompt = build_system_prompt(memory.get_context())
    
    # Call provider
    response = provider.chat(system_prompt, query)
    
    # Parse updates
    updates = memory.parse_memory_updates(response)
    
    # Apply and save
    memory.apply_updates(updates)
    memory.save()
    
    return response
```

## Session Snapshots

Sessions are saved with memory snapshots in `~/.forestgump/sessions/{session_id}.json`:

```json
{
  "session_id": "20260505T212854",
  "task": "scan the network",
  "provider": "groq",
  "model": "llama-3.3-70b-versatile",
  "timestamp": "2026-05-05T21:28:54",
  "messages": [...],
  "memory_snapshot": {
    "facts": ["WPA2 detected"],
    "credentials": ["router: admin"],
    "networks": ["MyWifi"],
    "notes": ["Important finding"]
  }
}
```

## Troubleshooting

### Memory not persisting

- Ensure `~/.forestgump/memory/` directory exists and is writable
- Check session_id is consistent across calls
- Verify MemoryManager.save() is called

### Memory not injecting into prompts

- Verify `memory.get_context()` returns non-empty string
- Check system prompt building includes memory context
- Ensure provider receives full system prompt

### Parsing failures

- Check `[MEMORY UPDATE]` block format matches specification
- Verify proper braces and commas in credential/network entries
- Malformed entries are silently skipped (check logs for details)

## Future Enhancements

- [ ] Encryption for credentials stored in memory
- [ ] Memory compression for large sessions
- [ ] Automatic memory archival after N sessions
- [ ] Memory search/filtering by tags
- [ ] Differential memory updates (only changed fields)
- [ ] Remote memory synchronization
