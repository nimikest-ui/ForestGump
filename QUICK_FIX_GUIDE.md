# ForestGump CLI - Quick Fix Guide

## IMPORTANT ISSUES TO ADDRESS

### 1. FIX: Hardcoded Sessions Directory (Line 26)

CURRENT:
```python
SESSIONS_DIR = Path("/root/ForestGump/sessions")
```

RECOMMENDED:
```python
SESSIONS_DIR = Path.home() / ".forestgump" / "sessions"
```

IMPACT: Fixes portability issue, makes code work on any system


### 2. FIX: File Permissions on Config File (Lines 115-121)

CURRENT:
```python
def _save_config(self):
    """Save configuration to file."""
    try:
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=2)
    except Exception as e:
        print(f"{Colors.error('[!]')} Failed to save config: {e}")
```

RECOMMENDED:
```python
def _save_config(self):
    """Save configuration to file."""
    try:
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=2)
        # Restrict file to owner only (security for future API keys)
        self.config_file.chmod(0o600)
    except Exception as e:
        print(f"{Colors.error('[!]')} Failed to save config: {e}")
```

IMPACT: Secures sensitive configuration data


### 3. FIX: Make Paths Injectable for Testing (Constructor Parameters)

CURRENT:
```python
class ProviderManager:
    def __init__(self):
        self.config_file = CONFIG_DIR / "config.json"
        CONFIG_DIR.mkdir(exist_ok=True)
        self.config = self._load_config()

class SessionManager:
    def __init__(self):
        SESSIONS_DIR.mkdir(exist_ok=True)
```

RECOMMENDED:
```python
class ProviderManager:
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or (Path.home() / ".forestgump")
        self.config_file = self.config_dir / "config.json"
        self.config_dir.mkdir(exist_ok=True, parents=True)
        self.config = self._load_config()

class SessionManager:
    def __init__(self, sessions_dir: Optional[Path] = None):
        self.sessions_dir = sessions_dir or (Path.home() / ".forestgump" / "sessions")
        self.sessions_dir.mkdir(exist_ok=True, parents=True)
```

UPDATE ForestGumpCLI:
```python
def __init__(self, config_dir: Optional[Path] = None, sessions_dir: Optional[Path] = None):
    self.providers = ProviderManager(config_dir)
    self.sessions = SessionManager(sessions_dir)
    self.models = ModelDiscovery()
```

IMPACT: Enables unit testing without filesystem mocking


## OPTIONAL IMPROVEMENTS

### Minor: Replace Exception Handling (Lines 66, 111, 162)

Add specific exception types instead of bare `except Exception`:

```python
# Line 66 - ModelDiscovery._discover_models()
except ImportError:
    print(f"{Colors.warning('[!]')} Groq library not installed")
except Exception as e:
    print(f"{Colors.warning('[!]')} Could not discover Groq models: {e}")

# Line 111 - ProviderManager._load_config()
except (json.JSONDecodeError, IOError):
    print(f"{Colors.warning('[!]')} Config file corrupted, using defaults")
return {...}

# Line 162 - ProviderManager._check_ollama()
except (subprocess.TimeoutExpired, FileNotFoundError):
    return False
```

IMPACT: Better error diagnostics and debugging


### Nice: Add Logging Instead of Print

At top of file:
```python
import logging
logger = logging.getLogger(__name__)

# Replace: print(f"{Colors.error('[!]')} ...")
# With: logger.error("message")
```

IMPACT: Professional error tracking and debugging


### Nice: Replace curl Subprocess with requests (Line 155)

CURRENT:
```python
def _check_ollama(self) -> bool:
    try:
        subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True,
            timeout=2,
            check=False
        )
        return True
    except Exception:
        return False
```

RECOMMENDED:
```python
def _check_ollama(self) -> bool:
    try:
        import requests
        requests.get("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False
```

IMPACT: Removes dependency on curl binary, more Pythonic


## TESTING STRUCTURE TEMPLATE

Create file: tests/unit/test_cli.py

```python
import pytest
from pathlib import Path
from forestgump_cli import ProviderManager, SessionManager, ForestGumpCLI

@pytest.fixture
def temp_config_dir(tmp_path):
    return tmp_path / "config"

@pytest.fixture
def temp_sessions_dir(tmp_path):
    return tmp_path / "sessions"

def test_provider_manager_init(temp_config_dir):
    pm = ProviderManager(config_dir=temp_config_dir)
    assert pm.config_dir == temp_config_dir
    assert pm.config_dir.exists()

def test_session_manager_init(temp_sessions_dir):
    sm = SessionManager(sessions_dir=temp_sessions_dir)
    assert sm.sessions_dir == temp_sessions_dir
    assert sm.sessions_dir.exists()

def test_config_file_permissions(temp_config_dir):
    pm = ProviderManager(config_dir=temp_config_dir)
    pm._save_config()
    # Check file has 0o600 permissions
    mode = pm.config_file.stat().st_mode & 0o777
    assert mode == 0o600
```

IMPACT: Enable CI/CD and catch regressions


## SUMMARY

Priority fixes:
1. ✓ Fix SESSIONS_DIR path (Line 26)
2. ✓ Add file permission to config (Lines 115-121)
3. ✓ Make paths injectable (Constructor changes)

Optional improvements:
4. Replace bare exceptions
5. Add logging framework
6. Replace curl with requests

All changes are backward compatible and non-breaking.
