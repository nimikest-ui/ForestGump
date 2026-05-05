# Task 5: Encrypted Credential Storage - Implementation Plan

**Status:** Planning Phase  
**Date:** May 5, 2026  
**Objective:** Add encrypted credential storage to replace plaintext JSON in ForestGump

---

## Current State Analysis

### Existing Credential Storage (memory.py)
```python
# Current: plaintext JSON
{
  "target.com": {
    "username": "admin",
    "password": "password123",  # ⚠️ PLAINTEXT!
    "method": "http_basic",
    "date_found": "2026-05-05"
  }
}
```

**Issues:**
- ❌ Credentials stored as plaintext in JSON
- ❌ No encryption at rest
- ❌ Memory files readable with `cat`
- ❌ No key management system
- ❌ No secure deletion
- ❌ ~/.forestgump/memory/*.json visible in file listing

---

## Task 5 Requirements

### 1. Encryption at Rest
- ✅ Encrypt credential objects before saving to disk
- ✅ Decrypt on load/access
- ✅ Use industry-standard encryption (AES-256-GCM)
- ✅ Fail gracefully if decryption fails

### 2. Key Management
- ✅ Derive encryption key from master password (PBKDF2)
- ✅ Store key derivation params (salt, iterations) with ciphertext
- ✅ Option to change master password
- ✅ Support environment variable override (FORESTGUMP_KEY)

### 3. Secure Credential Access
- ✅ Add MemoryManager methods:
  - `get_credential(target)` - retrieve decrypted credential
  - `update_credential(target, cred)` - save encrypted credential
  - `delete_credential(target)` - secure deletion
  - `list_credentials()` - list targets only (no plaintext)

### 4. Integration with REPL
- ✅ Update InteractiveREPL to use encrypted storage
- ✅ REPL command: `/credentials` - list stored targets
- ✅ REPL command: `/add-cred <target> <user> <pass>` - add encrypted credential
- ✅ REPL command: `/show-cred <target>` - decrypt and display (with confirmation)
- ✅ REPL command: `/del-cred <target>` - delete encrypted credential

### 5. Tool Sandbox Integration
- ✅ Tool sandbox can request credentials from MemoryManager
- ✅ Credentials auto-injected into tool execution (e.g., `sshpass -p $PASSWORD ssh`)
- ✅ Example: `ssh -u $USER@target.com` → lookup encrypted credential → auto-fill

### 6. Security Features
- ✅ Master password validation on first use
- ✅ Password strength requirements
- ✅ Option to use environment variable (CI/CD integration)
- ✅ Secure credential display with timeout (auto-clear after 10s)
- ✅ Audit log of credential access
- ✅ Warning when accessing credentials in non-interactive mode

### 7. Testing & Verification
- ✅ Unit tests for encryption/decryption
- ✅ Key derivation tests
- ✅ Integration tests with MemoryManager
- ✅ End-to-end tests with REPL commands
- ✅ Security tests (verify no plaintext in files)

---

## Implementation Phases

### Phase 1: Cryptography Foundation (encryptedcreds.py)
**Files to create:**
- `encryptedcreds.py` (new, ~400 lines)
  - `CryptoManager` class - encryption/decryption core
  - `CredentialVault` class - credential storage abstraction
  - `CredentialAuditLog` class - access logging

**Key classes:**

```python
class CryptoManager:
    """Handle encryption/decryption with PBKDF2 + AES-256-GCM"""
    
    def __init__(self, master_password: str, salt: bytes = None):
        """Initialize with master password, derive key"""
        self.salt = salt or os.urandom(16)
        self.key = self._derive_key(master_password)
        self.iv_length = 12  # GCM IV
        self.tag_length = 16  # GCM auth tag
    
    def encrypt(self, plaintext: str) -> dict:
        """Encrypt string, return {ciphertext, salt, iv, tag}"""
        pass
    
    def decrypt(self, encrypted_data: dict) -> str:
        """Decrypt using stored salt/iv/tag"""
        pass
    
    def _derive_key(self, password: str) -> bytes:
        """PBKDF2-SHA256: 100k iterations"""
        pass


class CredentialVault:
    """Secure credential storage"""
    
    def __init__(self, crypto_manager: CryptoManager):
        self.crypto = crypto_manager
        self.credentials = {}  # In-memory cache
        self.audit_log = CredentialAuditLog()
    
    def store(self, target: str, username: str, password: str, method: str):
        """Encrypt and store credential"""
        pass
    
    def retrieve(self, target: str, user_id: str = None) -> dict:
        """Decrypt and return credential with audit log"""
        pass
    
    def delete(self, target: str):
        """Securely delete credential"""
        pass
    
    def list_targets(self) -> List[str]:
        """Return target names only (no plaintext)"""
        pass


class CredentialAuditLog:
    """Log all credential access for security audit"""
    
    def __init__(self, log_file: str = "~/.forestgump/audit.log"):
        self.log_file = Path(log_file).expanduser()
    
    def log_access(self, target: str, user_id: str, action: str):
        """Log: timestamp, user, target, action"""
        pass
    
    def get_history(self, target: str = None) -> List[dict]:
        """Get access history for audit"""
        pass
```

**Crypto spec:**
- Algorithm: AES-256 in GCM mode (authenticated encryption)
- Key derivation: PBKDF2-SHA256, 100,000 iterations
- IV: 12 bytes (random per encryption)
- Authentication tag: 16 bytes (built into GCM)
- Salt: 16 bytes (stored with ciphertext)
- Python libraries:
  - `cryptography.hazmat.primitives.ciphers.aead` (AES-GCM)
  - `cryptography.hazmat.primitives.kdf.pbkdf2` (PBKDF2)

**Dependencies to add:**
```
cryptography>=41.0.0  # Already installed for CLAUDE.md hooks
```

---

### Phase 2: MemoryManager Integration (memory.py)
**Changes:**
- Update `MemoryManager.__init__()` to accept `master_password`
- Create `CredentialVault` instance
- Replace `self.credentials` dict with vault methods
- Add encryption toggle (can disable for dev/testing)

```python
class MemoryManager:
    def __init__(self, session_id: str, use_encryption: bool = True, master_password: str = None):
        # Initialize CredentialVault if use_encryption=True
        if use_encryption:
            password = master_password or os.environ.get("FORESTGUMP_KEY")
            if not password:
                password = self._prompt_master_password()
            self.crypto_manager = CryptoManager(password)
            self.credential_vault = CredentialVault(self.crypto_manager)
        else:
            self.credential_vault = None  # Fallback to plaintext (dev mode)
    
    def add_credential(self, target: str, username: str, password: str, method: str = None):
        """Add encrypted credential"""
        if self.credential_vault:
            self.credential_vault.store(target, username, password, method)
        else:
            # Fallback to plaintext
            self.credentials[target] = {"username": username, "password": password, "method": method}
    
    def get_credential(self, target: str) -> dict:
        """Get decrypted credential"""
        if self.credential_vault:
            return self.credential_vault.retrieve(target)
        else:
            return self.credentials.get(target)
    
    def list_targets(self) -> List[str]:
        """List credential targets (no plaintext)"""
        if self.credential_vault:
            return self.credential_vault.list_targets()
        else:
            return list(self.credentials.keys())
```

---

### Phase 3: REPL Integration (forestgump_cli.py)
**New REPL commands:**

```python
# In InteractiveREPL.parse_command():

def handle_command(self, cmd: str):
    if cmd.startswith("/credentials"):
        targets = self.memory.list_targets()
        print(f"[+] Stored credentials ({len(targets)}):")
        for target in targets:
            print(f"    - {target}")
    
    elif cmd.startswith("/add-cred"):
        parts = cmd.split()
        if len(parts) < 4:
            print("[!] Usage: /add-cred <target> <user> <password>")
            return
        target, user, pwd = parts[1], parts[2], parts[3]
        self.memory.add_credential(target, user, pwd)
        print(f"[✓] Credential stored for {target}")
    
    elif cmd.startswith("/show-cred"):
        target = cmd.split()[1] if len(cmd.split()) > 1 else None
        if not target:
            print("[!] Usage: /show-cred <target>")
            return
        cred = self.memory.get_credential(target)
        if cred:
            print(f"[+] Credential for {target}:")
            print(f"    User: {cred['username']}")
            print(f"    Pass: {'*' * len(cred['password'])}")  # Masked
            print("[!] Clearing in 10 seconds...")
            time.sleep(10)
        else:
            print(f"[!] No credential for {target}")
    
    elif cmd.startswith("/del-cred"):
        target = cmd.split()[1] if len(cmd.split()) > 1 else None
        if not target:
            print("[!] Usage: /del-cred <target>")
            return
        self.memory.delete_credential(target)
        print(f"[✓] Credential deleted for {target}")
```

---

### Phase 4: Tool Sandbox Integration (toolsandbox.py)
**Credential injection in command execution:**

```python
class Sandbox:
    def execute_with_safeguards(self, command: str, memory: MemoryManager = None):
        """Execute command with optional credential injection"""
        
        # Extract credential placeholders
        # Example: ssh -u $USER@$TARGET -p $PASS
        pattern = r'\$(\w+)'
        placeholders = re.findall(pattern, command)
        
        substitutions = {}
        for placeholder in placeholders:
            # Try memory lookup
            if memory and placeholder in ["USER", "PASS", "KEY"]:
                # Lookup credential
                cred = memory.get_credential(placeholder)
                if cred:
                    substitutions[f"${placeholder}"] = cred["password"]
        
        # Substitute
        for placeholder, value in substitutions.items():
            command = command.replace(placeholder, value)
        
        # Execute
        return CommandExecutor.execute(command)
```

---

### Phase 5: Testing Suite (test_task_5.py)
**Create comprehensive test suite (~300 lines):**

```python
import pytest
from encryptedcreds import CryptoManager, CredentialVault
from memory import MemoryManager

class TestCryptoManager:
    def test_encrypt_decrypt(self):
        """Verify encryption/decryption roundtrip"""
        pass
    
    def test_key_derivation(self):
        """Verify PBKDF2 produces consistent keys"""
        pass
    
    def test_different_passwords(self):
        """Verify different passwords produce different keys"""
        pass
    
    def test_gcm_authentication(self):
        """Verify GCM detects tampered ciphertext"""
        pass

class TestCredentialVault:
    def test_store_retrieve(self):
        """Verify credential store/retrieve"""
        pass
    
    def test_delete(self):
        """Verify credential secure deletion"""
        pass
    
    def test_list_targets(self):
        """Verify list returns targets only"""
        pass
    
    def test_audit_log(self):
        """Verify access logging"""
        pass

class TestMemoryManagerEncryption:
    def test_add_credential_encrypted(self):
        """Verify credentials are encrypted when stored"""
        pass
    
    def test_get_credential_decrypted(self):
        """Verify credentials are decrypted when retrieved"""
        pass
    
    def test_fallback_plaintext(self):
        """Verify plaintext fallback for dev mode"""
        pass

class TestREPLIntegration:
    def test_add_cred_command(self):
        """Verify /add-cred command"""
        pass
    
    def test_show_cred_command(self):
        """Verify /show-cred command"""
        pass
    
    def test_credentials_list_command(self):
        """Verify /credentials command"""
        pass

class TestSecurityFeatures:
    def test_no_plaintext_in_files(self):
        """Verify credentials not stored as plaintext"""
        pass
    
    def test_master_password_validation(self):
        """Verify master password required"""
        pass
    
    def test_environment_variable_override(self):
        """Verify FORESTGUMP_KEY env var works"""
        pass
```

---

## File Changes Summary

| File | Changes | Lines | Status |
|------|---------|-------|--------|
| `encryptedcreds.py` | NEW | 400 | Phase 1 |
| `memory.py` | MODIFY | +50 | Phase 2 |
| `forestgump_cli.py` | MODIFY | +100 | Phase 3 |
| `toolsandbox.py` | MODIFY | +50 | Phase 4 |
| `test_task_5.py` | NEW | 300 | Phase 5 |

**Total new code:** ~850 lines  
**Total modified code:** ~200 lines

---

## Usage Examples

### CLI: Set master password on first use
```bash
$ forestgump_cli.py chat

[*] First-time setup: Enter master password for encrypted credentials
Master password: ••••••••••
Confirm: ••••••••••
[✓] Master password set
```

### REPL: Store credentials
```bash
forrestgump [sonnet]> /add-cred router.local admin router123

[✓] Credential stored for router.local
```

### REPL: List credentials
```bash
forrestgump [sonnet]> /credentials

[+] Stored credentials (3):
    - router.local
    - target.com
    - ssh.internal
```

### REPL: Show credential
```bash
forrestgump [sonnet]> /show-cred router.local

[+] Credential for router.local:
    User: admin
    Pass: ••••••••••
[!] Clearing in 10 seconds...
```

### Tool Sandbox: Auto-inject credentials
```bash
forrestgump [sonnet]> scan router with ssh

Agent: Use `ssh -u $ADMIN@router.local` to connect

[*] Found credential for ADMIN, injecting...
>>> Command: ssh -u admin@router.local
Execute? [y/n]: y
[+] Connected to router.local
```

### Environment variable: CI/CD integration
```bash
export FORESTGUMP_KEY="master_password_here"
forestgump_cli.py chat -q "scan network"
# Uses encrypted credentials without prompting
```

---

## Security Considerations

### Threat Model
- ❌ **Does NOT protect against:**
  - Memory-resident attacks (plaintext in RAM while REPL is running)
  - Master password compromise
  - Compromised filesystem
  
- ✅ **DOES protect against:**
  - Accidental exposure (cat ~/.forestgump/memory/*.json)
  - Disk forensics (encrypted at rest)
  - Credential theft via GitHub repo leak
  - Casual inspection

### Recommended Practices
1. Use strong master password (16+ characters)
2. Use environment variable for CI/CD (not hardcoded)
3. Store audit logs for compliance
4. Rotate credentials regularly
5. Never commit plaintext credentials

---

## Testing Roadmap

### Unit Tests
- ✅ Encryption/decryption roundtrip
- ✅ PBKDF2 key derivation
- ✅ GCM authentication verification
- ✅ Credential storage/retrieval
- ✅ Audit logging

### Integration Tests
- ✅ MemoryManager with CredentialVault
- ✅ REPL commands (/add-cred, /show-cred, /credentials, /del-cred)
- ✅ Tool Sandbox credential injection
- ✅ Session persistence with encryption

### Security Tests
- ✅ Verify no plaintext in saved files
- ✅ Verify master password required on first use
- ✅ Verify environment variable override works
- ✅ Verify audit log contains access records
- ✅ Verify credentials cleared from memory after display

---

## Success Criteria

- ✅ All credentials encrypted before saving to disk
- ✅ Master password required on first use
- ✅ Can retrieve and decrypt credentials in REPL
- ✅ Tool Sandbox can auto-inject credentials
- ✅ Environment variable override works for CI/CD
- ✅ No plaintext credentials in any JSON files
- ✅ Audit log tracks all credential access
- ✅ 90%+ test coverage
- ✅ All tests passing

---

## Timeline

- **Phase 1 (Crypto):** 30 min
- **Phase 2 (Memory):** 20 min
- **Phase 3 (REPL):** 30 min
- **Phase 4 (Sandbox):** 20 min
- **Phase 5 (Tests):** 40 min
- **Total:** ~2.5 hours

---

**Ready to proceed? Confirm and I'll begin Phase 1 implementation.**
