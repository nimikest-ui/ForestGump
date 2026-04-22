#!/usr/bin/env python3
"""
Fast skill extraction from session logs using pattern matching.
No LLM required - extracts successful command patterns directly.
"""

import json
import re
from pathlib import Path
from collections import Counter
from skills import init_db, save_skill, get_all_skills

SESSIONS_DIR = Path(__file__).parent / 'sessions'


def extract_command_patterns(session_file: Path) -> list[dict]:
    """
    Extract successful command patterns from a session.
    Returns list of skill-like dicts.
    """
    if not session_file.exists():
        return []

    try:
        with open(session_file, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return []

    log = data.get('log', [])
    if not log:
        return []

    skills = []
    session_id = data.get('timestamp', session_file.stem)
    task = data.get('task', 'unknown')

    # Extract successful command patterns
    for entry in log:
        if entry.get('type') != 'exec':
            continue

        cmd = entry.get('cmd', '')
        output = entry.get('output', '')[:500]

        # Skip short commands
        if len(cmd) < 10:
            continue

        # SSH patterns
        if 'ssh' in cmd.lower() or 'sshpass' in cmd.lower():
            # Extract user, host, port from command
            user_match = re.search(r'(?:sshpass|ssh).*?(?:-u|@)\s*(\w+)@([\w\.-]+)', cmd, re.IGNORECASE)
            if user_match:
                user, host = user_match.groups()
                port = re.search(r'-p\s+(\d+)', cmd)
                port_str = port.group(1) if port else '22'
                skills.append({
                    'name': f'SSH to {host}',
                    'problem': 'Need non-interactive SSH authentication',
                    'solution': 'Use sshpass or key-based auth',
                    'template': cmd.replace(user, '{user}').replace(host, '{host}').replace(port_str, '{port}'),
                    'tags': ['ssh', 'auth', 'remote-access']
                })

        # Nmap patterns
        if 'nmap' in cmd.lower():
            flags = re.findall(r'-([a-zA-Z]+)', cmd)
            if flags:
                skill_name = f'Nmap scan with {" ".join(set(flags))}'
                skills.append({
                    'name': skill_name[:50],
                    'problem': 'Reconnaissance - discover hosts and ports',
                    'solution': 'Use nmap for port scanning and service enumeration',
                    'template': cmd.replace(re.search(r'[\d\.\-/]+', cmd).group(0) if re.search(r'[\d\.\-/]+', cmd) else '', '{target}'),
                    'tags': ['recon', 'nmap', 'port-scan']
                })

        # Aircrack/WiFi patterns
        if any(x in cmd.lower() for x in ['airodump', 'aireplay', 'aircrack', 'hashcat']):
            if 'airodump' in cmd.lower():
                skills.append({
                    'name': 'WiFi Reconnaissance with airodump-ng',
                    'problem': 'Discover WiFi networks and capture handshakes',
                    'solution': 'Use airodump-ng in monitor mode with write flag',
                    'template': cmd.replace(re.search(r'wlan\d', cmd).group(0) if re.search(r'wlan\d', cmd) else '', '{interface}'),
                    'tags': ['wifi', 'recon', 'airodump', 'handshake']
                })
            elif 'aireplay' in cmd.lower():
                skills.append({
                    'name': 'WiFi Deauth Attack',
                    'problem': 'Force WiFi clients to reconnect (capture handshake)',
                    'solution': 'Use aireplay-ng deauth attack on target BSSID',
                    'template': cmd.replace(re.search(r'[A-Fa-f0-9:]{17}', cmd).group(0) if re.search(r'[A-Fa-f0-9:]{17}', cmd) else '', '{bssid}'),
                    'tags': ['wifi', 'attack', 'aireplay', 'deauth']
                })

        # Gobuster/dirb patterns
        if any(x in cmd.lower() for x in ['gobuster', 'dirb', 'ffuf']):
            tool_match = re.search(r"(gobuster|dirb|ffuf)", cmd, re.I)
            tool = tool_match.group(1).lower() if tool_match else 'web-enum'
            skills.append({
                'name': f'Web Directory Enumeration with {tool}',
                'problem': 'Discover hidden web directories and files',
                'solution': f'Use {tool} for brute force enumeration against web servers',
                'template': cmd.replace(re.search(r'https?://[\w\.\-:]+', cmd).group(0) if re.search(r'https?://[\w\.\-:]+', cmd) else '', '{url}'),
                'tags': ['web', 'recon', tool]
            })

        # curl/wget patterns
        if any(x in cmd.lower() for x in ['curl', 'wget']) and ('-X' in cmd or '--data' in cmd):
            skills.append({
                'name': 'HTTP Request Manipulation',
                'problem': 'Send custom HTTP requests (GET, POST, PUT, DELETE)',
                'solution': 'Use curl or wget with custom headers, methods, and data',
                'template': cmd[:80] + '...' if len(cmd) > 80 else cmd,
                'tags': ['http', 'web', 'api']
            })

        # find/locate patterns
        if any(x in cmd.lower() for x in ['find ', 'locate ', 'grep -r']):
            skills.append({
                'name': 'File/Content Search and Discovery',
                'problem': 'Find sensitive files or patterns across the system',
                'solution': 'Use find, locate, or grep with appropriate filters',
                'template': cmd[:60] + '...',
                'tags': ['recon', 'files', 'search']
            })

        # cat/strings patterns
        if any(x in cmd for x in ['cat /proc/', 'strings', 'objdump', 'readelf']):
            skills.append({
                'name': 'Binary/File Analysis',
                'problem': 'Extract information from binaries and system files',
                'solution': 'Use strings, objdump, readelf, or file inspection tools',
                'template': cmd[:60] + '...',
                'tags': ['binary', 'analysis', 'recon']
            })

        # SQLmap patterns
        if 'sqlmap' in cmd.lower():
            skills.append({
                'name': 'SQL Injection Testing with sqlmap',
                'problem': 'Test for and exploit SQL injection vulnerabilities',
                'solution': 'Use sqlmap to automate SQLi detection and exploitation',
                'template': cmd.replace(re.search(r'https?://[\w\.\-:/?=]+', cmd).group(0) if re.search(r'https?://[\w\.\-:/?=]+', cmd) else '', '{url}'),
                'tags': ['sql', 'injection', 'sqlmap', 'web-vuln']
            })

        # Metasploit patterns
        if 'msfconsole' in cmd.lower() or 'msfvenom' in cmd.lower():
            skills.append({
                'name': 'Metasploit Exploitation Framework',
                'problem': 'Exploit vulnerabilities with pre-built payloads',
                'solution': 'Use msfconsole or msfvenom for payload generation and delivery',
                'template': cmd[:60] + '...',
                'tags': ['exploit', 'metasploit', 'payload']
            })

        # Hashcat patterns
        if 'hashcat' in cmd.lower():
            skills.append({
                'name': 'Password Cracking with hashcat',
                'problem': 'Crack password hashes using GPU acceleration',
                'solution': 'Use hashcat with wordlist or brute-force attack mode',
                'template': cmd.replace(re.search(r'[\w/\.]+\.hashes?', cmd).group(0) if re.search(r'[\w/\.]+\.hashes?', cmd) else '', '{hash_file}'),
                'tags': ['password', 'crack', 'hashcat', 'gpu']
            })

        # John the Ripper patterns
        if 'john' in cmd.lower():
            skills.append({
                'name': 'Password Cracking with John the Ripper',
                'problem': 'Crack password hashes using dictionary/brute-force',
                'solution': 'Use john with wordlists and hash formatting',
                'template': cmd.replace(re.search(r'[\w/\.]+\.txt', cmd).group(0) if re.search(r'[\w/\.]+\.txt', cmd) else '', '{hash_file}'),
                'tags': ['password', 'crack', 'john', 'hashes']
            })

    return skills


def deduplicate_skills(skills: list[dict]) -> list[dict]:
    """Remove near-duplicate skills."""
    seen = {}
    unique = []
    for skill in skills:
        # Normalize name and problem for deduplication
        name = skill['name'].lower().strip()
        problem = skill['problem'].lower()[:40].strip()
        key = (name, problem)

        if key not in seen:
            seen[key] = True
            unique.append(skill)
    return unique


def main():
    print("=" * 70)
    print("FAST SKILL EXTRACTION FROM SESSION LOGS (Pattern Matching)")
    print("=" * 70)

    init_db()

    # Get all session files
    session_files = sorted(SESSIONS_DIR.glob('*.json'), reverse=True)
    print(f"\nProcessing {len(session_files)} session files...\n")

    total_extracted = 0
    all_skills = []

    # Get existing skill names to avoid duplicates
    existing = get_all_skills(999)
    existing_names = {s['name'].lower() for s in existing}

    for session_file in session_files[:50]:  # Process last 50 sessions
        skills = extract_command_patterns(session_file)
        if skills:
            all_skills.extend(skills)
            print(f"✓ {session_file.name}: {len(skills)} patterns")

    print(f"\nTotal patterns extracted: {len(all_skills)}")

    # Deduplicate
    unique_skills = deduplicate_skills(all_skills)
    print(f"After deduplication: {len(unique_skills)} unique skills")

    # Save to DB (skip duplicates)
    print("\nSaving skills to database...")
    for skill in unique_skills:
        skill_name = skill['name'].lower().strip()
        if skill_name not in existing_names:
            try:
                save_skill(skill, source_session='batch_extract')
                total_extracted += 1
                existing_names.add(skill_name)
            except Exception as e:
                pass

    all_db_skills = get_all_skills(999)
    print(f"\n" + "=" * 70)
    print(f"Extracted {total_extracted} new skills")
    print(f"Total skills in database: {len(all_db_skills)}")
    print("=" * 70)

    # Show sample
    if all_db_skills:
        print("\nSample skills:")
        for skill in all_db_skills[-5:]:
            print(f"  - {skill['name'][:50]}")


if __name__ == '__main__':
    main()
