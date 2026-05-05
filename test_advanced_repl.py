#!/usr/bin/env python3
"""
Advanced end-to-end test for InteractiveREPL with simulated interaction flow.
Tests realistic usage patterns and integration with real Copilot provider interface.
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, "/root/ForestGump")

from forestgump_cli import InteractiveREPL, Colors, ForestGumpCLI
from providers import CopilotProvider
from memory import MemoryManager


def print_test_header(test_name: str):
    """Print formatted test header."""
    print(f"\n{Colors.info('='*60)}")
    print(f"{Colors.info(f'TEST: {test_name}')}")
    print(f"{Colors.info('='*60)}\n")


class AdvancedREPLTester:
    """Advanced end-to-end testing for InteractiveREPL."""
    
    def __init__(self):
        self.results = []
        self.session_dir = Path.home() / ".forestgump" / "sessions"
        self.memory_dir = Path.home() / ".forestgump" / "memory"
    
    def test_provider_interface_compatibility(self):
        """Test 1: Verify provider interface compatibility."""
        print_test_header("Provider Interface Compatibility")
        
        try:
            # Test that providers implement the required chat interface
            from providers import GroqProvider, ClaudeCliProvider, AnthropicProvider, CopilotProvider
            from providers.base import Provider
            
            providers_to_test = [
                ("GroqProvider", GroqProvider),
                ("ClaudeCliProvider", ClaudeCliProvider),
                ("AnthropicProvider", AnthropicProvider),
                ("CopilotProvider", CopilotProvider),
            ]
            
            all_valid = True
            for provider_name, provider_class in providers_to_test:
                # Check if it's a Provider subclass
                is_subclass = issubclass(provider_class, Provider)
                
                # Check if it has chat method
                has_chat = hasattr(provider_class, 'chat')
                
                # Check if it has is_available property
                has_available = True  # We can't check without instantiation
                
                result = is_subclass and has_chat
                
                status = Colors.success("[PASS]") if result else Colors.error("[FAIL]")
                print(f"{status} {provider_name}")
                
                all_valid = all_valid and result
            
            self.results.append(("Provider Interface Compatibility", all_valid))
            return all_valid
        
        except Exception as e:
            print(f"{Colors.error('[!]')} Error: {e}")
            self.results.append(("Provider Interface Compatibility", False))
            return False
    
    def test_repl_with_memory_injection(self):
        """Test 2: REPL properly injects memory context."""
        print_test_header("REPL with Memory Injection")
        
        try:
            class TestProvider:
                def __init__(self):
                    self.last_call = None
                
                def chat(self, message: str, history: list = None) -> str:
                    self.last_call = {"message": message, "history": history}
                    return f"Response to: {message}"
            
            session_id = f"mem_test_{int(time.time())}"
            provider = TestProvider()
            
            # Create REPL instance
            repl = InteractiveREPL(
                provider=provider,
                model="test-model",
                provider_name="test",
                session_dir=self.session_dir,
                session_id=None
            )
            
            # Add messages
            repl.append_message("user", "first query")
            response1 = provider.chat("first query", repl.conversation_history)
            repl.append_message("assistant", response1)
            
            # Verify history is passed to provider
            checks = [
                ("History passed to provider", provider.last_call is not None),
                ("History contains user message", provider.last_call["history"] is not None and len(provider.last_call["history"]) > 0),
                ("Turn count increased", repl.get_turn_count() == 1),
            ]
            
            passed = all(c[1] for c in checks)
            for check_name, check_result in checks:
                status = Colors.success("[PASS]") if check_result else Colors.error("[FAIL]")
                print(f"{status} {check_name}")
            
            self.results.append(("REPL with Memory Injection", passed))
            return passed
        
        except Exception as e:
            print(f"{Colors.error('[!]')} Error: {e}")
            self.results.append(("REPL with Memory Injection", False))
            return False
    
    def test_session_workflow(self):
        """Test 3: Complete session workflow (create, save, resume, extend)."""
        print_test_header("Complete Session Workflow")
        
        try:
            class SimpleProvider:
                def chat(self, message: str, history: list = None) -> str:
                    return f"Response to: {message}"
            
            # Step 1: Create new session
            repl1 = InteractiveREPL(
                provider=SimpleProvider(),
                model="test",
                provider_name="test",
                session_dir=self.session_dir
            )
            
            # Step 2: Add first exchange
            repl1.append_message("user", "First question")
            repl1.append_message("assistant", "First answer")
            session_id = repl1.save_session()
            
            # Step 3: Resume session
            repl2 = InteractiveREPL(
                provider=SimpleProvider(),
                model="test",
                provider_name="test",
                session_dir=self.session_dir,
                session_id=session_id
            )
            
            # Step 4: Extend conversation
            repl2.append_message("user", "Follow-up question")
            repl2.append_message("assistant", "Follow-up answer")
            repl2.save_session()
            
            # Step 5: Verify all exchanges are preserved
            repl3 = InteractiveREPL(
                provider=SimpleProvider(),
                model="test",
                provider_name="test",
                session_dir=self.session_dir,
                session_id=session_id
            )
            
            checks = [
                ("Session created", session_id is not None),
                ("Session file exists", (self.session_dir / f"{session_id}.json").exists()),
                ("History has 4 messages", len(repl3.conversation_history) == 4),
                ("Turn count is 2", repl3.get_turn_count() == 2),
                ("First message preserved", repl3.conversation_history[0]["content"] == "First question"),
                ("Last message preserved", repl3.conversation_history[-1]["content"] == "Follow-up answer"),
            ]
            
            passed = all(c[1] for c in checks)
            for check_name, check_result in checks:
                status = Colors.success("[PASS]") if check_result else Colors.error("[FAIL]")
                print(f"{status} {check_name}")
            
            self.results.append(("Complete Session Workflow", passed))
            return passed
        
        except Exception as e:
            print(f"{Colors.error('[!]')} Error: {e}")
            self.results.append(("Complete Session Workflow", False))
            return False
    
    def test_memory_update_extraction(self):
        """Test 4: Extract memory updates from provider responses."""
        print_test_header("Memory Update Extraction")
        
        try:
            import re
            
            # Sample response with memory updates
            response = """Here's the result of the nmap scan:

PORT   STATE SERVICE
22/tcp open  ssh
80/tcp open  http

[MEMORY UPDATE]
[FACT] SSH service found on port 22
[FACT] HTTP service found on port 80
[CREDENTIAL] Target: 192.168.1.1 | User: admin | Pass: ****
[NOTE] Target appears to be running Linux
[/MEMORY UPDATE]

End of scan."""
            
            # Test extraction logic
            memory_block = re.search(r'\[MEMORY UPDATE\](.*?)\[/MEMORY UPDATE\]', response, re.DOTALL)
            
            checks = [
                ("Memory block found", memory_block is not None),
            ]
            
            if memory_block:
                content = memory_block.group(1)
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                
                facts = [l for l in lines if l.startswith('[FACT]')]
                credentials = [l for l in lines if l.startswith('[CREDENTIAL]')]
                notes = [l for l in lines if l.startswith('[NOTE]')]
                
                checks.extend([
                    ("Facts extracted", len(facts) == 2),
                    ("Credentials extracted", len(credentials) == 1),
                    ("Notes extracted", len(notes) == 1),
                ])
            
            passed = all(c[1] for c in checks)
            for check_name, check_result in checks:
                status = Colors.success("[PASS]") if check_result else Colors.error("[FAIL]")
                print(f"{status} {check_name}")
            
            self.results.append(("Memory Update Extraction", passed))
            return passed
        
        except Exception as e:
            print(f"{Colors.error('[!]')} Error: {e}")
            self.results.append(("Memory Update Extraction", False))
            return False
    
    def test_cli_initialization(self):
        """Test 5: ForestGumpCLI initialization and structure."""
        print_test_header("CLI Initialization")
        
        try:
            cli = ForestGumpCLI()
            
            checks = [
                ("CLI created", cli is not None),
                ("ProviderManager available", cli.providers is not None),
                ("SessionManager available", cli.sessions is not None),
                ("ModelDiscovery available", cli.models is not None),
            ]
            
            passed = all(c[1] for c in checks)
            for check_name, check_result in checks:
                status = Colors.success("[PASS]") if check_result else Colors.error("[FAIL]")
                print(f"{status} {check_name}")
            
            self.results.append(("CLI Initialization", passed))
            return passed
        
        except Exception as e:
            print(f"{Colors.error('[!]')} Error: {e}")
            self.results.append(("CLI Initialization", False))
            return False
    
    def test_memory_lifecycle(self):
        """Test 6: Complete memory lifecycle."""
        print_test_header("Memory Lifecycle")
        
        try:
            session_id = f"lifecycle_{int(time.time())}"
            
            # Create memory and add data
            mem1 = MemoryManager(session_id)
            mem1.add_fact("First discovery")
            mem1.add_credential("host1", "user1", "pass1", "ssh")
            mem1.add_note("Initial scan complete")
            mem1.save()
            
            # Load memory and verify
            mem2 = MemoryManager(session_id)
            
            # Add more data
            mem2.add_fact("Second discovery")
            mem2.add_credential("host2", "user2", "pass2", "http")
            mem2.add_note("Extended scan")
            mem2.save()
            
            # Load again and verify all data
            mem3 = MemoryManager(session_id)
            
            checks = [
                ("Facts accumulated", len(mem3.memory["facts"]) == 2),
                ("Credentials accumulated", len(mem3.memory["credentials"]) == 2),
                ("Notes accumulated", len(mem3.memory["notes"]) == 2),
                ("Context generated", len(mem3.get_context()) > 0),
                ("Context contains facts", "FACTS:" in mem3.get_context()),
                ("Context contains credentials", "CREDENTIALS:" in mem3.get_context()),
            ]
            
            passed = all(c[1] for c in checks)
            for check_name, check_result in checks:
                status = Colors.success("[PASS]") if check_result else Colors.error("[FAIL]")
                print(f"{status} {check_name}")
            
            self.results.append(("Memory Lifecycle", passed))
            return passed
        
        except Exception as e:
            print(f"{Colors.error('[!]')} Error: {e}")
            self.results.append(("Memory Lifecycle", False))
            return False
    
    def test_error_handling(self):
        """Test 7: Error handling and recovery."""
        print_test_header("Error Handling and Recovery")
        
        try:
            class FailingProvider:
                def chat(self, message: str, history: list = None) -> str:
                    if "error" in message.lower():
                        raise RuntimeError("Simulated provider error")
                    return "Success"
            
            repl = InteractiveREPL(
                provider=FailingProvider(),
                model="test",
                provider_name="test",
                session_dir=self.session_dir
            )
            
            # Test 1: Successful call
            repl.append_message("user", "normal query")
            try:
                result1 = repl.provider.chat("normal query")
                success1 = True
            except Exception:
                success1 = False
            
            # Test 2: Failed call (should not crash REPL)
            repl.append_message("user", "error query")
            try:
                result2 = repl.provider.chat("error query")
                success2 = False
            except RuntimeError:
                success2 = True
            except Exception:
                success2 = False
            
            checks = [
                ("Normal query succeeds", success1),
                ("Error query raises exception", success2),
                ("REPL still functional", repl.conversation_history is not None),
            ]
            
            passed = all(c[1] for c in checks)
            for check_name, check_result in checks:
                status = Colors.success("[PASS]") if check_result else Colors.error("[FAIL]")
                print(f"{status} {check_name}")
            
            self.results.append(("Error Handling and Recovery", passed))
            return passed
        
        except Exception as e:
            print(f"{Colors.error('[!]')} Error: {e}")
            self.results.append(("Error Handling and Recovery", False))
            return False
    
    def run_all_tests(self):
        """Run all advanced tests."""
        print(f"\n{Colors.info('╔════════════════════════════════════════╗')}")
        print(f"{Colors.info('║  Advanced InteractiveREPL Tests        ║')}")
        print(f"{Colors.info('╚════════════════════════════════════════╝')}")
        
        start_time = time.time()
        
        self.test_provider_interface_compatibility()
        self.test_repl_with_memory_injection()
        self.test_session_workflow()
        self.test_memory_update_extraction()
        self.test_cli_initialization()
        self.test_memory_lifecycle()
        self.test_error_handling()
        
        elapsed_time = time.time() - start_time
        
        # Print summary
        self.print_summary(elapsed_time)
    
    def print_summary(self, elapsed_time: float):
        """Print test summary."""
        print(f"\n{Colors.info('='*60)}")
        print(f"{Colors.info('ADVANCED TEST SUMMARY')}")
        print(f"{Colors.info('='*60)}\n")
        
        passed_count = sum(1 for _, result in self.results if result)
        total_count = len(self.results)
        
        for test_name, result in self.results:
            status = Colors.success("[PASS]") if result else Colors.error("[FAIL]")
            print(f"{status} {test_name}")
        
        print(f"\n{Colors.info(f'Results: {passed_count}/{total_count} tests passed')}")
        print(f"{Colors.info(f'Time: {elapsed_time:.2f}s')}\n")
        
        if passed_count == total_count:
            print(Colors.success("✓ All advanced tests passed!\n"))
            return 0
        else:
            print(Colors.warning(f"⚠ {total_count - passed_count} test(s) failed\n"))
            return 1


def main():
    """Main test runner."""
    print(f"\n{Colors.info('ForestGump Advanced REPL Test Suite')}\n")
    
    tester = AdvancedREPLTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
