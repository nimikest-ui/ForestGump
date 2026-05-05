"""Tests for MemoryManager with per-session memory and update parsing."""

import pytest
import json
from pathlib import Path
from forestgump.memory.manager import MemoryManager


@pytest.fixture
def memory_dir(tmp_path):
    """Create a temporary memory directory."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    return mem_dir


@pytest.fixture(autouse=True)
def mock_home(monkeypatch, tmp_path):
    """Mock home directory for memory storage."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def test_memory_manager_init(mock_home):
    """Test MemoryManager initialization."""
    manager = MemoryManager("test_session_001")
    assert manager.session_id == "test_session_001"
    assert "test_session_001" in str(manager.memory_file)


def test_memory_manager_save(mock_home):
    """Test saving memory to disk."""
    manager = MemoryManager("test_session_001")
    manager.add_fact("Test fact")
    assert manager.save()
    
    # Verify file was created
    memory_file = mock_home / ".forestgump" / "memory" / "test_session_001.json"
    assert memory_file.exists()


def test_memory_manager_add_fact(mock_home):
    """Test adding facts."""
    manager = MemoryManager("test_session_001")
    assert manager.add_fact("WPA2 network detected on channel 6")
    
    facts = manager.memory.list_facts()
    assert len(facts) == 1
    assert "WPA2 network detected" in facts[0]


def test_memory_manager_add_credential(mock_home):
    """Test adding credentials by target."""
    manager = MemoryManager("test_session_001")
    assert manager.add_credential("router", "admin", "admin123", method="ssh")
    
    creds = manager.memory.get_credentials("router")
    assert creds is not None
    assert creds["username"] == "admin"
    assert creds["password"] == "admin123"
    assert creds["method"] == "ssh"


def test_memory_manager_add_network(mock_home):
    """Test adding discovered networks."""
    manager = MemoryManager("test_session_001")
    assert manager.add_network("MyWifi", "AA:BB:CC:DD:EE:FF", 6, security="WPA2")
    
    networks = manager.memory.list_networks()
    assert "MyWifi" in networks
    
    net = manager.memory.get_network("MyWifi")
    assert net["bssid"] == "AA:BB:CC:DD:EE:FF"
    assert net["channel"] == 6
    assert net["security"] == "WPA2"


def test_memory_manager_add_note(mock_home):
    """Test adding notes."""
    manager = MemoryManager("test_session_001")
    assert manager.add_note("SSH is open on 192.168.1.1")
    
    notes = manager.memory.list_notes()
    assert len(notes) > 0
    assert "SSH is open" in notes[0]


def test_memory_manager_get_context(mock_home):
    """Test context generation."""
    manager = MemoryManager("test_session_001")
    manager.add_fact("Network: 192.168.1.0/24")
    manager.add_network("MyWifi", "AA:BB:CC:DD:EE:FF", 6)
    manager.add_credential("router", "admin", "admin123")
    
    context = manager.get_context()
    assert "Network: 192.168.1.0/24" in context
    assert "MyWifi" in context
    assert "router" in context


def test_memory_manager_clear(mock_home):
    """Test clearing all memory."""
    manager = MemoryManager("test_session_001")
    manager.add_fact("Fact 1")
    manager.add_note("Note 1")
    manager.add_credential("target", "user", "pass")
    manager.add_network("Net", "AA:BB:CC:DD:EE:FF", 6)
    
    # Verify items were added
    assert len(manager.memory.list_facts()) > 0
    
    # Clear
    assert manager.clear()
    
    # Verify cleared
    assert len(manager.memory.list_facts()) == 0
    assert len(manager.memory.list_notes()) == 0
    assert len(manager.memory.list_networks()) == 0
    assert len(manager.memory.credentials) == 0


def test_parse_credential_format(mock_home):
    """Test parsing credential from response format."""
    manager = MemoryManager("test_session")
    
    cred_text = "router {username: admin, password: admin123, method: ssh}"
    parsed = manager._parse_credential(cred_text)
    
    assert parsed is not None
    assert parsed["target"] == "router"
    assert parsed["username"] == "admin"
    assert parsed["password"] == "admin123"
    assert parsed["method"] == "ssh"


def test_parse_credential_missing_fields(mock_home):
    """Test parsing credential with missing required fields."""
    manager = MemoryManager("test_session")
    
    cred_text = "router {username: admin}"
    parsed = manager._parse_credential(cred_text)
    
    assert parsed is None


def test_parse_network_format(mock_home):
    """Test parsing network from response format."""
    manager = MemoryManager("test_session")
    
    net_text = "MyWifi {bssid: AA:BB:CC:DD:EE:FF, channel: 6, security: WPA2}"
    parsed = manager._parse_network(net_text)
    
    assert parsed is not None
    assert parsed["ssid"] == "MyWifi"
    assert parsed["bssid"] == "AA:BB:CC:DD:EE:FF"
    assert parsed["channel"] == 6
    assert parsed["security"] == "WPA2"


def test_parse_memory_updates_facts(mock_home):
    """Test parsing [MEMORY UPDATE] block with facts."""
    manager = MemoryManager("test_session")
    
    response = """
    Some response text here.
    [MEMORY UPDATE]
    - fact: WEP key cracked with aircrack-ng
    - fact: Router firmware version 3.2.1
    [END]
    """
    
    updates = manager.parse_memory_updates(response)
    assert len(updates["facts"]) == 2
    assert "WEP key cracked" in updates["facts"][0]
    assert "Router firmware" in updates["facts"][1]


def test_parse_memory_updates_credentials(mock_home):
    """Test parsing [MEMORY UPDATE] block with credentials."""
    manager = MemoryManager("test_session")
    
    response = """
    [MEMORY UPDATE]
    - credential: router {username: admin, password: admin123, method: ssh}
    - credential: target.com {username: root, password: root123, method: ssh}
    """
    
    updates = manager.parse_memory_updates(response)
    assert len(updates["credentials"]) == 2
    assert updates["credentials"][0]["target"] == "router"
    assert updates["credentials"][1]["target"] == "target.com"


def test_parse_memory_updates_networks(mock_home):
    """Test parsing [MEMORY UPDATE] block with networks."""
    manager = MemoryManager("test_session")
    
    response = """
    [MEMORY UPDATE]
    - network: Fiber-4k {bssid: AA:BB:CC:DD:EE:FF, channel: 6, security: WPA2}
    - network: OpenWifi {bssid: 11:22:33:44:55:66, channel: 11, security: Open}
    """
    
    updates = manager.parse_memory_updates(response)
    assert len(updates["networks"]) == 2
    assert updates["networks"][0]["ssid"] == "Fiber-4k"
    assert updates["networks"][1]["ssid"] == "OpenWifi"


def test_parse_memory_updates_notes(mock_home):
    """Test parsing [MEMORY UPDATE] block with notes."""
    manager = MemoryManager("test_session")
    
    response = """
    [MEMORY UPDATE]
    - note: Bluetooth adapter on hci0
    - note: Found SSH service on port 22
    """
    
    updates = manager.parse_memory_updates(response)
    assert len(updates["notes"]) == 2
    assert "Bluetooth adapter" in updates["notes"][0]
    assert "SSH service" in updates["notes"][1]


def test_parse_memory_updates_mixed(mock_home):
    """Test parsing mixed [MEMORY UPDATE] block."""
    manager = MemoryManager("test_session")
    
    response = """
    Some response...
    [MEMORY UPDATE]
    - fact: WPA2 cracked on Fiber-4k
    - credential: router {username: admin, password: admin123, method: ssh}
    - network: Fiber-4k {bssid: AA:BB:CC:DD:EE:FF, channel: 6, security: WPA2}
    - note: Router firmware version 3.2.1
    """
    
    updates = manager.parse_memory_updates(response)
    assert len(updates["facts"]) == 1
    assert len(updates["credentials"]) == 1
    assert len(updates["networks"]) == 1
    assert len(updates["notes"]) == 1


def test_parse_memory_updates_malformed_graceful(mock_home):
    """Test graceful handling of malformed [MEMORY UPDATE] blocks."""
    manager = MemoryManager("test_session")
    
    response = """
    [MEMORY UPDATE]
    - fact: Valid fact
    - credential: invalid format without braces
    - network: MyWifi {bssid: AA:BB:CC:DD:EE:FF}
    - note: Valid note
    """
    
    # Should not raise, should gracefully skip malformed entries
    updates = manager.parse_memory_updates(response)
    assert len(updates["facts"]) == 1
    assert len(updates["credentials"]) == 0  # Malformed, skipped
    assert len(updates["networks"]) == 0  # Missing channel, skipped
    assert len(updates["notes"]) == 1


def test_apply_updates_all_types(mock_home):
    """Test applying all types of updates."""
    manager = MemoryManager("test_session")
    
    updates = {
        "facts": ["Fact 1", "Fact 2"],
        "credentials": [
            {"target": "router", "username": "admin", "password": "admin123", "method": "ssh"}
        ],
        "networks": [
            {"ssid": "MyWifi", "bssid": "AA:BB:CC:DD:EE:FF", "channel": 6, "security": "WPA2"}
        ],
        "notes": ["Note 1"]
    }
    
    assert manager.apply_updates(updates)
    
    # Verify all applied
    assert len(manager.memory.list_facts()) == 2
    assert len(manager.memory.credentials) == 1
    assert len(manager.memory.list_networks()) == 1
    assert len(manager.memory.list_notes()) == 1


def test_memory_manager_session_isolation(mock_home):
    """Test that different sessions have separate memory."""
    manager1 = MemoryManager("session1")
    manager2 = MemoryManager("session2")
    
    manager1.add_fact("Fact from session 1")
    manager2.add_fact("Fact from session 2")
    
    # Each should have only its own fact
    assert "session 1" in manager1.memory.list_facts()[0]
    assert "session 2" in manager2.memory.list_facts()[0]
    assert len(manager1.memory.list_facts()) == 1
    assert len(manager2.memory.list_facts()) == 1


def test_memory_manager_persistence_across_instances(mock_home):
    """Test that memory persists when creating new MemoryManager with same session_id."""
    # Create first manager and add data
    manager1 = MemoryManager("persistent_session")
    manager1.add_fact("Persistent fact")
    manager1.add_credential("target", "user", "pass")
    
    # Create second manager with same session_id
    manager2 = MemoryManager("persistent_session")
    
    # Should have access to first manager's data
    assert "Persistent fact" in manager2.memory.list_facts()[0]
    assert manager2.memory.get_credentials("target") is not None
