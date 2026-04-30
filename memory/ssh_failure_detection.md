---
name: SSH failure detection improvements
description: Fixed issue where sshpass remote command failures were falsely attributed to sshpass tool
type: feedback
---

## Problem

When running `sshpass -p 'pwd' ssh host 'cat nonexistent_file'`, the agent would detect the remote `cat` command failure and incorrectly mark **sshpass** as the failed tool. This caused false loop-detection after 3 consecutive attempts at different remote commands.

Example from session 20260430_112144:
- Turn 5-7: Tried 3 different ways to access a file (`"spaces in this filename"`, escaped version, wildcard)
- All 3 failed with "No such file or directory" (remote cat failed, not SSH)
- Agent blamed sshpass and stopped using it
- Turn 14: `cat ~/*` worked, proving sshpass itself was never broken

## Solution

**Updated command_base()** — Now strips away sshpass and -p arguments so the base command is `ssh`, not `sshpass`.

**Added is_ssh_connection_failure()** — Detects SSH-level errors:
- "Permission denied (publickey,password)" → SSH auth failed
- "Connection refused", "Could not resolve hostname" → Network/host issue
- "Host key verification failed" → SSH trust issue

**Added has_remote_output()** — Detects evidence that SSH succeeded:
- "No such file", "command not found" → remote command output
- Substantial output (>2 lines) → likely from remote system

**Updated is_command_failure()** — For SSH/sshpass commands:
```
if cmd_base in ('ssh', 'sshpass'):
    if is_ssh_connection_failure(output):
        return True  # SSH auth/connection failed → true tool failure
    if has_remote_output(output):
        return False  # SSH OK, remote output present → not an SSH failure
    return False  # Assume success if no connection error
```

## Why it works on any SSH server

- **Not hardcoded to OverTheWire** — Uses generic SSH error messages that all SSH servers return
- **Generic auth errors** — Checks for "Permission denied (publickey" or "Permission denied (password" patterns
- **Remote command detection** — Looks for ANY remote output indicators, not server-specific banners
- **Distinction principle** — SSH layer errors ≠ remote command layer errors

## When to use / How to apply

This fix applies automatically to all SSH/sshpass commands. The agent now correctly:
- Retries SSH if the connection/auth fails (legitimate tool failure)
- Suggests alternative syntax/approach if the remote command fails (not the SSH tool's fault)
- Doesn't loop-detect on repeated SSH attempts with different remote commands
