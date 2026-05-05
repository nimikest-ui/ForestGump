Tool Sandbox Implementation
===========================

Overview
--------
The tool sandbox module (toolsandbox.py) provides comprehensive command parsing, validation,
and secure subprocess execution for ForestGump. It extracts commands from LLM responses and
executes them with safety safeguards, timeout protection, and user confirmations.

Components
----------

1. CommandParser
   - Extracts commands from response text using multiple patterns
   - Pattern support:
     * Backticks: `nmap -p 22 192.168.1.0/24`
     * XML-style: <cmd>nmap -p 22 192.168.1.0/24</cmd>
     * Markdown blocks: ```bash nmap -p 22 192.168.1.0/24 ```
   - Returns: List of (command, confidence_score, line_number) tuples
   - Confidence scores:
     * Backticks: 0.95 (highest)
     * XML-style: 0.90
     * Markdown blocks: 0.85 (lowest)

2. CommandExecutor
   - Executes commands safely using subprocess.run()
   - Features:
     * Timeout protection (default 30 seconds per command)
     * ANSI code stripping from output
     * SIGTERM-based timeout handling
     * Stderr/stdout capture and separation
     * Environment variable substitution support
   - Returns: CommandResult with exit_code, stdout, stderr, timeout status
   - Exit codes:
     * 0: Success
     * 124: Timeout
     * 127: Command not found
     * Other: Command-specific error codes

3. Sandbox (Main Orchestrator)
   - Central safety and execution controller
   - Command validation:
     * Blocks dangerous patterns (rm -rf, mkfs, dd, airmon-ng, etc.)
     * Whitelists safe commands (nmap, netcat, ifconfig, ping, etc.)
     * Requires user confirmation for unknown commands
   - Methods:
     * parse_response(response_text) -> List of commands
     * execute_with_safeguards(command, cwd) -> (success, output)
     * execute_and_feedback(command, cwd) -> (success, feedback)
     * confirm_execution(command) -> bool
     * _is_dangerous(command) -> (bool, reason)
     * _is_safe(command) -> bool

4. CommandFilter
   - Filters and prioritizes commands for execution
   - Features:
     * Filter by confidence threshold
     * Sort by confidence (highest first)
     * Validate and categorize commands
   - Methods:
     * filter_commands(commands, min_confidence=0.8)
     * prioritize_commands(commands)
     * validate_commands(commands) -> dict with safe/dangerous/unknown

Safety Features
---------------

Dangerous Pattern Blocklist:
  - rm -rf          : Recursive force delete
  - mkfs            : Filesystem formatting
  - dd              : Direct disk writes
  - :(){ | :        : Fork bomb
  - airmon-ng       : WiFi mode changes
  - systemctl kill  : Service termination
  - reboot/shutdown : System restart
  - chmod 777       : Dangerous permissions
  - chown root      : Root ownership changes
  - /dev/sd* writes : Raw device writes
  - iptables -F     : Firewall flush

Trusted Safe Commands (Whitelist):
  - nmap, netcat, nc
  - ifconfig, ip addr
  - ping, hostname, whoami, pwd
  - ls, cat, echo, grep, find
  - netstat, ss, dig, nslookup
  - curl, wget
  - head, tail, wc, sort, uniq
  - cut, awk, sed

User Confirmation:
  - All dangerous commands are blocked
  - Unknown (non-whitelisted) commands require user y/n confirmation
  - Safe commands may execute automatically
  - YOLO mode (--yolo flag) bypasses confirmations (dangerous!)

Integration with ForestGump CLI
-------------------------------

In InteractiveREPL:
  1. Provider returns response text
  2. extract_and_handle_commands() is called
  3. Sandbox parses response for commands
  4. CommandFilter validates each command
  5. Safe commands execute automatically
  6. Dangerous commands are blocked with reason
  7. Unknown commands ask user for confirmation
  8. Output is captured and fed back to conversation

Usage in Chat Loop:
```python
repl = InteractiveREPL(
    provider=provider,
    model=model,
    provider_name="groq",
    yolo=False  # Set to True to skip confirmations (dangerous!)
)
repl.run()
```

Command Execution Flow:
```
Response from LLM
  ↓
extract_and_handle_commands()
  ↓
parse_response() → [commands with confidence]
  ↓
filter_commands() → [high-confidence only]
  ↓
prioritize_commands() → [sorted by confidence]
  ↓
validate_commands() → {safe, dangerous, unknown}
  ↓
For each command:
  - DANGEROUS: Block with reason, show user
  - SAFE: Execute automatically
  - UNKNOWN: Show to user, ask confirmation
  ↓
execute_with_safeguards()
  ↓
Display results to user
```

Testing
-------

Test suite: test_toolsandbox.py
Tests cover:
  - Command parsing (backticks, XML, markdown)
  - Multiple command extraction
  - Safe command execution
  - Error handling
  - Timeout behavior (1-second limit)
  - Dangerous pattern detection
  - Safe pattern detection
  - Command filtering by confidence
  - Command prioritization
  - Command validation and categorization

Run tests:
```bash
python3 test_toolsandbox.py
```

Example Usage
-------------

1. Basic parsing:
```python
from toolsandbox import Sandbox

sandbox = Sandbox()
response = "Scan with: `nmap -p 22 192.168.1.0/24`"
commands = sandbox.parse_response(response)
# Returns: [("nmap -p 22 192.168.1.0/24", 0.95, 0)]
```

2. Execute with safeguards:
```python
success, output = sandbox.execute_with_safeguards(
    "nmap -p 22 192.168.1.0/24"
)
if success:
    print(f"Output: {output}")
else:
    print(f"Failed: {output}")
```

3. Full filtering and validation:
```python
from toolsandbox import CommandFilter

filter_obj = CommandFilter()
commands = sandbox.parse_response(response)
validated = filter_obj.validate_commands(commands)

print(f"Safe: {validated['safe']}")
print(f"Dangerous: {validated['dangerous']}")
print(f"Unknown: {validated['unknown']}")
```

Configuration
-------------

Timeout (per command):
  - Default: 30 seconds
  - Configurable in Sandbox.__init__(timeout=...)
  - Enforced with subprocess timeout

YOLO Mode:
  - Sandbox(yolo=True) skips all confirmations
  - Dangerous only: still blocks dangerous patterns
  - Not recommended for untrusted agent responses

Environment:
  - Respects current working directory
  - Inherits parent environment
  - Can specify cwd in execute() methods

Limitations & Future Work
--------------------------

Current Limitations:
  1. Command patterns are regex-based (no full parsing)
  2. Whitelist is static (not extensible via config yet)
  3. No command history persistence
  4. No output logging
  5. Single-threaded execution only

Future Enhancements:
  1. Configurable blocklist/whitelist files
  2. Command output logging and replay
  3. Concurrent command execution
  4. Custom pattern plugins
  5. Interactive command editor before execution
  6. Command result persistence in session file

Performance
-----------

Parsing: O(n) where n = response text length
  - Uses compiled regex patterns
  - Single pass through text

Validation: O(k*m) where k = commands, m = patterns
  - Each command checked against all patterns
  - Typically fast for <10 commands

Execution: ~30ms per command (excluding actual command runtime)
  - Subprocess overhead
  - ANSI stripping
  - Result capture

Memory: ~1MB per 1000 commands in history
  - Minimal overhead
  - Scales linearly

See Also
--------
- forestgump_cli.py: CLI integration
- InteractiveREPL.extract_and_handle_commands(): Entry point
- test_toolsandbox.py: Comprehensive test suite
- IMPLEMENTATION_SUMMARY.md: Overall architecture
