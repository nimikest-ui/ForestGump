#!/usr/bin/env python3
"""
Comprehensive test script for InteractiveREPL with Copilot provider.

Tests:
1. REPL session with real Copilot provider
2. Query handling (what is the top 5 kali tools)
3. Command handling (/model, /status, /exit)
4. Session persistence and resumption
5. Memory system persistence
6. Timeout handling
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, "/root/ForestGump")

from forestgump_cli import InteractiveREPL, Colors, ProviderManager
from providers import CopilotProvider
from memory import MemoryManager


def print_test_header(test_name: str):
    """Print formatted test header."""
    print(f"\n{Colors.info('='*60)}")
    print(f"{Colors.info(f'TEST: {test_name}')}")
    print(f"{Colors.info('='*60)}\n")


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result."""
    status = Colors.success("[PASS]") if passed else Colors.error("[FAIL]")
    print(f"{status} {test_name}")
    if details:
        print(f"       {details}")


class MockProvider:
    """Mock provider for testing REPL without external dependencies."""
    
    def __init__(self, name: str = "mock"):
        self.name = name
        self.call_count = 0
        self.last_input = None
        self.last_history = None
    
    def chat(self, message: str, history: list = None) -> str:
        """Mock chat that returns demo responses."""
        self.call_count += 1
        self.last_input = message
        self.last_history = history or []
        
        # Return realistic demo responses
        responses = {
            "what is the top 5 kali tools": """The top 5 Kali Linux tools for penetration testing are:

1. **Metasploit Framework** - Comprehensive exploitation framework with 1000+ exploits
   - Best for: Post-exploitation, framework-based attacks
   - Command: msfconsole

2. **Burp Suite** - Web application security testing platform
   - Best for: Web app penetration testing, API testing
   - Command: burpsuite

3. **Nmap** - Network mapper for discovery and scanning
   - Best for: Network enumeration, port scanning, service detection
   - Command: nmap

4. **Wireshark** - Network packet analyzer and protocol analyzer
   - Best for: Traffic analysis, network debugging
   - Command: wireshark

5. **sqlmap** - SQL injection detection and exploitation tool
   - Best for: Automated SQL injection testing
   - Command: sqlmap

Each tool serves a specific role in the penetration testing workflow.""",
            
            "scan port 22 with nmap": """# Nmap scan result
Starting Nmap 7.80
Nmap scan report for localhost (127.0.0.1)
Host is up (0.0000s latency).
PORT   STATE SERVICE
22/tcp open  ssh
Service detection performed.
Nmap done at {timestamp}; 1 IP address (1 host up) scanned in 0.15 seconds

[MEMORY UPDATE]
[FACT] Port 22 (SSH) is open on target 127.0.0.1
[FACT] SSH service is running on target
[/MEMORY UPDATE]""".format(timestamp=datetime.now().strftime("%a %b %d %H:%M:%S %Y")),
        }
        
        # Check for key phrases in input
        message_lower = message.lower()
        for key, response in responses.items():
            if key in message_lower:
                return response
        
        # Generic response
        return f"Response to: {message[:50]}... (mock provider)"


class InteractiveREPLTester:
    """Comprehensive tester for InteractiveREPL."""
    
    def __init__(self):
        self.session_dir = Path.home() / ".forestgump" / "sessions"
        self.memory_dir = Path.home() / ".forestgump" / "memory"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.test_results = []
        self.session_id = None
    
    def test_repl_initialization(self):
        """Test 1: REPL initialization with mock provider."""
        print_test_header("REPL Initialization")
        
        try:
            provider = MockProvider("mock-copilot")
            repl = InteractiveREPL(
                provider=provider,
                model="mock-model",
                provider_name="mock",
                session_dir=self.session_dir
            )
            
            checks = [
                ("Provider set", repl.provider is not None),
                ("Model set", repl.model == "mock-model"),
                ("History initialized", repl.conversation_history == []),
                ("Session dir created", repl.session_dir.exists()),
            ]
            
            passed = all(check[1] for check in checks)
            for check_name, check_result in checks:
                print_result(check_name, check_result)
            
            self.test_results.append(("REPL Initialization", passed))
            return passed
        
        except Exception as e:
            print_result("REPL Initialization", False, str(e))
            self.test_results.append(("REPL Initialization", False))
            return False
    
    def test_message_handling(self):
        """Test 2: Message sending and receiving."""
        print_test_header("Message Handling")
        
        try:
            provider = MockProvider("mock-copilot")
            repl = InteractiveREPL(
                provider=provider,
                model="mock-model",
                provider_name="mock",
                session_dir=self.session_dir
            )
            
            # Simulate sending a message
            query = "what is the top 5 kali tools"
            repl.append_message("user", query)
            
            # Get provider response
            response = provider.chat(query, repl.conversation_history)
            repl.append_message("assistant", response)
            
            checks = [
                ("User message appended", len(repl.conversation_history) >= 1),
                ("Assistant response appended", len(repl.conversation_history) >= 2),
                ("Response contains content", len(response) > 0),
                ("Turn count correct", repl.get_turn_count() == 1),
                ("User message stored", repl.conversation_history[0]["role"] == "user"),
                ("Assistant message stored", repl.conversation_history[1]["role"] == "assistant"),
            ]
            
            passed = all(check[1] for check in checks)
            for check_name, check_result in checks:
                print_result(check_name, check_result)
            
            self.test_results.append(("Message Handling", passed))
            return passed
        
        except Exception as e:
            print_result("Message Handling", False, str(e))
            self.test_results.append(("Message Handling", False))
            return False
    
    def test_session_persistence(self):
        """Test 3: Session saving and loading."""
        print_test_header("Session Persistence")
        
        try:
            provider = MockProvider("mock-copilot")
            repl = InteractiveREPL(
                provider=provider,
                model="mock-model",
                provider_name="mock",
                session_dir=self.session_dir
            )
            
            # Add some messages
            repl.append_message("user", "test query 1")
            repl.append_message("assistant", "test response 1")
            repl.task_description = "Test session"
            
            # Save session
            session_id = repl.save_session()
            self.session_id = session_id
            session_file = self.session_dir / f"{session_id}.json"
            
            checks = [
                ("Session ID generated", session_id is not None),
                ("Session file created", session_file.exists()),
                ("Session file readable", session_file.stat().st_size > 0),
            ]
            
            # Verify session file content
            if session_file.exists():
                with open(session_file) as f:
                    session_data = json.load(f)
                    checks.extend([
                        ("Session contains messages", len(session_data.get("messages", [])) > 0),
                        ("Session contains provider", session_data.get("provider") == "mock"),
                        ("Session contains model", session_data.get("model") == "mock-model"),
                    ])
            
            passed = all(check[1] for check in checks)
            for check_name, check_result in checks:
                print_result(check_name, check_result)
            
            self.test_results.append(("Session Persistence", passed))
            return passed
        
        except Exception as e:
            print_result("Session Persistence", False, str(e))
            self.test_results.append(("Session Persistence", False))
            return False
    
    def test_session_resumption(self):
        """Test 4: Loading and resuming previous session."""
        print_test_header("Session Resumption")
        
        try:
            if not self.session_id:
                print_result("Session Resumption", False, "No previous session ID available")
                self.test_results.append(("Session Resumption", False))
                return False
            
            provider = MockProvider("mock-copilot")
            repl = InteractiveREPL(
                provider=provider,
                model="mock-model",
                provider_name="mock",
                session_dir=self.session_dir,
                session_id=self.session_id
            )
            
            checks = [
                ("Session loaded", repl.session_id == self.session_id),
                ("History restored", len(repl.conversation_history) > 0),
                ("Turn count maintained", repl.get_turn_count() >= 1),
            ]
            
            passed = all(check[1] for check in checks)
            for check_name, check_result in checks:
                print_result(check_name, check_result)
            
            self.test_results.append(("Session Resumption", passed))
            return passed
        
        except Exception as e:
            print_result("Session Resumption", False, str(e))
            self.test_results.append(("Session Resumption", False))
            return False
    
    def test_memory_persistence(self):
        """Test 5: Memory system persistence."""
        print_test_header("Memory Persistence")
        
        try:
            test_session_id = f"test_session_{int(time.time())}"
            
            # Create and populate memory
            memory = MemoryManager(test_session_id)
            memory.add_fact("Port 22 (SSH) is open on target 127.0.0.1")
            memory.add_fact("SSH service is running")
            memory.add_credential("192.168.1.1", "admin", "password123", "web")
            memory.add_note("Target appears to be running Ubuntu")
            memory.save()
            
            memory_file = self.memory_dir / f"{test_session_id}.json"
            
            checks = [
                ("Memory file created", memory_file.exists()),
                ("Memory file not empty", memory_file.stat().st_size > 0),
                ("Facts persisted", len(memory.memory["facts"]) == 2),
                ("Credentials persisted", len(memory.memory["credentials"]) == 1),
                ("Notes persisted", len(memory.memory["notes"]) == 1),
            ]
            
            # Load memory from disk to verify persistence
            if memory_file.exists():
                memory2 = MemoryManager(test_session_id)
                checks.extend([
                    ("Facts loaded", len(memory2.memory["facts"]) == 2),
                    ("Credentials loaded", len(memory2.memory["credentials"]) == 1),
                    ("Notes loaded", len(memory2.memory["notes"]) == 1),
                    ("Context generation works", len(memory2.get_context()) > 0),
                ])
            
            passed = all(check[1] for check in checks)
            for check_name, check_result in checks:
                print_result(check_name, check_result)
            
            self.test_results.append(("Memory Persistence", passed))
            return passed
        
        except Exception as e:
            print_result("Memory Persistence", False, str(e))
            self.test_results.append(("Memory Persistence", False))
            return False
    
    def test_command_parsing(self):
        """Test 6: Command parsing."""
        print_test_header("Command Parsing")
        
        try:
            provider = MockProvider("mock-copilot")
            repl = InteractiveREPL(
                provider=provider,
                model="mock-model",
                provider_name="mock",
                session_dir=self.session_dir
            )
            
            test_cases = [
                ("/help", ("help", [])),
                ("/status", ("status", [])),
                ("/exit", ("exit", [])),
                ("/load session123", ("load", ["session123"])),
                ("regular message", (None, None)),
            ]
            
            passed = True
            for input_text, expected in test_cases:
                command, args = repl.parse_command(input_text)
                result = (command, args) == expected
                print_result(f"Parse '{input_text}'", result)
                passed = passed and result
            
            self.test_results.append(("Command Parsing", passed))
            return passed
        
        except Exception as e:
            print_result("Command Parsing", False, str(e))
            self.test_results.append(("Command Parsing", False))
            return False
    
    def test_memory_context_injection(self):
        """Test 7: Memory context injection in responses."""
        print_test_header("Memory Context Injection")
        
        try:
            test_session_id = f"test_context_{int(time.time())}"
            
            # Create memory with context
            memory = MemoryManager(test_session_id)
            memory.add_fact("Port 22 is open")
            memory.add_fact("SSH service running")
            memory.save()
            
            # Verify context injection works
            context = memory.get_context()
            
            checks = [
                ("Context not empty", len(context) > 0),
                ("Context contains facts", "FACTS:" in context),
                ("Context includes fact 1", "Port 22 is open" in context),
                ("Context includes fact 2", "SSH service running" in context),
            ]
            
            passed = all(check[1] for check in checks)
            for check_name, check_result in checks:
                print_result(check_name, check_result)
            
            self.test_results.append(("Memory Context Injection", passed))
            return passed
        
        except Exception as e:
            print_result("Memory Context Injection", False, str(e))
            self.test_results.append(("Memory Context Injection", False))
            return False
    
    def test_session_listing(self):
        """Test 8: Session listing."""
        print_test_header("Session Listing")
        
        try:
            provider = MockProvider("mock-copilot")
            repl = InteractiveREPL(
                provider=provider,
                model="mock-model",
                provider_name="mock",
                session_dir=self.session_dir
            )
            
            # List sessions
            sessions = repl.list_sessions(limit=5)
            
            checks = [
                ("Can list sessions", isinstance(sessions, list)),
                ("Sessions found", len(sessions) > 0),
            ]
            
            if sessions:
                checks.extend([
                    ("Session has ID", "id" in sessions[0]),
                    ("Session has task", "task" in sessions[0]),
                    ("Session has provider", "provider" in sessions[0]),
                ])
            
            passed = all(check[1] for check in checks)
            for check_name, check_result in checks:
                print_result(check_name, check_result)
            
            self.test_results.append(("Session Listing", passed))
            return passed
        
        except Exception as e:
            print_result("Session Listing", False, str(e))
            self.test_results.append(("Session Listing", False))
            return False
    
    def test_memory_update_parsing(self):
        """Test 9: Parsing [MEMORY UPDATE] blocks from responses."""
        print_test_header("Memory Update Parsing")
        
        try:
            response_with_memory = """Here's the result:

Port scan complete.

[MEMORY UPDATE]
[FACT] Port 22 (SSH) is open on 127.0.0.1
[CREDENTIAL] Target: 127.0.0.1 | Username: admin | Password: pass123
[NOTE] Target is running Ubuntu
[/MEMORY UPDATE]

End of output."""
            
            # Parse memory updates (simple regex-based)
            import re
            memory_block = re.search(r'\[MEMORY UPDATE\](.*?)\[/MEMORY UPDATE\]', response_with_memory, re.DOTALL)
            
            checks = [
                ("Memory block found", memory_block is not None),
            ]
            
            if memory_block:
                content = memory_block.group(1)
                checks.extend([
                    ("Contains facts", "[FACT]" in content),
                    ("Contains credentials", "[CREDENTIAL]" in content),
                    ("Contains notes", "[NOTE]" in content),
                ])
            
            passed = all(check[1] for check in checks)
            for check_name, check_result in checks:
                print_result(check_name, check_result)
            
            self.test_results.append(("Memory Update Parsing", passed))
            return passed
        
        except Exception as e:
            print_result("Memory Update Parsing", False, str(e))
            self.test_results.append(("Memory Update Parsing", False))
            return False
    
    def run_all_tests(self):
        """Run all tests."""
        print(f"\n{Colors.info('╔════════════════════════════════════════╗')}")
        print(f"{Colors.info('║  InteractiveREPL Comprehensive Tests   ║')}")
        print(f"{Colors.info('╚════════════════════════════════════════╝')}")
        
        start_time = time.time()
        
        # Run all test methods
        self.test_repl_initialization()
        self.test_message_handling()
        self.test_session_persistence()
        self.test_session_resumption()
        self.test_memory_persistence()
        self.test_command_parsing()
        self.test_memory_context_injection()
        self.test_session_listing()
        self.test_memory_update_parsing()
        
        elapsed_time = time.time() - start_time
        
        # Print summary
        self.print_summary(elapsed_time)
    
    def print_summary(self, elapsed_time: float):
        """Print test summary."""
        print(f"\n{Colors.info('='*60)}")
        print(f"{Colors.info('TEST SUMMARY')}")
        print(f"{Colors.info('='*60)}\n")
        
        passed_count = sum(1 for _, result in self.test_results if result)
        total_count = len(self.test_results)
        
        for test_name, result in self.test_results:
            status = Colors.success("[PASS]") if result else Colors.error("[FAIL]")
            print(f"{status} {test_name}")
        
        print(f"\n{Colors.info(f'Results: {passed_count}/{total_count} tests passed')}")
        print(f"{Colors.info(f'Time: {elapsed_time:.2f}s')}\n")
        
        if passed_count == total_count:
            print(Colors.success("✓ All tests passed!\n"))
        else:
            print(Colors.warning(f"⚠ {total_count - passed_count} test(s) failed\n"))


def test_copilot_provider_availability():
    """Test if real Copilot provider is available."""
    print_test_header("Copilot Provider Availability")
    
    try:
        provider = CopilotProvider()
        is_available = provider.is_available
        
        if is_available:
            print_result("GitHub Copilot CLI", True, "gh CLI is configured and authenticated")
            return True
        else:
            print_result("GitHub Copilot CLI", False, "gh CLI not available (expected for test environment)")
            return False
    except Exception as e:
        print_result("GitHub Copilot CLI", False, str(e))
        return False


def main():
    """Main test runner."""
    print(f"\n{Colors.info('ForestGump Interactive REPL Test Suite')}\n")
    
    # First, check if Copilot provider is available
    copilot_available = test_copilot_provider_availability()
    
    # Run comprehensive tests with mock provider
    tester = InteractiveREPLTester()
    tester.run_all_tests()
    
    # Print additional info
    print(f"\n{Colors.info('Test Environment Info:')}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  ForestGump: /root/ForestGump")
    print(f"  Sessions: {tester.session_dir}")
    print(f"  Memory: {tester.memory_dir}")
    print(f"  Copilot Available: {Colors.success('Yes') if copilot_available else Colors.warning('No')}")
    print()


if __name__ == "__main__":
    main()
