"""
Cost controls: token pricing and an answer cache.

Prices are configuration, not constants, because providers change them and a
local model costs nothing per token. Set LLM_PRICE_INPUT_PER_M and
LLM_PRICE_OUTPUT_PER_M (US dollars per million tokens) from your provider's
pricing page; the default of 0 matches a free tier or a self-hosted model.
See docs/COSTS.md.
"""
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional


class Pricing:
    def __init__(self, input_per_m: Optional[float] = None, output_per_m: Optional[float] = None):
        self.input_per_m = float(os.getenv("LLM_PRICE_INPUT_PER_M", "0") if input_per_m is None else input_per_m)
        self.output_per_m = float(os.getenv("LLM_PRICE_OUTPUT_PER_M", "0") if output_per_m is None else output_per_m)

    @property
    def configured(self) -> bool:
        return self.input_per_m > 0 or self.output_per_m > 0

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.input_per_m + completion_tokens * self.output_per_m) / 1_000_000

    def as_dict(self) -> Dict[str, Any]:
        return {"input_per_m": self.input_per_m, "output_per_m": self.output_per_m, "configured": self.configured}


class AnswerCache:
    """
    LRU + TTL cache of finished answers.

    The key includes the index version, so any upload or delete invalidates every
    entry: a cached answer can never cite a document that has since changed.
    A hit skips embedding, search, reranking and the LLM call entirely.
    """

    def __init__(self, max_entries: int = 256, ttl_seconds: float = 3600):
        self.max_entries = max_entries
        self.ttl = ttl_seconds
        self._items: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self.ttl > 0 and self.max_entries > 0

    @staticmethod
    def key(**parts: Any) -> str:
        return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        with self._lock:
            item = self._items.get(key)
            if item and time.time() - item[0] <= self.ttl:
                self._items.move_to_end(key)
                self.hits += 1
                return item[1]
            if item:
                del self._items[key]
            self.misses += 1
            return None

    def put(self, key: str, value: Dict[str, Any]):
        if not self.enabled:
            return
        with self._lock:
            self._items[key] = (time.time(), value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "enabled": self.enabled,
            "entries": len(self._items),
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }
