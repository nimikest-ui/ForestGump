# InteractiveREPL Usage Examples and Integration Guide

## Quick Start

### 1. Starting an Interactive REPL Session

```bash
# Start with default provider
python3 -m forestgump_cli chat

# Start with specific provider
python3 -m forestgump_cli chat --provider copilot

# Start with specific model
python3 -m forestgump_cli chat --model llama-3.3-70b-versatile

# Start with query (non-interactive mode)
python3 -m forestgump_cli chat -q "what is nmap used for?"
```

### 2. REPL Command Reference

Once inside the REPL, type commands starting with `/`:

```
/help              - Show available commands
/status            - Show current session status
/model             - List available models
/exit              - Save session and exit
/sessions          - List recent sessions
/load <session-id> - Resume a previous session
/clear             - Clear conversation history
/save              - Manually save session
```

## Session Persistence Workflow

### Example 1: Creating and Resuming a Session

Session 1: Initial exploration
```
$ python3 -m forestgump_cli chat
[*] Session ID: 20260505T214215

You: what are the top kali tools for penetration testing?