# Plan: ForestGump menu.py TUI — Complete Fix & Polish

**Date:** 2026-05-06  
**Status:** Planning  
**Scope:** Fix the full TUI experience in `/root/ForestGump/menu.py`

---

## Goal

Make `menu.py` behave like Hermes in a real interactive terminal:

1. **Scroll region** — output fills the top portion of the terminal
2. **Fixed input bar** — prompt stays locked at the bottom
3. **Typed input appears in real-time** as the user types
4. **Enter executes** the task or slash command
5. **Slash commands** (`/provider`, `/model`, `/resume`) open arrow-key menus
6. **Agent output streams** into the scroll region as it runs
7. **Fallback mode** remains fully functional for non-TTY environments

---

## Current Context

### Already Fixed (this session)
- `getch_unix()` now checks `os.isatty()` before calling termios — no more ioctl crash
- `\\033` escape bug on line 751 fixed — scroll region ANSI code now sent correctly
- Slash commands `/provider` and `/model` render and accept input in fallback mode
- `RealtimeCapture` class for streaming agent output into scroll buffer

### Remaining Issues

#### 1. `redisplay_screen()` — function defined but not shown yet
- Need to verify it correctly clears the scroll region and redraws output + input bar
- Suspect: cursor positioning may be off (uses `\033[{rows};{col}H` to place cursor)

#### 2. Arrow key handling in `_run_with_fixed_input()`
- Reads one char at a time (non-blocking with `O_NONBLOCK`)
- Arrow keys are 3-char sequences: `\x1b`, `[`, then `A`/`B`/`C`/`D`
- Current code on line 981 checks for `key == '\\x1b[A'` — but chars arrive one at a time, not concatenated
- **This is a bug**: up/down arrow history navigation won't work

#### 3. `show_menu()` inside TUI mode
- When `/provider` is typed in TUI mode, `show_menu()` is called
- `show_menu()` calls `getch_unix()` which now handles non-TTY correctly
- But inside TUI mode, `fd` is set to `setcbreak` — need to restore/re-set around `show_menu()` call
- Otherwise menu input may misbehave

#### 4. Status bar display
- Status bar shows fake token/progress data (lines 799–812)
- Should show real data from agent execution (turns, provider, model, actual elapsed time)

#### 5. ANSI scroll region restoration on exit
- `finally` block on line 1099 restores scroll region — looks correct
- But if exception happens mid-TUI, terminal state may be left dirty

---

## Proposed Approach

Fix in three stages, smallest risk first.

### Stage 1 — Fix Arrow Key Parsing (High Impact, Low Risk)

The non-blocking read loop reads one character at a time. Arrow key sequences (`\x1b[A`) must be assembled across multiple reads.

**Solution:** When `\x1b` is read, immediately do two more blocking reads (with a short timeout) to collect the full escape sequence before dispatching to `handle_input_key()`.

```python
# In the main input loop, replace:
char = sys.stdin.read(1)
if char:
    handle_input_key(char)

# With:
char = sys.stdin.read(1)
if char == '\x1b':
    # Try to read the rest of the escape sequence (non-blocking, short timeout)
    rest = ''
    for _ in range(2):
        try:
            rest += sys.stdin.read(1)
        except (IOError, BlockingIOError):
            break
    char = '\x1b' + rest
if char:
    handle_input_key(char)
```

**Files changed:** `menu.py` lines ~1075–1085

### Stage 2 — Fix `redisplay_screen()` Cursor Positioning

Audit the `redisplay_screen()` function (around line 830–863):
- Verify it moves cursor to the scroll region start (`\033[1;1H`) before drawing output
- Verify it draws status bar at `rows-1` and input prompt at `rows`
- Verify it moves cursor back to end of current input after drawing

If cursor positioning is wrong, `redisplay_screen()` will overwrite random lines.

**Files changed:** `menu.py` lines ~830–863

### Stage 3 — Fix `show_menu()` Inside TUI Mode

When `/provider` or `/model` is typed in TUI mode:
1. Restore terminal to normal (`tcsetattr` old settings) before calling `show_menu()`
2. Call `show_menu()` (arrow key menu works correctly)
3. Return to `setcbreak` mode for the input loop

This requires passing `old_settings` into `handle_input_key()` or using a context manager.

**Files changed:** `menu.py` lines ~886–905, ~1062–1068

---

## Step-by-Step Plan

1. **Read `redisplay_screen()` in full** (lines 820–865) — understand current cursor logic
2. **Fix arrow key escape sequence assembly** (Stage 1 above)
3. **Audit and fix `redisplay_screen()`** — correct cursor placement for status + input bars
4. **Fix terminal mode around `show_menu()` calls** (Stage 3)
5. **Remove fake status bar data** — replace with real elapsed time, provider, model
6. **Integration test** in a real TTY (run `python3 menu.py` in actual terminal, not piped)
7. **Edge case test** — Ctrl+C during agent run, /resume with existing sessions, long output

---

## Files Likely to Change

| File | Lines | Change |
|------|-------|--------|
| `menu.py` | ~1075–1085 | Arrow key escape sequence assembly |
| `menu.py` | ~830–865 | `redisplay_screen()` cursor positioning |
| `menu.py` | ~886–905 | Restore termios around `show_menu()` in TUI mode |
| `menu.py` | ~799–812 | Replace fake status bar with real data |

---

## Tests / Validation

```bash
# Syntax check
python3 -m py_compile menu.py

# Smoke test — slash commands in fallback mode
echo "/provider" | timeout 3 python3 menu.py 2>&1 | grep -q "Select Provider" && echo "PASS"
echo "/model" | printf '/model\n1\n' | timeout 3 python3 menu.py 2>&1 | grep -q "Select Model" && echo "PASS"

# Full TUI test (requires real TTY — run manually in terminal)
python3 menu.py
# Type "hello world", press Enter → should echo in scroll region
# Press Up arrow → should recall "hello world" from history
# Type /provider → should open provider menu with arrow navigation
# Select provider → should return to TUI with updated provider shown
```

---

## Risks & Tradeoffs

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Terminal left in raw mode on crash | Medium | `finally` block restores settings — already in place |
| Arrow key timeout causes input lag | Low | 10ms timeout on escape seq reads — imperceptible |
| `show_menu()` termios restore breaks if exception | Medium | Wrap in try/finally |
| Real TTY test only possible in interactive session | High | Must test manually — cannot automate via piped stdin |

---

## Open Questions

1. Does `redisplay_screen()` currently work at all in a real TTY? (untested)
2. Should `/help` slash command be added showing all available commands?
3. Should agent output be colorized differently from user commands in scroll region?
4. Is the 500-line scroll buffer sufficient, or should it be configurable?
