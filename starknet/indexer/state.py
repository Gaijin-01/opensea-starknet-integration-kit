# starknet/indexer/state.py
"""
Indexer state persistence for idempotent restart and reorg tracking.

Atomic write: write to temp file then rename to prevent corruption on crash.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class PersistedIndexerState:
    """
    Persistent state for a chain indexer.

    Tracks:
    - last_block: last successfully indexed block number
    - reorg_count: total reorgs detected
    - last_reorg_block: block number of most recent reorg
    - last_block_hash: block hash at last index (for reorg detection)
    - total_events: total events indexed across all runs
    """
    last_block: int
    reorg_count: int
    last_reorg_block: Optional[int]
    last_block_hash: Optional[str]
    total_events: int
    contract: Optional[str] = None
    indexer_name: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict) -> "PersistedIndexerState":
        return cls(
            last_block=d.get("last_block", 0),
            reorg_count=d.get("reorg_count", 0),
            last_reorg_block=d.get("last_reorg_block"),
            last_block_hash=d.get("last_block_hash"),
            total_events=d.get("total_events", 0),
            contract=d.get("contract"),
            indexer_name=d.get("indexer_name"),
        )


def save_state(state: PersistedIndexerState, path: str) -> None:
    """
    Save indexer state to a JSON file atomically.

    Write to a temporary file in the same directory, then rename to target.
    This prevents corruption if the process crashes mid-write.
    """
    dirname = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dirname, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state.to_dict(), f)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def load_state(path: str) -> Optional[PersistedIndexerState]:
    """
    Load indexer state from a JSON file.

    Returns None if the file doesn't exist.
    Raises on parse errors.
    """
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        data = json.load(f)
    return PersistedIndexerState.from_dict(data)
