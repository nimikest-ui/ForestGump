#!/usr/bin/env python3
"""
Test skill extraction from a mock session.
Demonstrates how skills are learned and stored from successful runs.
"""

import json
from pathlib import Path
from skills import init_db, save_skill, search_skills, get_all_skills, skills_context

def test_skill_creation():
    """Create a test skill and verify it can be retrieved."""
    init_db()

    # Create a sample skill
    test_skill = {
        'name': 'WPA2 Handshake Capture',
        'problem': 'Need to capture WPA2 4-way handshake for cracking',
        'solution': 'Use airodump-ng to monitor network, then aireplay-ng to deauth and trigger handshake',
        'template': 'sudo airodump-ng -w capture -c {channel} --bssid {bssid} {interface} & sleep {duration} && sudo aireplay-ng -0 5 -a {bssid} {interface}',
        'tags': ['wifi', 'wpa2', 'handshake', 'aircrack']
    }

    skill_id = save_skill(test_skill, source_session='test_20260422_150000')
    print(f"✓ Created skill ID: {skill_id}")

    # Search for it
    results = search_skills('WPA2 handshake', limit=5)
    print(f"✓ Found {len(results)} results for 'WPA2 handshake'")
    for r in results:
        print(f"  - {r['name']}")

    # Get all
    all_skills = get_all_skills(limit=10)
    print(f"✓ Total skills in database: {len(all_skills)}")

    # Generate context
    context = skills_context('wifi cracking', limit=3)
    print(f"\n✓ Generated skill context:\n{context}")

if __name__ == '__main__':
    test_skill_creation()
