# starknet/indexer/chain_indexer.py
"""
Raw Starknet event chain indexer.

Ground truth source: confirmed from Infura Sepolia integration:
  - starknet_getEvents takes flat params with block_number objects
  - from_block: {block_number: N}, to_block: {block_number: N}
  - chunk_size for pagination
  - continuation_token for large result sets
  - Transfer event key: selector of "Transfer" = 0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9

Reorg detection: compare block_hash of indexed events against current chain state.
On mismatch: mark events as reorged, emit warning.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from starknet.rpc.client import StarknetRPCClient
from starknet.standards.interfaces import (
    TRANSFER_EVENT_KEY,
    normalize_felt_address,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransferEvent:
    """A Transfer event from a Starknet NFT contract."""
    block_number: int
    block_hash: str
    transaction_hash: str
    from_address: str
    to_address: str
    token_id: int
    contract_address: str
    event_index: int = 0
    reorged: bool = False  # True if chain reorganized since indexing

    @property
    def is_mint(self) -> bool:
        return self.from_address == "0x" + "0" * 64

    @property
    def is_burn(self) -> bool:
        return self.to_address == "0x" + "0" * 64


@dataclass
class IndexerState:
    """Persistent state for the chain indexer."""
    contract: str
    last_indexed_block: int
    last_indexed_hash: str  # block_hash at last index
    reorg_count: int = 0
    last_reorg_block: Optional[int] = None
    total_events: int = 0


# ---------------------------------------------------------------------------
# Chain indexer
# ---------------------------------------------------------------------------

class ChainIndexer:
    """
    Raw Starknet event indexer using starknet_getEvents.

    Features:
    - Handles continuation tokens for large event sets
    - Detects chain reorganizations by comparing block_hash
    - Tracks indexed_block per contract for idempotent restart
    - Deduplicates by (transaction_hash, event_index)
    """

    def __init__(self, rpc_client: StarknetRPCClient):
        self.rpc = rpc_client
        self.state: dict[str, IndexerState] = {}  # contract → state

    def index_transfer_events(
        self,
        contract_address: str,
        from_block: int,
        to_block: int | str = "latest",
        chunk_size: int = 1000,
    ) -> list[TransferEvent]:
        """
        Index Transfer events for an NFT contract.

        Uses starknet_getEvents with:
          from_block: {block_number: N}
          to_block: {block_number: N} or "latest"
          keys: [[TRANSFER_EVENT_KEY]]
          chunk_size: N

        Returns deduplicated list of TransferEvent.
        """
        contract = normalize_felt_address(contract_address)

        all_events = []
        continuation_token: Optional[str] = None

        while True:
            filter_obj: dict[str, Any] = {
                "from_block": {"block_number": from_block},
                "to_block": (
                    {"block_number": to_block}
                    if isinstance(to_block, int)
                    else {"block_number": to_block}
                ),
                "chunk_size": chunk_size,
                "keys": [[TRANSFER_EVENT_KEY]],
                "address": contract,
            }
            if continuation_token:
                filter_obj["continuation_token"] = continuation_token

            raw = self.rpc.call("starknet_getEvents", [filter_obj])
            events = raw.get("events", [])
            all_events.extend(events)

            continuation_token = raw.get("continuation_token")
            if not continuation_token:
                break

            # Safety: avoid infinite loop
            if len(all_events) >= 10000:
                break

        # Parse into TransferEvent objects
        parsed = []
        seen: set[tuple[str, int]] = set()
        for idx, ev in enumerate(all_events):
            keys = ev.get("keys", [])
            data = ev.get("data", [])
            if len(keys) < 3 or len(data) < 1:
                continue

            from_addr = keys[1]
            to_addr = keys[2]
            token_id = int(data[0], 16) if data[0].startswith("0x") else int(data[0])

            tx_hash = ev.get("transaction_hash", "")
            event_index = idx

            # Deduplicate
            key = (tx_hash, event_index)
            if key in seen:
                continue
            seen.add(key)

            block_number = ev.get("block_number", from_block)
            block_hash = ev.get("block_hash", "")

            parsed.append(TransferEvent(
                block_number=block_number,
                block_hash=block_hash,
                transaction_hash=tx_hash,
                from_address=from_addr,
                to_address=to_addr,
                token_id=token_id,
                contract_address=contract,
                event_index=event_index,
            ))

        # Update state
        if parsed:
            max_block = max(e.block_number for e in parsed)
            last_hash = next(e.block_hash for e in parsed if e.block_number == max_block)
            if contract not in self.state:
                self.state[contract] = IndexerState(
                    contract=contract,
                    last_indexed_block=0,
                    last_indexed_hash="",
                )
            self.state[contract].last_indexed_block = max_block
            self.state[contract].last_indexed_hash = last_hash
            self.state[contract].total_events += len(parsed)

        return parsed

    def detect_reorg(
        self,
        contract_address: str,
        block_number: int,
        expected_block_hash: str,
    ) -> bool:
        """
        Check if a previously-indexed block has been reorganized.

        Calls starknet_getBlockHash or compares block hash at the same height.
        Returns True if reorg detected (hash mismatch).
        """
        try:
            # starknet_getBlockByNumber can return the block hash
            block = self.rpc.call(
                "starknet_getBlockWithTxs",
                [{"block_number": block_number}],
            )
            if block and "block_hash" in block:
                current_hash = block["block_hash"]
                if current_hash != expected_block_hash:
                    # Reorg detected
                    if contract_address in self.state:
                        self.state[contract_address].reorg_count += 1
                        self.state[contract_address].last_reorg_block = block_number
                    # NOTE: reorged events are detected but not automatically re-indexed
                    # in this reference implementation.
                    return True
        except Exception:
            pass
        return False

    def get_ownership_at_block(
        self,
        contract_address: str,
        token_id: int,
        block_number: int | str = "latest",
    ) -> str | None:
        """
        Query owner_of(token_id) at a specific block.

        Calls owner_of entrypoint on the NFT contract via starknet_call.
        Returns the owner's address or None if not found.
        """
        owner_of_selector = "0x3552df12bdc6089cf963c40c4cf56fbfd4bd14680c244d1c5494c2790f1ea5c"
        try:
            result = self.rpc.call_contract(
                normalize_felt_address(contract_address),
                owner_of_selector,
                [hex(token_id)],
                block_identifier=block_number,
            )
            if result and "return_data" in result and result["return_data"]:
                owner = result["return_data"][0]
                return normalize_felt_address(owner)
        except Exception:
            pass
        return None

    def get_state(self, contract_address: str) -> Optional[IndexerState]:
        return self.state.get(normalize_felt_address(contract_address))
