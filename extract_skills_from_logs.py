#!/usr/bin/env python3
"""
Batch extract skills from existing session logs.
Retroactively learns from past successful sessions.
"""

import json
import sys
from pathlib import Path
from skills import init_db, save_skill, get_all_skills

SESSIONS_DIR = Path(__file__).parent / 'sessions'


def load_provider():
    """Load the LLM provider (claude by default)."""
    try:
        from agent import ClaudeCliProvider
        return ClaudeCliProvider()
    except Exception as e:
        print(f"Warning: Could not load Claude provider: {e}")
        print("Trying Ollama...")
        try:
            from agent import OllamaProvider
            return OllamaProvider()
        except Exception as e2:
            print(f"Error: Could not load any provider: {e2}")
            return None


def extract_skills_from_session_log(session_file: Path, provider) -> list[dict]:
    """
    Read a session log and extract skills from it.
    Returns list of extracted skill dicts.
    """
    if not session_file.exists():
        return []

    try:
        with open(session_file, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"  ✗ Invalid JSON in {session_file.name}")
        return []

    messages = data.get('messages', [])
    memory = data.get('memory', {})
    session_id = data.get('timestamp', session_file.stem)
    log = data.get('log', [])

    # Skip if no messages or very short session
    if len(messages) < 3:
        return []

    # Build session summary
    summary = f"Session: {session_id}\n\n"
    summary += "Task: " + data.get('task', 'unknown') + "\n\n"
    summary += "Conversation (last 15 messages):\n"
    for msg in messages[-15:]:
        role = msg['role'].upper()[:3]
        content = msg['content'][:200]
        summary += f"{role}: {content}\n"

    if memory.get('networks') or memory.get('credentials') or memory.get('facts'):
        summary += "\nLearned state:\n"
        if memory.get('facts'):
            summary += f"Facts: {', '.join(memory['facts'][:3])}\n"
        if memory.get('networks'):
            summary += f"Networks discovered: {len(memory['networks'])}\n"
        if memory.get('credentials'):
            summary += f"Credentials found: {len(memory['credentials'])}\n"

    # Build command history
    if log:
        summary += "\nCommands executed:\n"
        for entry in log[-10:]:
            if entry.get('type') == 'exec':
                cmd = entry.get('cmd', '')[:80]
                summary += f"  {cmd}\n"

    # Ask LLM to extract skills
    extraction_prompt = f"""{summary}

Based on this security session, extract 1-5 reusable attack/defense skills as JSON.
Return ONLY valid JSON array (no markdown, no explanation):

[
  {{
    "name": "skill name (short, e.g. 'SSH with sshpass')",
    "problem": "what problem it solves",
    "solution": "how it solves it",
    "template": "shell command or code template with {{placeholders}}",
    "tags": ["tag1", "tag2", "tag3"]
  }}
]

If no reusable skills, return [].
"""

    try:
        response = provider.chat(
            [{'role': 'user', 'content': extraction_prompt}],
            system="You are a cybersecurity expert. Extract reusable attack/defense techniques from security session logs. Be specific and practical."
        )

        # Parse JSON
        import re
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            skills_data = json.loads(json_match.group(0))
            saved = []
            for skill in skills_data:
                try:
                    skill_id = save_skill(skill, source_session=session_id)
                    saved.append(skill)
                except Exception as e:
                    pass
            return saved
    except Exception as e:
        pass

    return []


def main():
    print("=" * 70)
    print("BATCH SKILL EXTRACTION FROM SESSION LOGS")
    print("=" * 70)

    init_db()
    provider = load_provider()
    if not provider:
        print("Error: No LLM provider available")
        sys.exit(1)

    # Get all session files
    session_files = sorted(SESSIONS_DIR.glob('*.json'), reverse=True)
    print(f"\nFound {len(session_files)} session files\n")

    if not session_files:
        print("No sessions to process.")
        return

    total_extracted = 0
    processed = 0

    for session_file in session_files[:20]:  # Process last 20 sessions
        try:
            print(f"Processing {session_file.name}...", end=" ")
            skills = extract_skills_from_session_log(session_file, provider)
            processed += 1
            if skills:
                for skill in skills:
                    print(f"\n  ✓ {skill.get('name', 'unnamed')}")
                    total_extracted += 1
            else:
                print("(no new skills)")
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            break
        except Exception as e:
            print(f"\n  ✗ Error: {e}")

    print("\n" + "=" * 70)
    print(f"Results: Processed {processed} sessions, extracted {total_extracted} new skills")

    all_skills = get_all_skills(999)
    print(f"Total skills in database: {len(all_skills)}")
    print("=" * 70)


if __name__ == '__main__':
    main()
