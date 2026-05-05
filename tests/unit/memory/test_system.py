import pytest
import json
from pathlib import Path
from forestgump.memory.system import MemorySystem

@pytest.fixture
def memory_file(tmp_path):
    return tmp_path / "memory.json"

@pytest.fixture
def memory_system(memory_file):
    return MemorySystem(memory_file=memory_file)

def test_memory_add_fact(memory_system, memory_file):
    """Test adding facts to memory"""
    memory_system.add_fact("WPA2 network detected on channel 6")
    facts = memory_system.list_facts()
    assert len(facts) == 1
    assert "WPA2 network detected" in facts[0]

def test_memory_add_multiple_facts(memory_system):
    """Test adding multiple facts"""
    memory_system.add_fact("Fact 1")
    memory_system.add_fact("Fact 2")
    facts = memory_system.list_facts()
    assert len(facts) == 2

def test_memory_add_credential(memory_system):
    """Test adding credentials with target scope"""
    memory_system.add_credential("router", "admin", "admin123", method="brute_force")
    creds = memory_system.get_credentials("router")
    assert creds["username"] == "admin"
    assert creds["password"] == "admin123"

def test_memory_replace_fact(memory_system):
    """Test replacing a fact"""
    memory_system.add_fact("Old information")
    memory_system.replace_fact("Old information", "Updated information")
    facts = memory_system.list_facts()
    assert "Updated information" in facts[0]
    assert "Old information" not in facts[0]

def test_memory_remove_credential(memory_system):
    """Test removing credentials"""
    memory_system.add_credential("router", "admin", "admin123")
    memory_system.remove_credential("router", "admin")
    creds = memory_system.get_credentials("router")
    assert creds is None

def test_memory_persistence(memory_file):
    """Test that memory persists across instances"""
    system1 = MemorySystem(memory_file=memory_file)
    system1.add_fact("Persistent fact")
    
    system2 = MemorySystem(memory_file=memory_file)
    facts = system2.list_facts()
    assert "Persistent fact" in facts[0]

def test_memory_export_context(memory_system):
    """Test exporting memory as LLM context"""
    memory_system.add_fact("Network: 192.168.1.0/24")
    memory_system.add_network("MyWifi", bssid="AA:BB:CC:DD:EE:FF", channel=6)
    
    context = memory_system.export_as_context()
    assert "Network: 192.168.1.0/24" in context
    assert "MyWifi" in context

def test_memory_add_note(memory_system):
    """Test adding notes/insights"""
    memory_system.add_note("SSH is open on 192.168.1.1", tags=["ssh", "finding"])
    notes = memory_system.list_notes()
    assert len(notes) > 0
    assert "SSH is open" in notes[0]

def test_memory_add_network(memory_system):
    """Test adding networks"""
    memory_system.add_network("MyWifi", bssid="AA:BB:CC:DD:EE:FF", channel=6, security="WPA2")
    networks = memory_system.list_networks()
    assert "MyWifi" in networks
    net = memory_system.get_network("MyWifi")
    assert net["security"] == "WPA2"

def test_memory_facts_cap_at_20(memory_system):
    """Test facts are capped at 20 entries"""
    for i in range(25):
        memory_system.add_fact(f"Fact {i}")
    facts = memory_system.list_facts()
    assert len(facts) <= 20

def test_memory_notes_cap_at_10(memory_system):
    """Test notes are capped at 10 entries"""
    for i in range(15):
        memory_system.add_note(f"Note {i}")
    notes = memory_system.list_notes()
    assert len(notes) <= 10
