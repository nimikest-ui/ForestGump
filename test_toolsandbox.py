#!/usr/bin/env python3
"""
Test suite for toolsandbox module.
Tests command parsing, execution, and safety features.
"""

import sys
import os
sys.path.insert(0, '/root/ForestGump')

from toolsandbox import CommandParser, CommandExecutor, Sandbox, CommandFilter


def test_command_parser():
    """Test command parsing with different patterns."""
    print("Testing CommandParser...")
    parser = CommandParser()
    
    # Test backticks
    response1 = "Here's a command: `nmap -p 22 192.168.1.0/24`"
    commands = parser.parse_response(response1)
    assert len(commands) == 1
    assert "nmap" in commands[0][0]
    print("  ✓ Backticks parsing")
    
    # Test XML-style
    response2 = "Run this: <cmd>ifconfig</cmd> to see networking"
    commands = parser.parse_response(response2)
    assert len(commands) == 1
    assert "ifconfig" in commands[0][0]
    print("  ✓ XML-style parsing")
    
    # Test markdown code blocks
    response3 = """Here's how:
```bash
ping -c 4 google.com
```"""
    commands = parser.parse_response(response3)
    assert len(commands) >= 1
    assert any("ping" in cmd[0] for cmd in commands)
    print("  ✓ Markdown code block parsing")
    
    # Test multiple commands
    response4 = "`hostname` and then `whoami`"
    commands = parser.parse_response(response4)
    assert len(commands) >= 2
    print("  ✓ Multiple commands parsing")


def test_command_executor():
    """Test command execution with timeout."""
    print("\nTesting CommandExecutor...")
    executor = CommandExecutor(timeout=5)
    
    # Test safe command
    result = executor.execute("echo 'Hello World'")
    assert result.exit_code == 0
    assert "Hello" in result.stdout
    print("  ✓ Safe command execution")
    
    # Test command with error
    result = executor.execute("ls /nonexistent/path")
    assert result.exit_code != 0
    print("  ✓ Error handling")
    
    # Test timeout
    result = executor.execute("sleep 10", timeout=1)
    assert result.timeout
    print("  ✓ Timeout handling")


def test_sandbox_dangerous_patterns():
    """Test dangerous pattern detection."""
    print("\nTesting Sandbox dangerous patterns...")
    sandbox = Sandbox()
    
    # Test dangerous patterns
    dangerous_commands = [
        "rm -rf /",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda",
        "airmon-ng start wlan0"
    ]
    
    for cmd in dangerous_commands:
        is_dangerous, _ = sandbox._is_dangerous(cmd)
        assert is_dangerous, f"Failed to detect dangerous: {cmd}"
    print(f"  ✓ Detected {len(dangerous_commands)} dangerous patterns")


def test_sandbox_safe_patterns():
    """Test safe pattern detection."""
    print("\nTesting Sandbox safe patterns...")
    sandbox = Sandbox()
    
    # Test safe patterns
    safe_commands = [
        "nmap -p 22 192.168.1.0/24",
        "ping -c 4 google.com",
        "netcat -l -p 8080",
        "ifconfig"
    ]
    
    for cmd in safe_commands:
        is_safe = sandbox._is_safe(cmd)
        assert is_safe, f"Failed to detect safe: {cmd}"
    print(f"  ✓ Detected {len(safe_commands)} safe patterns")


def test_command_filter():
    """Test command filtering and validation."""
    print("\nTesting CommandFilter...")
    filter_obj = CommandFilter()
    
    # Create sample commands
    commands = [
        ("nmap -p 22 192.168.1.0/24", 0.95, 0),
        ("rm -rf /", 0.90, 5),
        ("ping google.com", 0.85, 10),
    ]
    
    # Test filtering by confidence
    filtered = filter_obj.filter_commands(commands, min_confidence=0.9)
    assert len(filtered) == 2
    print("  ✓ Confidence filtering")
    
    # Test prioritization
    prioritized = filter_obj.prioritize_commands(commands)
    assert prioritized[0][1] == 0.95  # Highest confidence first
    print("  ✓ Command prioritization")
    
    # Test validation
    validation = filter_obj.validate_commands(commands)
    assert len(validation['safe']) > 0
    assert len(validation['dangerous']) > 0
    print("  ✓ Command validation")


def test_sandbox_parse_response():
    """Test sandbox response parsing."""
    print("\nTesting Sandbox.parse_response()...")
    sandbox = Sandbox()
    
    response = """
To scan the network, run:
`nmap -p 22,80,443 192.168.1.0/24`

Then check connectivity:
<cmd>ping -c 4 8.8.8.8</cmd>
"""
    
    commands = sandbox.parse_response(response)
    assert len(commands) >= 2
    print(f"  ✓ Extracted {len(commands)} commands from response")


if __name__ == "__main__":
    try:
        test_command_parser()
        test_command_executor()
        test_sandbox_dangerous_patterns()
        test_sandbox_safe_patterns()
        test_command_filter()
        test_sandbox_parse_response()
        
        print("\n" + "="*50)
        print("All tests passed! ✓")
        print("="*50)
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
