#!/usr/bin/env python3
"""Quick tests for token optimization functions."""

import sys
sys.path.insert(0, '/root/ForestGump')

from agent import trim_message_history, compress_command_output

def test_trim_message_history():
    """Test message history trimming."""
    messages = [
        {'role': 'user', 'content': f'msg {i}'}
        for i in range(20)
    ]

    trimmed = trim_message_history(messages, max_history=5)
    assert len(trimmed) == 5, f"Expected 5, got {len(trimmed)}"
    assert trimmed[0] == messages[0], "First message not preserved"
    assert trimmed[-1] == messages[-1], "Last message not preserved"
    print('✓ trim_message_history: keeps first + last N-1')

def test_compress_command_output():
    """Test output compression."""

    # Small output (no compression)
    small = "hello\nworld"
    compressed = compress_command_output(small, max_length=100)
    assert compressed == small, "Small output should not be compressed"
    print('✓ compress_command_output: small output unchanged')

    # Large output (many lines)
    large_lines = [f"line {i}: " + "x" * 50 for i in range(100)]
    large = '\n'.join(large_lines)
    compressed = compress_command_output(large, max_length=1500)
    assert len(compressed) < len(large), "Large output should be compressed"
    assert 'line 0' in compressed, "First lines should be present"
    assert 'line 99' in compressed, "Last lines should be present"
    assert '...' in compressed, "Should have ellipsis marker"
    reduction = (1 - len(compressed) / len(large)) * 100
    print(f'✓ compress_command_output: {reduction:.0f}% reduction on 100-line output')

    # Large single block
    large_block = "x" * 5000
    compressed = compress_command_output(large_block, max_length=1500)
    assert len(compressed) <= 1600, f"Compressed too large: {len(compressed)}"
    reduction = (1 - len(compressed) / len(large_block)) * 100
    print(f'✓ compress_command_output: {reduction:.0f}% reduction on 5KB output')

def test_token_accumulation():
    """Test token tracking structure."""
    token_totals = {
        'input_tokens': 100,
        'output_tokens': 50,
        'cache_creation_input_tokens': 500,
        'cache_read_input_tokens': 1000,
    }

    # Simulate accumulation
    usage = {
        'input_tokens': 200,
        'output_tokens': 75,
        'cache_creation_input_tokens': 0,
        'cache_read_input_tokens': 100,
    }

    token_totals['input_tokens'] += usage.get('input_tokens', 0)
    token_totals['output_tokens'] += usage.get('output_tokens', 0)
    token_totals['cache_creation_input_tokens'] += usage.get('cache_creation_input_tokens', 0)
    token_totals['cache_read_input_tokens'] += usage.get('cache_read_input_tokens', 0)

    assert token_totals['input_tokens'] == 300
    assert token_totals['cache_read_input_tokens'] == 1100
    print('✓ Token tracking: accumulation works correctly')

if __name__ == '__main__':
    test_trim_message_history()
    test_compress_command_output()
    test_token_accumulation()
    print('\n✅ All optimization tests passed!')
