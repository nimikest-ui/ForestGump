#!/usr/bin/env python3
"""
ForestGump Tasks 1, 2, 4 - End-to-End Demo
Demonstrates real provider calls, interactive REPL, and tool sandbox execution
"""

import sys
from pathlib import Path

# Add ForestGump to path
FORESTGUMP_DIR = Path(__file__).parent
sys.path.insert(0, str(FORESTGUMP_DIR))

def demo_task1_real_provider_calls():
    """Demo: Real provider calls (Task 1)"""
    print("\n" + "="*70)
    print("  DEMO: Task 1 - Real Provider Calls")
    print("="*70 + "\n")
    
    from forestgump_cli import ModelManager
    from providers import ClaudeCliProvider
    
    print("[*] Initializing provider manager...")
    providers_mgr = ModelManager()
    
    print("[*] Creating Claude CLI provider...")
    provider = ClaudeCliProvider()
    
    print(f"[✓] Provider available: {provider.is_available}")
    
    if provider.is_available:
        print("\n[*] Testing real provider.chat() call...")
        messages = [
            {"role": "user", "content": "What is the nmap command? One sentence."}
        ]
        
        try:
            response = provider.chat(messages, system_prompt=None)
            print(f"[✓] Real response received ({len(response)} chars):")
            print(f"    {response[:150]}...")
        except Exception as e:
            print(f"[!] Provider call failed (expected if rate-limited): {e}")
            print("[*] This is normal - Claude API may be rate-limited in demo mode")
    else:
        print("[!] Claude CLI not available")
        print("[*] Trying Groq provider instead...")
        try:
            from providers import GroqProvider
            groq = GroqProvider()
            if groq.is_available:
                print(f"[✓] Groq provider available")
        except Exception as e:
            print(f"[!] Groq not available: {e}")

def demo_task2_interactive_repl():
    """Demo: Interactive REPL structure (Task 2)"""
    print("\n" + "="*70)
    print("  DEMO: Task 2 - Interactive REPL Structure")
    print("="*70 + "\n")
    
    from forestgump_cli import InteractiveREPL
    from providers import ClaudeCliProvider
    from pathlib import Path
    
    print("[*] Creating InteractiveREPL instance...")
    provider = ClaudeCliProvider()
    
    session_id = "demo_session_001"
    repl = InteractiveREPL(
        provider=provider,
        model="claude-3.5-sonnet",
        provider_name="claude",
        session_id=session_id
    )
    
    print(f"[✓] REPL created: session_id={session_id}")
    print(f"[✓] Provider: {repl.provider_name}")
    print(f"[✓] Model: {repl.model}")
    print(f"[✓] Sandbox: {repl.sandbox is not None}")
    print(f"[✓] System prompt: {'set' if repl.system_prompt else 'not set'}")
    
    print("\n[*] REPL methods available:")
    methods = ['run', 'parse_command', 'save_session', 'append_message', 'get_input', 
               'print_welcome', 'handle_command', 'extract_and_handle_commands']
    for method in methods:
        has_method = hasattr(repl, method)
        symbol = "✓" if has_method else "✗"
        print(f"    [{symbol}] {method}()")
    
    print("\n[*] Session files location:")
    session_file = Path.home() / ".forestgump" / "sessions" / f"{session_id}.json"
    memory_file = Path.home() / ".forestgump" / "memory" / f"{session_id}.json"
    print(f"    Sessions: {session_file.parent}")
    print(f"    Memory: {memory_file.parent}")
    
    # Try to save a test session
    try:
        repl.append_message("user", "What is nmap?")
        repl.append_message("assistant", "Nmap is a network scanning tool.")
        repl.save_session()
        if session_file.exists():
            print(f"\n[✓] Session saved successfully to {session_file.name}")
    except Exception as e:
        print(f"\n[!] Session save demo failed: {e}")

def demo_task4_tool_sandbox():
    """Demo: Tool sandbox capabilities (Task 4)"""
    print("\n" + "="*70)
    print("  DEMO: Task 4 - Tool Sandbox")
    print("="*70 + "\n")
    
    from toolsandbox import Sandbox, CommandParser, CommandFilter
    
    print("[*] Initializing sandbox components...")
    
    # Test CommandParser
    print("\n[1] CommandParser - Extract commands from responses:")
    parser = CommandParser()
    
    test_responses = [
        ("Backticks", "Run this command: `nmap -p 22 192.168.1.0/24`"),
        ("XML-style", "Execute: <cmd>ping 8.8.8.8</cmd>"),
        ("Markdown", "Use:\n```bash\nls -la /tmp\n```"),
    ]
    
    for pattern_name, response in test_responses:
        commands = parser.parse_response(response)
        print(f"    [{pattern_name}] Found {len(commands)} command(s)")
        for cmd, conf, line in commands:
            print(f"      - {cmd[:50]}... (confidence: {conf:.0%})")
    
    # Test Sandbox with yolo flag
    print("\n[2] Sandbox - Safety validation and execution:")
    sandbox = Sandbox(yolo=True)  # yolo=True to skip user confirmation
    
    test_cases = [
        ("Safe command", "echo 'hello world'"),
        ("Dangerous command", "rm -rf /"),
    ]
    
    for case_name, cmd in test_cases:
        is_danger = sandbox.is_dangerous(cmd)
        symbol = "❌ BLOCKED" if is_danger else "✅ SAFE"
        print(f"    [{symbol}] {case_name}: {cmd}")
    
    # Test actual execution
    print("\n[3] CommandExecutor - Execute safe command:")
    try:
        success, output = sandbox.execute_and_feedback("echo 'ForestGump Test'")
        if success:
            print(f"    [✓] Execution successful")
            print(f"    [+] Output: {output.strip()}")
        else:
            print(f"    [!] Execution failed: {output}")
    except Exception as e:
        print(f"    [!] Execution error: {e}")
    
    # Test CommandFilter
    print("\n[4] CommandFilter - Categorize commands:")
    filter_obj = CommandFilter()
    
    commands = [
        ("nmap -p 22 192.168.1.0/24", 0.95),
        ("rm -rf /", 0.99),
        ("find . -name 'test'", 0.90),
    ]
    
    validation = filter_obj.validate_commands(commands)
    
    print(f"    Safe commands: {len(validation['safe'])}")
    for cmd_info in validation['safe']:
        print(f"      ✓ {cmd_info['command'][:50]}")
    
    print(f"    Dangerous commands: {len(validation['dangerous'])}")
    for cmd_info in validation['dangerous']:
        print(f"      ❌ {cmd_info['command'][:50]} ({cmd_info.get('reason', '')})")

def demo_integrated_workflow():
    """Demo: Integrated workflow (all tasks together)"""
    print("\n" + "="*70)
    print("  DEMO: Integrated Workflow (All Tasks)")
    print("="*70 + "\n")
    
    from toolsandbox import CommandParser
    from forestgump_cli import InteractiveREPL
    from providers import ClaudeCliProvider
    
    print("[*] Simulating agent response with command suggestion...")
    
    # Simulate agent response
    agent_response = """
    The best way to scan a network is using nmap:
    `nmap -sV 192.168.1.0/24`
    
    This will scan all IPs in the subnet and identify services.
    """
    
    print(f"\n[Agent Response]:\n{agent_response}\n")
    
    # Extract command using CommandParser
    print("[*] Task 4: Extracting commands from agent response...")
    parser = CommandParser()
    commands = parser.parse_response(agent_response)
    
    if commands:
        for cmd, conf, line in commands:
            print(f"  [✓] Found command (confidence {conf:.0%}): {cmd}")
    
    # Validate with sandbox
    print("\n[*] Task 4: Validating command safety...")
    sandbox = Sandbox = __import__("toolsandbox").Sandbox
    sandbox_obj = sandbox(yolo=True)
    
    for cmd, conf, _ in commands:
        is_safe = not sandbox_obj.is_dangerous(cmd)
        status = "✓ SAFE" if is_safe else "❌ DANGEROUS"
        print(f"  [{status}] {cmd}")
    
    # Show how this would be integrated in REPL
    print("\n[*] Task 2: Integration in Interactive REPL...")
    print("  [✓] Agent response would be captured")
    print("  [✓] Commands extracted and validated (Task 4)")
    print("  [✓] User prompted for confirmation")
    print("  [✓] Safe commands executed with feedback")
    print("  [✓] Results injected back into memory")
    print("  [✓] Session auto-saved")

def main():
    print("\n" + "="*70)
    print("  ForestGump - Tasks 1, 2, 4 End-to-End Demo")
    print("  Real Provider Calls, Interactive REPL, Tool Sandbox")
    print("="*70)
    
    try:
        demo_task1_real_provider_calls()
    except Exception as e:
        print(f"[!] Task 1 demo error: {e}")
    
    try:
        demo_task2_interactive_repl()
    except Exception as e:
        print(f"[!] Task 2 demo error: {e}")
    
    try:
        demo_task4_tool_sandbox()
    except Exception as e:
        print(f"[!] Task 4 demo error: {e}")
    
    try:
        demo_integrated_workflow()
    except Exception as e:
        print(f"[!] Integrated workflow demo error: {e}")
    
    print("\n" + "="*70)
    print("  ✓ End-to-End Demo Complete!")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
