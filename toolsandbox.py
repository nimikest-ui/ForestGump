"""
Tool Sandbox - Command parsing, validation, and subprocess execution with safety safeguards.
Implements command extraction from response text and secure execution with timeout protection.
"""

import os
import re
import subprocess
import signal
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass


@dataclass
class CommandResult:
    """Result of command execution."""
    exit_code: int
    stdout: str
    stderr: str
    timeout: bool = False
    error: bool = False
    error_msg: str = ""


class CommandParser:
    """Extract commands from response text with multiple pattern support."""
    
    # Patterns to extract commands
    PATTERNS = [
        # Backticks: `command here`
        r'`([^`\n]+)`',
        # XML-style: <cmd>command here</cmd>
        r'<cmd>([^<\n]+)</cmd>',
        # Markdown code blocks: ```bash command here ``` (multiline)
        r'```(?:bash|shell|sh)?\n(.*?)\n```',
    ]
    
    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.MULTILINE | re.DOTALL) for p in self.PATTERNS]
    
    def parse_response(self, response_text: str) -> List[Tuple[str, float, int]]:
        """
        Extract commands from response text.
        
        Args:
            response_text: LLM response containing potential commands
            
        Returns:
            List of (command, confidence, source_line) tuples
        """
        commands = []
        seen = set()
        
        lines = response_text.split('\n')
        
        # Use full text for patterns that might span multiple lines
        for pattern_idx, pattern in enumerate(self.compiled_patterns):
            matches = pattern.finditer(response_text)
            for match in matches:
                raw_cmd = match.group(1).strip()
                
                # Skip empty or whitespace-only
                if not raw_cmd or raw_cmd.isspace():
                    continue
                
                # Normalize: remove extra whitespace, handle multiline
                cmd = ' '.join(raw_cmd.split())
                
                # Skip duplicates
                if cmd in seen:
                    continue
                seen.add(cmd)
                
                # Find line number (approximate)
                line_num = response_text[:match.start()].count('\n')
                
                # Calculate confidence (backticks and XML-style are high confidence)
                if pattern_idx == 0:  # Backticks
                    confidence = 0.95
                elif pattern_idx == 1:  # XML
                    confidence = 0.90
                else:  # Markdown blocks
                    confidence = 0.85
                
                commands.append((cmd, confidence, line_num))
        
        return commands


class CommandExecutor:
    """Execute commands safely with subprocess and timeout protection."""
    
    DEFAULT_TIMEOUT = 30
    
    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """Initialize executor with default timeout."""
        self.timeout = timeout
    
    def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None
    ) -> CommandResult:
        """
        Execute a command in subprocess with timeout protection.
        
        Args:
            command: Command string to execute
            timeout: Timeout in seconds (uses default if None)
            cwd: Working directory for command
            
        Returns:
            CommandResult with exit code, stdout, stderr
        """
        timeout = timeout or self.timeout
        
        try:
            # Execute with timeout
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # Strip ANSI codes from output
            stdout = self._strip_ansi(result.stdout)
            stderr = self._strip_ansi(result.stderr)
            
            return CommandResult(
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
                timeout=False,
                error=result.returncode != 0
            )
        
        except subprocess.TimeoutExpired:
            # Kill the process and return timeout error
            return CommandResult(
                exit_code=124,  # Standard timeout exit code
                stdout="",
                stderr=f"Command timeout after {timeout}s",
                timeout=True,
                error=True
            )
        
        except FileNotFoundError:
            return CommandResult(
                exit_code=127,
                stdout="",
                stderr="Command not found",
                error=True,
                error_msg="Command not found"
            )
        
        except Exception as e:
            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                error=True,
                error_msg=str(e)
            )
    
    def _strip_ansi(self, text: str) -> str:
        """Remove ANSI escape sequences from text."""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)


class Sandbox:
    """Main orchestrator for safe command parsing, validation, and execution."""
    
    # Commands that are too dangerous to allow
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf',           # Recursive force delete
        r'mkfs',               # Format filesystem
        r'\bdd\b',             # Direct disk writes
        r':(){ *\| *:',        # Fork bomb
        r'airmon-ng',          # WiFi mode changes
        r'systemctl.*kill',    # Kill services
        r'reboot|shutdown',    # System restart/halt
        r'chmod\s+777',        # Dangerous permissions
        r'chown\s+root',       # Change ownership to root
        r'>\s*/dev/sd',        # Raw device write
        r'iptables.*-F',       # Flush firewall
    ]
    
    # Commands we trust are safe
    SAFE_PATTERNS = [
        r'nmap',
        r'netcat|nc\b',
        r'ifconfig|ip\s+addr',
        r'ping\b',
        r'hostname',
        r'whoami',
        r'pwd',
        r'ls\b',
        r'cat\b',
        r'echo\b',
        r'grep\b',
        r'find\b',
        r'netstat',
        r'ss\b',
        r'dig\b',
        r'nslookup',
        r'curl\b',
        r'wget\b',
        r'file\b',
        r'head\b|tail\b',
        r'wc\b',
        r'sort\b',
        r'uniq\b',
        r'cut\b',
        r'awk\b',
        r'sed\b',
    ]
    
    def __init__(self, timeout: int = 30, yolo: bool = False):
        """
        Initialize sandbox.
        
        Args:
            timeout: Command timeout in seconds
            yolo: If True, skip user confirmations (dangerous!)
        """
        self.parser = CommandParser()
        self.executor = CommandExecutor(timeout=timeout)
        self.timeout = timeout
        self.yolo = yolo
        
        self.compiled_dangerous = [
            re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PATTERNS
        ]
        self.compiled_safe = [
            re.compile(p, re.IGNORECASE) for p in self.SAFE_PATTERNS
        ]
    
    def parse_response(self, response_text: str) -> List[Tuple[str, float, int]]:
        """
        Extract commands from response text.
        
        Args:
            response_text: LLM response text
            
        Returns:
            List of (command, confidence, source_line) tuples
        """
        return self.parser.parse_response(response_text)
    
    def _is_dangerous(self, command: str) -> Tuple[bool, str]:
        """
        Check if command matches dangerous patterns.
        
        Returns:
            (is_dangerous, reason) tuple
        """
        for pattern in self.compiled_dangerous:
            if pattern.search(command):
                return True, f"Matches dangerous pattern: {pattern.pattern}"
        
        return False, ""
    
    def _is_safe(self, command: str) -> bool:
        """Check if command is in trusted whitelist."""
        for pattern in self.compiled_safe:
            if pattern.search(command):
                return True
        return False
    
    def confirm_execution(self, command: str) -> bool:
        """
        Ask user to confirm command execution.
        
        Returns:
            True if user confirms, False otherwise
        """
        if self.yolo:
            return True
        
        print(f"\n>>> Command: {command}")
        response = input("Execute? [y/n]: ").strip().lower()
        return response in ('y', 'yes')
    
    def execute_with_safeguards(self, command: str, cwd: Optional[str] = None) -> Tuple[bool, str]:
        """
        Execute command with safety checks.
        
        Args:
            command: Command to execute
            cwd: Working directory
            
        Returns:
            (success, output) tuple
        """
        # Check for dangerous patterns
        is_dangerous, reason = self._is_dangerous(command)
        if is_dangerous:
            return False, f"BLOCKED: {reason}"
        
        # Show command and ask confirmation
        print(f"\n>>> Command: {command}")
        if not self.confirm_execution(command):
            return False, "Execution cancelled by user"
        
        # Execute
        result = self.executor.execute(command, timeout=self.timeout, cwd=cwd)
        
        if result.timeout:
            return False, f"Timeout after {self.timeout}s: {result.stderr}"
        
        if result.error and result.error_msg:
            return False, f"Error: {result.error_msg}"
        
        # Combine output
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr] {result.stderr}"
        
        success = result.exit_code == 0
        return success, output
    
    def execute_and_feedback(self, command: str, cwd: Optional[str] = None) -> Tuple[bool, str]:
        """
        Execute command and return feedback for conversation context.
        
        Args:
            command: Command to execute
            cwd: Working directory
            
        Returns:
            (success, formatted_output) tuple
        """
        success, output = self.execute_with_safeguards(command, cwd=cwd)
        
        if success:
            feedback = f"Command executed successfully:\n{output}"
        else:
            feedback = f"Command failed or was blocked:\n{output}"
        
        return success, feedback


class CommandFilter:
    """Filter and prioritize commands for execution."""
    
    def __init__(self):
        self.sandbox = Sandbox()
    
    def filter_commands(
        self,
        commands: List[Tuple[str, float, int]],
        min_confidence: float = 0.8
    ) -> List[Tuple[str, float, int]]:
        """
        Filter commands by confidence threshold.
        
        Args:
            commands: List of (command, confidence, line) tuples
            min_confidence: Minimum confidence score (0-1)
            
        Returns:
            Filtered list of commands
        """
        return [
            (cmd, conf, line)
            for cmd, conf, line in commands
            if conf >= min_confidence
        ]
    
    def prioritize_commands(
        self,
        commands: List[Tuple[str, float, int]]
    ) -> List[Tuple[str, float, int]]:
        """
        Sort commands by confidence (highest first).
        
        Args:
            commands: List of (command, confidence, line) tuples
            
        Returns:
            Sorted list (descending by confidence)
        """
        return sorted(commands, key=lambda x: x[1], reverse=True)
    
    def validate_commands(
        self,
        commands: List[Tuple[str, float, int]]
    ) -> Dict[str, List]:
        """
        Validate all commands and categorize.
        
        Args:
            commands: List of (command, confidence, line) tuples
            
        Returns:
            Dict with 'safe', 'dangerous', 'unknown' keys
        """
        result = {
            'safe': [],
            'dangerous': [],
            'unknown': []
        }
        
        for cmd, conf, line in commands:
            is_dangerous, reason = self.sandbox._is_dangerous(cmd)
            
            if is_dangerous:
                result['dangerous'].append({
                    'command': cmd,
                    'confidence': conf,
                    'line': line,
                    'reason': reason
                })
            elif self.sandbox._is_safe(cmd):
                result['safe'].append({
                    'command': cmd,
                    'confidence': conf,
                    'line': line
                })
            else:
                result['unknown'].append({
                    'command': cmd,
                    'confidence': conf,
                    'line': line
                })
        
        return result
