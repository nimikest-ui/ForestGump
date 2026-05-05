#!/usr/bin/env python3
"""
Integration test for tool sandbox with ForestGump CLI components.
"""

import sys
sys.path.insert(0, '/root/ForestGump')

from toolsandbox import Sandbox, CommandFilter


def test_integration():
    """Test the full tool sandbox integration flow."""
    
    print("Integration Test: Tool Sandbox with ForestGump CLI")
    print("=" * 60)
    
    # Simulate an LLM response with various command patterns
    llm_response = """
To gather information about the target network, I recommend:

1. First, scan for active hosts:
`nmap -sn 192.168.1.0/24`

2. Then perform a port scan:
<cmd>nmap -p 1-1000 192.168.1.100</cmd>

3. Check your own connectivity:
```bash
ping -c 4 8.8.8.8
```

4. For deeper enumeration, use:
`nmap -A -T4 -p 22,80,443 192.168.1.100`

5. Finally, list network interfaces:
`ifconfig`

Do NOT run: rm -rf / (this would be destructive!)
"""
    
    print("\n1. Simulated LLM Response:")
    print("-" * 60)
    print(llm_response[:300] + "...")
    
    # Initialize sandbox
    sandbox = Sandbox(timeout=30, yolo=False)
    print("\n2. Parsing commands from response...")
    
    commands = sandbox.parse_response(llm_response)
    print(f"   Found {len(commands)} command(s)")
    for i, (cmd, conf, line) in enumerate(commands, 1):
        print(f"   {i}. {cmd[:50]}... (confidence: {conf:.1%})")
    
    # Filter and prioritize
    filter_obj = CommandFilter()
    print("\n3. Filtering and prioritizing commands...")
    
    filtered = filter_obj.filter_commands(commands, min_confidence=0.8)
    print(f"   After filtering (confidence > 0.8): {len(filtered)} command(s)")
    
    prioritized = filter_obj.prioritize_commands(filtered)
    print(f"   Prioritized (highest confidence first)")
    
    # Validate commands
    print("\n4. Validating command safety...")
    validation = filter_obj.validate_commands(prioritized)
    
    print(f"   Safe commands: {len(validation['safe'])}")
    for cmd in validation['safe']:
        print(f"     ✓ {cmd['command'][:50]}...")
    
    print(f"\n   Dangerous commands: {len(validation['dangerous'])}")
    for cmd in validation['dangerous']:
        print(f"     ✗ {cmd['command'][:50]}...")
        print(f"       Reason: {cmd['reason']}")
    
    print(f"\n   Unknown commands: {len(validation['unknown'])}")
    for cmd in validation['unknown']:
        print(f"     ? {cmd['command'][:50]}... (confidence: {cmd['confidence']:.1%})")
    
    # Test dangerous pattern detection
    print("\n5. Testing dangerous pattern detection...")
    dangerous_tests = [
        ("rm -rf /", "Recursive delete"),
        ("mkfs.ext4 /dev/sda", "Format disk"),
        ("dd if=/dev/zero of=/dev/sda", "Direct disk write"),
        ("airmon-ng start wlan0", "WiFi mode change"),
    ]
    
    for cmd, desc in dangerous_tests:
        is_dangerous, reason = sandbox._is_dangerous(cmd)
        status = "✗ BLOCKED" if is_dangerous else "✓ ALLOWED"
        print(f"   {status}: {cmd} ({desc})")
    
    # Test safe command execution
    print("\n6. Testing command execution...")
    test_cmd = "echo 'ForestGump Tool Sandbox Active'"
    result = sandbox.executor.execute(test_cmd)
    if result.exit_code == 0:
        print(f"   ✓ Executed: {test_cmd}")
        print(f"   Output: {result.stdout.strip()}")
    else:
        print(f"   ✗ Failed to execute: {test_cmd}")
    
    print("\n" + "=" * 60)
    print("Integration test completed successfully! ✓")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_integration()
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
