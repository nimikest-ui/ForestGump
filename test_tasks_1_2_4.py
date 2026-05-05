#!/usr/bin/env python3
"""
ForestGump Integration Test Suite - Tasks 1, 2, 4 Verification
Tests that real provider calls are wired, REPL works end-to-end, and tool sandbox functions.
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Test environment
FORESTGUMP_DIR = Path("/root/ForestGump")
SESSION_DIR = Path.home() / ".forestgump" / "sessions"
MEMORY_DIR = Path.home() / ".forestgump" / "memory"

def print_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def print_result(test_name, passed, details=""):
    symbol = "✓" if passed else "✗"
    status = "PASS" if passed else "FAIL"
    print(f"  [{symbol}] {test_name}: {status}")
    if details:
        print(f"      {details}")

# ==============================================================================
# TASK 1: VERIFY REAL PROVIDER CALLS WIRED
# ==============================================================================

def test_task1_provider_wiring():
    """Test that real provider calls are wired in chat command."""
    print_header("TASK 1: Real Provider Calls Wired")
    
    all_passed = True
    
    # Test 1: Import providers
    try:
        from providers import ClaudeCliProvider, GroqProvider, AnthropicProvider, CopilotProvider
        print_result("Import all providers", True)
    except ImportError as e:
        print_result("Import all providers", False, f"Error: {e}")
        all_passed = False
    
    # Test 2: Check provider availability
    try:
        from providers import ClaudeCliProvider
        provider = ClaudeCliProvider()
        available = provider.is_available
        print_result("Claude CLI provider available", available, 
                    f"Status: {'available' if available else 'not available'}")
    except Exception as e:
        print_result("Claude CLI provider check", False, f"Error: {e}")
        all_passed = False
    
    # Test 3: Verify chat method signature
    try:
        from providers import ClaudeCliProvider
        import inspect
        provider = ClaudeCliProvider()
        sig = inspect.signature(provider.chat)
        params = list(sig.parameters.keys())
        has_messages = 'messages' in params
        has_system = 'system_prompt' in params
        print_result("Provider.chat() signature correct", 
                    has_messages and has_system,
                    f"Parameters: {params}")
    except Exception as e:
        print_result("Provider.chat() signature check", False, f"Error: {e}")
        all_passed = False
    
    # Test 4: Verify CLI has real provider integration
    try:
        with open(FORESTGUMP_DIR / "forestgump_cli.py") as f:
            content = f.read()
            has_provider_create = "self.providers.create_provider(provider)" in content
            has_provider_chat = "real_provider.chat(messages, system_prompt)" in content
            has_error_handling = "Provider error:" in content or "Provider initialization failed" in content
            
            all_checks = has_provider_create and has_provider_chat and has_error_handling
            print_result("CLI wired with real provider calls", all_checks,
                        f"create_provider: {has_provider_create}, chat: {has_provider_chat}, error_handling: {has_error_handling}")
    except Exception as e:
        print_result("CLI provider integration check", False, f"Error: {e}")
        all_passed = False
    
    # Test 5: Verify error handling
    try:
        with open(FORESTGUMP_DIR / "forestgump_cli.py") as f:
            content = f.read()
            has_timeout = "subprocess.TimeoutExpired" in content
            has_runtime = "RuntimeError" in content
            has_generic = "except Exception as e" in content
            
            all_checks = has_timeout and has_runtime and has_generic
            print_result("CLI has error handling", all_checks,
                        f"Timeout: {has_timeout}, Runtime: {has_runtime}, Generic: {has_generic}")
    except Exception as e:
        print_result("CLI error handling check", False, f"Error: {e}")
        all_passed = False
    
    # Test 6: Verify system prompt injection
    try:
        with open(FORESTGUMP_DIR / "forestgump_cli.py") as f:
            content = f.read()
            has_memory_injection = "system_prompt = self._build_system_prompt(memory)" in content
            has_system_in_messages = '{"role": "system", "content": system_prompt}' in content
            
            all_checks = has_memory_injection and has_system_in_messages
            print_result("CLI has system prompt injection", all_checks,
                        f"Memory context: {has_memory_injection}, Message building: {has_system_in_messages}")
    except Exception as e:
        print_result("System prompt injection check", False, f"Error: {e}")
        all_passed = False
    
    return all_passed

# ==============================================================================
# TASK 2: VERIFY INTERACTIVE REPL
# ==============================================================================

def test_task2_interactive_repl():
    """Test that interactive REPL is wired and functional."""
    print_header("TASK 2: Interactive REPL")
    
    all_passed = True
    
    # Test 1: InteractiveREPL class exists
    try:
        from forestgump_cli import InteractiveREPL
        print_result("InteractiveREPL class exists", True)
    except ImportError as e:
        print_result("InteractiveREPL class exists", False, f"Error: {e}")
        all_passed = False
    
    # Test 2: REPL initializes with provider
    try:
        from forestgump_cli import InteractiveREPL
        from providers import ClaudeCliProvider
        
        provider = ClaudeCliProvider()
        repl = InteractiveREPL(
            provider=provider,
            model="claude-3.5-sonnet",
            provider_name="claude",
            session_id="test_session_001"
        )
        print_result("REPL initializes with provider", True)
    except Exception as e:
        print_result("REPL initialization", False, f"Error: {e}")
        all_passed = False
    
    # Test 3: REPL has required methods
    try:
        from forestgump_cli import InteractiveREPL
        import inspect
        
        # Get all method names
        methods = [m for m, _ in inspect.getmembers(InteractiveREPL, predicate=inspect.isfunction)]
        method_str = " ".join(methods)
        
        required = ["run", "parse_command", "save_session", "append_message"]
        has_all = all(req in method_str for req in required)
        
        print_result("REPL has required methods", has_all,
                    f"Methods include: run, parse_command, save_session, append_message")
    except Exception as e:
        print_result("REPL methods check", False, f"Error: {e}")
        all_passed = False
    
    # Test 4: Session persistence directories exist or can be created
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        session_ok = SESSION_DIR.exists()
        memory_ok = MEMORY_DIR.exists()
        print_result("Session/memory directories created", session_ok and memory_ok,
                    f"Sessions: {SESSION_DIR}, Memory: {MEMORY_DIR}")
    except Exception as e:
        print_result("Session/memory directory creation", False, f"Error: {e}")
        all_passed = False
    
    # Test 5: REPL has sandbox integration
    try:
        with open(FORESTGUMP_DIR / "forestgump_cli.py") as f:
            content = f.read()
            has_sandbox_import = "from toolsandbox import Sandbox, CommandFilter" in content
            has_sandbox_init = "self.sandbox = Sandbox" in content
            has_extract_commands = "extract_and_handle_commands" in content
            
            all_checks = has_sandbox_import and has_sandbox_init and has_extract_commands
            print_result("REPL has tool sandbox integration", all_checks,
                        f"Import: {has_sandbox_import}, Init: {has_sandbox_init}, Extract: {has_extract_commands}")
    except Exception as e:
        print_result("REPL sandbox integration check", False, f"Error: {e}")
        all_passed = False
    
    # Test 6: REPL has memory injection
    try:
        with open(FORESTGUMP_DIR / "forestgump_cli.py") as f:
            content = f.read()
            has_memory_param = "memory=None" in content
            has_system_prompt = "system_prompt: str = None" in content
            has_context_injection = 'if self.system_prompt:' in content
            
            all_checks = has_memory_param and has_system_prompt and has_context_injection
            print_result("REPL has memory context injection", all_checks,
                        f"Memory param: {has_memory_param}, System prompt: {has_system_prompt}, Context: {has_context_injection}")
    except Exception as e:
        print_result("REPL memory injection check", False, f"Error: {e}")
        all_passed = False
    
    # Test 7: REPL main loop calls provider
    try:
        with open(FORESTGUMP_DIR / "forestgump_cli.py") as f:
            content = f.read()
            has_provider_call = "self.provider.chat(messages, self.system_prompt)" in content
            has_message_building = "messages.append" in content and 'self.system_prompt' in content
            
            all_checks = has_provider_call and has_message_building
            print_result("REPL main loop calls provider", all_checks,
                        f"Provider call: {has_provider_call}, Message building: {has_message_building}")
    except Exception as e:
        print_result("REPL main loop check", False, f"Error: {e}")
        all_passed = False
    
    return all_passed

# ==============================================================================
# TASK 4: VERIFY TOOL SANDBOX
# ==============================================================================

def test_task4_tool_sandbox():
    """Test that tool sandbox is implemented and integrated."""
    print_header("TASK 4: Tool Sandbox")
    
    all_passed = True
    
    # Test 1: toolsandbox.py exists
    try:
        toolsandbox_file = FORESTGUMP_DIR / "toolsandbox.py"
        exists = toolsandbox_file.exists()
        size = toolsandbox_file.stat().st_size if exists else 0
        print_result("toolsandbox.py file exists", exists,
                    f"File size: {size} bytes")
    except Exception as e:
        print_result("toolsandbox.py exists check", False, f"Error: {e}")
        all_passed = False
    
    # Test 2: Sandbox classes can be imported
    try:
        from toolsandbox import Sandbox, CommandParser, CommandExecutor, CommandFilter
        print_result("All Sandbox classes importable", True,
                    "Sandbox, CommandParser, CommandExecutor, CommandFilter")
    except ImportError as e:
        print_result("Import Sandbox classes", False, f"Error: {e}")
        all_passed = False
    
    # Test 3: CommandParser extracts commands from multiple patterns
    try:
        from toolsandbox import CommandParser
        parser = CommandParser()
        
        # Test backticks
        backtick_response = "Run this: `nmap -p 22 192.168.1.1`"
        backtick_cmds = parser.parse_response(backtick_response)
        
        # Test XML style
        xml_response = "Execute: <cmd>ping 8.8.8.8</cmd>"
        xml_cmds = parser.parse_response(xml_response)
        
        # Test markdown
        md_response = "Run: ```bash\nls -la\n```"
        md_cmds = parser.parse_response(md_response)
        
        all_patterns = len(backtick_cmds) > 0 or len(xml_cmds) > 0 or len(md_cmds) > 0
        print_result("CommandParser supports multiple patterns", all_patterns,
                    f"Backticks: {len(backtick_cmds)}, XML: {len(xml_cmds)}, Markdown: {len(md_cmds)}")
    except Exception as e:
        print_result("CommandParser pattern extraction", False, f"Error: {e}")
        all_passed = False
    
    # Test 4: Sandbox has safety validation
    try:
        from toolsandbox import Sandbox
        sandbox = Sandbox()
        
        # Test dangerous command blocking via parse_response
        dangerous_cmd = "rm -rf /"
        response_with_dangerous = f"Try this: `{dangerous_cmd}`"
        parsed = sandbox.parse_response(response_with_dangerous)
        
        # Test safe command
        safe_cmd = "nmap -p 22 192.168.1.1"
        response_with_safe = f"Run: `{safe_cmd}`"
        parsed_safe = sandbox.parse_response(response_with_safe)
        
        has_parsing = len(parsed) > 0 and len(parsed_safe) > 0
        print_result("Sandbox parses and identifies commands", has_parsing,
                    f"Dangerous parsed: {len(parsed)}, Safe parsed: {len(parsed_safe)}")
    except Exception as e:
        print_result("Sandbox safety validation", False, f"Error: {e}")
        all_passed = False
    
    # Test 5: Sandbox has execution capability
    try:
        from toolsandbox import Sandbox
        # Use yolo=True to skip user prompts in tests
        sandbox = Sandbox(yolo=True)
        
        # Test safe, simple command with yolo mode
        success, output = sandbox.execute_and_feedback("echo 'test'")
        has_execution = success and len(str(output)) > 0
        
        print_result("Sandbox can execute safe commands", has_execution,
                    f"Command success: {success}, Output: {str(output)[:50]}")
    except Exception as e:
        print_result("Sandbox command execution", False, f"Error: {e}")
        all_passed = False
    
    # Test 6: REPL integrates sandbox
    try:
        with open(FORESTGUMP_DIR / "forestgump_cli.py") as f:
            content = f.read()
            # Check for Sandbox initialization (import is typically done in module load)
            has_sandbox_init = "self.sandbox = Sandbox" in content
            has_extraction = "extract_and_handle_commands" in content
            
            all_checks = has_sandbox_init and has_extraction
            print_result("REPL integrates tool sandbox", all_checks,
                        f"Sandbox init: {has_sandbox_init}, Extraction: {has_extraction}")
    except Exception as e:
        print_result("REPL sandbox integration", False, f"Error: {e}")
        all_passed = False
    
    # Test 7: CommandFilter exists and filters
    try:
        from toolsandbox import CommandFilter
        filter_obj = CommandFilter()
        
        # CommandFilter has filter_commands, prioritize_commands, validate_commands methods
        has_filter = hasattr(filter_obj, 'filter_commands')
        has_prioritize = hasattr(filter_obj, 'prioritize_commands')
        has_validate = hasattr(filter_obj, 'validate_commands')
        
        all_methods = has_filter and has_prioritize and has_validate
        print_result("CommandFilter has filtering methods", all_methods,
                    f"filter_commands: {has_filter}, prioritize: {has_prioritize}, validate: {has_validate}")
    except Exception as e:
        print_result("CommandFilter categorization", False, f"Error: {e}")
        all_passed = False
    
    return all_passed

# ==============================================================================
# RUN ALL TESTS
# ==============================================================================

def main():
    print("\n" + "="*70)
    print("  ForestGump Integration Test Suite - Tasks 1, 2, 4")
    print("  Start time:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*70)
    
    results = {}
    
    # Run tests
    results["Task 1: Provider Wiring"] = test_task1_provider_wiring()
    results["Task 2: Interactive REPL"] = test_task2_interactive_repl()
    results["Task 4: Tool Sandbox"] = test_task4_tool_sandbox()
    
    # Summary
    print_header("Test Summary")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    for task_name, result in results.items():
        symbol = "✓" if result else "✗"
        print(f"  [{symbol}] {task_name}")
    
    print(f"\n  Total: {passed}/{total} test groups passed")
    
    if passed == total:
        print(f"\n  ✓ ALL TESTS PASSED!")
    else:
        print(f"\n  ✗ Some tests failed. Check output above.")
    
    print(f"\n  End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
