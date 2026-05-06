#!/usr/bin/env python3
"""
Hindsight integration for ForestGump agent.

Wraps the hindsight-client library to provide semantic/experiential memory
alongside the existing memory.json (structured credentials/networks).

Usage:
    hs = HindsightMemory.from_env()  # None if HINDSIGHT_URL not set
    if hs:
        context = hs.recall("crack WPA2 handshake")
        hs.retain("Command: aircrack-ng ... Output: KEY FOUND", context="wifi")

Environment variables:
    HINDSIGHT_URL      Required. e.g. http://localhost:8888
    HINDSIGHT_API_KEY  Optional. API key if server requires auth.
    HINDSIGHT_BANK     Optional. Bank ID (default: "forestgump")
"""

import os
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

HINDSIGHT_BANK_DEFAULT = "forestgump"


class HindsightMemory:
    """Semantic memory layer backed by a Hindsight server.

    All retain() calls are fire-and-forget (background thread) so they never
    block the agent loop. recall() is synchronous since it gates prompt building.
    """

    def __init__(self, base_url: str, api_key: Optional[str] = None, bank_id: str = HINDSIGHT_BANK_DEFAULT):
        from hindsight_client import Hindsight  # deferred import — graceful if missing
        self._client = Hindsight(base_url=base_url, api_key=api_key)
        self.bank_id = bank_id
        self._ensure_bank()

    def _ensure_bank(self):
        """Create the memory bank if it doesn't exist yet."""
        try:
            self._client.create_bank(self.bank_id)
        except Exception:
            pass  # Bank already exists or server handles it

    @classmethod
    def from_env(cls) -> Optional["HindsightMemory"]:
        """Create from environment variables. Returns None if HINDSIGHT_URL is not set."""
        url = os.environ.get("HINDSIGHT_URL", "").strip()
        if not url:
            return None
        try:
            api_key = os.environ.get("HINDSIGHT_API_KEY") or None
            bank_id = os.environ.get("HINDSIGHT_BANK", HINDSIGHT_BANK_DEFAULT)
            instance = cls(base_url=url, api_key=api_key, bank_id=bank_id)
            logger.info("Hindsight connected: %s (bank: %s)", url, bank_id)
            return instance
        except Exception as e:
            print(f"⚠️  Hindsight unavailable ({e}) — running without semantic memory")
            return None

    def retain(self, content: str, context: Optional[str] = None, tags: Optional[list] = None):
        """Store a memory asynchronously (non-blocking background thread)."""
        if not content or not content.strip():
            return

        def _store():
            try:
                self._client.retain(
                    bank_id=self.bank_id,
                    content=content,
                    context=context,
                    tags=tags,
                )
            except Exception as e:
                logger.debug("Hindsight retain failed: %s", e)

        t = threading.Thread(target=_store, daemon=True)
        t.start()

    def recall(self, query: str, max_tokens: int = 1024) -> str:
        """Retrieve relevant memories as a prompt-ready string. Returns '' on failure."""
        if not query or not query.strip():
            return ""
        try:
            response = self._client.recall(
                bank_id=self.bank_id,
                query=query,
                max_tokens=max_tokens,
                budget="low",
            )
            if not response or not response.results:
                return ""
            return response.to_prompt_string()
        except Exception as e:
            logger.debug("Hindsight recall failed: %s", e)
            return ""

    def close(self):
        """No-op — client is stateless HTTP. Kept for symmetry."""
        pass
