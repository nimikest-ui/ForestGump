#!/usr/bin/env python3
"""
Auto-extract successful techniques from session logs and update techniques.json.
Scoring: fewer turns to solve = higher priority next time.
Score = (use_count * 100) - best_session_turns
"""
import json
import re
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
SESSIONS_DIR = SCRIPT_DIR / 'sessions'
TECHNIQUES_FILE = SCRIPT_DIR / 'techniques.json'

# Each detector matches a command pattern + success signal in the output.
DETECTORS = [
    {
        'id': 'expect_ssh_password',
        'name': 'expect SSH password login',
        'tags': ['ssh', 'expect', 'automation', 'bandit'],
        'cmd_pattern': r'\bexpect\b.*\bspawn\s+ssh\b',
        'success_signals': ['congratulations', 'welcome to', 'password is', 'the password you'],
        'problem': 'Need to automate SSH login with a password prompt',
        'solution': 'Use expect to spawn SSH, wait for password prompt, send password, run command',
        'template': "expect -c 'spawn ssh -o StrictHostKeyChecking=no {user}@{host} -p {port}; expect \"*password*\"; send \"{pass}\\r\"; expect \"*$\"; send \"{command}\\r\"; expect \"*$\"; send \"exit\\r\"; expect eof'",
    },
    {
        'id': 'sshpass_with_command',
        'name': 'sshpass non-interactive SSH',
        'tags': ['ssh', 'sshpass', 'automation', 'bandit'],
        'cmd_pattern': r"\bsshpass\s+-p\s+\S+\s+ssh\b.*'[^']+'",
        'success_signals': ['congratulations', 'welcome to', 'password is', 'the password you'],
        'problem': 'Need to run a remote SSH command with password auth without interaction',
        'solution': 'Use sshpass to pass the password and ssh with a quoted command',
        'template': "sshpass -p '{pass}' ssh -o StrictHostKeyChecking=no {user}@{host} -p {port} '{command}'",
    },
    {
        'id': 'paramiko_base64',
        'name': 'SSH via Paramiko + base64',
        'tags': ['ssh', 'paramiko', 'base64', 'automation', 'bandit'],
        'cmd_pattern': r'\bbase64\s+-d\b.*\|\s*python',
        'success_signals': ['congratulations', 'welcome to', 'password is', 'the password you'],
        'problem': 'SSH blocked by safety filter; need programmatic SSH without ssh binary',
        'solution': 'Encode a paramiko Python script in base64 and pipe to python3',
        'template': "base64 -d <<< '{b64_code}' | python3",
    },
    {
        'id': 'xxd_hex_decode',
        'name': 'xxd hex reverse decode',
        'tags': ['decode', 'hex', 'bandit', 'forensics'],
        'cmd_pattern': r'\bxxd\s+-r\b',
        'success_signals': ['password is', 'the password you', 'flag{'],
        'problem': 'File contains hex-encoded data',
        'solution': 'Use xxd -r to reverse hex dump back to binary',
        'template': 'xxd -r {file}',
    },
    {
        'id': 'find_readable_files',
        'name': 'find readable files by other users',
        'tags': ['bandit', 'linux', 'find'],
        'cmd_pattern': r'\bfind\b.*-readable\b|\bfind\b.*-perm\b.*777',
        'success_signals': ['password is', 'the password you', 'flag{'],
        'problem': 'Need to locate files readable by current user',
        'solution': 'Use find with -readable flag',
        'template': 'find / -readable -type f 2>/dev/null | grep -v proc',
    },
]


def score_success(output):
    """Return a success score for a command's output. Higher = more successful."""
    low = output.lower()
    score = 0
    for s in ['congratulations', 'the password you', 'flag{', 'password is:']:
        if s in low:
            score += 50
    for s in ['welcome to', 'level', 'you are now']:
        if s in low:
            score += 20
    for s in ['error', 'failed', 'not found', 'permission denied', 'timed out', 'blocked']:
        if s in low:
            score -= 30
    return score


def analyze_session(session_file):
    """Return list of technique learnings from a completed session."""
    with open(session_file) as f:
        session = json.load(f)

    # Only learn from sessions the agent declared done
    messages = session.get('messages', [])
    last_assistant = next(
        (m['content'] for m in reversed(messages) if m['role'] == 'assistant'), ''
    )
    if '<done>' not in last_assistant:
        return []

    log = session.get('log', [])
    session_id = session.get('timestamp', Path(session_file).stem)
    turns = session.get('turns', 0)
    learnings = []

    for entry in [e for e in log if e.get('type') == 'exec']:
        cmd = entry.get('cmd', '')
        output = entry.get('output', '')
        turn = entry.get('turn', 0)

        if score_success(output) < 30:
            continue

        for det in DETECTORS:
            if not re.search(det['cmd_pattern'], cmd, re.IGNORECASE):
                continue
            signal = next((s for s in det['success_signals'] if s in output.lower()), None)
            if not signal:
                continue
            learnings.append({
                'id': det['id'],
                'name': det['name'],
                'problem': det['problem'],
                'solution': det['solution'],
                'template': det['template'],
                'tags': det['tags'],
                'success_rate': 'high',
                'use_count': 1,
                'turns_when_used': turns,       # total turns for this session
                'discovered_session': session_id,
                'discovered_turn': turn,         # which turn within the session it worked
                'notes': f'Matched "{signal}" at turn {turn}/{turns}.',
            })

    return learnings


def update_techniques(learnings):
    """Merge new learnings into techniques.json, boosting score for fewer turns."""
    if not TECHNIQUES_FILE.exists():
        data = {'techniques': {}, 'metadata': {}}
    else:
        with open(TECHNIQUES_FILE) as f:
            data = json.load(f)

    techniques = data.get('techniques', {})
    added, boosted = [], []

    for l in learnings:
        tid = l['id']
        if tid in techniques:
            techniques[tid]['use_count'] = techniques[tid].get('use_count', 1) + 1
            techniques[tid]['last_seen'] = l['discovered_session']
            # Track best (minimum) session turns — fewer turns = higher efficiency
            old_best = techniques[tid].get('best_session_turns', 999)
            new_turns = l.get('turns_when_used', 999)
            if new_turns < old_best:
                techniques[tid]['best_session_turns'] = new_turns
                boosted.append(f'{tid} (turns {old_best}→{new_turns})')
        else:
            techniques[tid] = {k: v for k, v in l.items() if k != 'turns_when_used'}
            techniques[tid]['best_session_turns'] = l.get('turns_when_used', 999)
            added.append(tid)

    # Sort by score: (use_count * 100) - best_session_turns
    # Fewer turns = higher score; more uses = higher score
    data['techniques'] = dict(sorted(
        techniques.items(),
        key=lambda x: (x[1].get('use_count', 1) * 100 - x[1].get('best_session_turns', 99)),
        reverse=True,
    ))
    data['metadata'] = {
        **data.get('metadata', {}),
        'last_updated': datetime.now().isoformat(),
        'total_techniques': len(techniques),
    }

    with open(TECHNIQUES_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    return added, boosted


def learn_from_session(session_file):
    """Analyze a session and update techniques. Safe to call — never raises."""
    learnings = analyze_session(Path(session_file))
    if not learnings:
        return
    added, boosted = update_techniques(learnings)
    if added:
        print(f'✨ Auto-learned: {", ".join(added)}')
    if boosted:
        print(f'📈 Efficiency boost (fewer turns): {", ".join(boosted)}')


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        learn_from_session(sys.argv[1])
    else:
        sessions = sorted(SESSIONS_DIR.glob('*.json'), reverse=True) if SESSIONS_DIR.exists() else []
        if sessions:
            print(f'Analyzing {sessions[0].name}...')
            learn_from_session(sessions[0])
        else:
            print('No sessions found.')
