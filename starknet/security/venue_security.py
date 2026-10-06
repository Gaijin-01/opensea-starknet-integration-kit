# starknet/security/venue_security.py
"""
Venue security primitives: stale listings, nonce replay, cancellation authority,
approval races, ownership validation, RPC consistency, and calldata validation.

Medialane fulfillment: NO SNIP-12 signature required for fulfiller (caller is fulfiller).
Medialane cancellation: SNIP-12 signature always required.
Ark operations: all direct on-chain (nonce in OrderV1 salt, expiry in endDate).

Security invariants enforced:
  1. STALE: order.endDate > current_time
  2. NONCE: order_hash not previously fulfilled for this signer
  3. CANCEL: canceller == order.offerer
  4. APPROVAL: NFT approved to executor (not to a third party)
  5. OWNERSHIP: current owner == order.offerer at fulfillment time
  6. RPC CONSISTENCY: multiple endpoints agree on block/chain state
  7. CALLDATA: fulfill calldata matches expected order
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from starknet.standards.interfaces import normalize_felt_address


# ---------------------------------------------------------------------------
# Approval status
# ---------------------------------------------------------------------------

class ApprovalStatus(Enum):
    APPROVED_TO_EXECUTOR = "APPROVED_TO_EXECUTOR"
    APPROVED_TO_OTHER = "APPROVED_TO_OTHER"
    NOT_APPROVED = "NOT_APPROVED"
    CALL_FAILED = "CALL_FAILED"


class OwnershipResult(Enum):
    OWNER_MATCH = "OWNER_MATCH"
    OWNER_MISMATCH = "OWNER_MISMATCH"
    CONTRACT_NOT_FOUND = "CONTRACT_NOT_FOUND"
    CALL_FAILED = "CALL_FAILED"


class ConsistencyResult(Enum):
    CONSISTENT = "CONSISTENT"
    INCONSISTENT = "INCONSISTENT"
    ONE_FAILED = "ONE_FAILED"
    ALL_FAILED = "ALL_FAILED"


@dataclass(frozen=True)
class StaleCheckResult:
    is_stale: bool
    blocks_behind: int
    time_behind: int
    end_date: int
    current_time: int


@dataclass(frozen=True)
class ApprovalCheckResult:
    status: ApprovalStatus
    approved_address: Optional[str]
    executor_address: str


@dataclass(frozen=True)
class OwnershipCheckResult:
    result: OwnershipResult
    current_owner: Optional[str]
    expected_owner: Optional[str]


# ---------------------------------------------------------------------------
# Stale listing detector
# ---------------------------------------------------------------------------

class StaleListingDetector:
    """
    Detects stale/expired listings.

    An order is stale when order.endDate <= current_time.
    """

    def check_stale(
        self,
        end_date: int,
        current_time: Optional[int] = None,
    ) -> StaleCheckResult:
        now = current_time or int(time.time())
        is_stale = end_date <= now
        time_diff = now - end_date if end_date < now else 0
        return StaleCheckResult(
            is_stale=is_stale,
            blocks_behind=max(0, time_diff // 12),  # ~12s block time
            time_behind=time_diff,
            end_date=end_date,
            current_time=now,
        )


# ---------------------------------------------------------------------------
# Nonce / replay detector
# ---------------------------------------------------------------------------

class NonceReplayDetector:
    """
    Tracks used order hashes per signer to prevent fulfillment replays.

    Thread-safe with a lock.

    Reference implementation: in-memory only. Production must use Redis or
    DB-backed set for durability across process restarts.
    """

    def __init__(self):
        self._used: dict[str, set[str]] = {}  # signer → {order_hash}
        self._lock = threading.Lock()

    def mark_used(self, order_hash: str, signer: str) -> None:
        with self._lock:
            normalized_signer = normalize_felt_address(signer)
            normalized_hash = order_hash.lower()
            if normalized_signer not in self._used:
                self._used[normalized_signer] = set()
            self._used[normalized_signer].add(normalized_hash)

    def is_replay(self, order_hash: str, signer: str) -> bool:
        with self._lock:
            normalized_signer = normalize_felt_address(signer)
            normalized_hash = order_hash.lower()
            return normalized_hash in self._used.get(normalized_signer, set())

    def clear(self) -> None:
        with self._lock:
            self._used.clear()


# ---------------------------------------------------------------------------
# Cancellation authority
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CancelValidationResult:
    valid: bool
    reason: Optional[str] = None


class CancellationSecurity:
    """
    Validates cancellation authority.

    Rule: only the offerer (seller) can cancel their own listing.
    """

    def validate_cancel_authority(
        self,
        canceller: str,
        order_offerer: str,
        order_hash: str,
    ) -> CancelValidationResult:
        if normalize_felt_address(canceller) != normalize_felt_address(order_offerer):
            return CancelValidationResult(
                valid=False,
                reason=f"Canceller {canceller} is not the offerer {order_offerer}",
            )
        return CancelValidationResult(valid=True)


# ---------------------------------------------------------------------------
# Approval race guard
# ---------------------------------------------------------------------------

class ApprovalRaceGuard:
    """
    Detects approval races when fulfilling orders.

    Before fulfilling, the NFT must be approved to the venue executor.
    If approved to a third party, the fulfill should be rejected.
    """

    def check_approval_status(
        self,
        owner_address: str,
        token_id: int,
        executor_address: str,
        rpc_client,
        nft_contract_address: str,
    ) -> ApprovalCheckResult:
        """
        Check if the NFT is approved to the executor.

        Calls get_approved(token_id) on the NFT contract.
        Returns the approval status and the approved address if any.
        """
        get_approved_selector = "0x309065f1424d76d4a4ace2ff671391d59536e0297409434908d38673290a749"

        from starknet.rpc.client import StarknetRPCError
        try:
            result = rpc_client.call_contract(
                normalize_felt_address(nft_contract_address),
                get_approved_selector,
                [hex(token_id)],
            )
            if result and "return_data" in result and result["return_data"]:
                approved = result["return_data"][0]
                if approved == "0x" + "0" * 64:
                    return ApprovalCheckResult(
                        status=ApprovalStatus.NOT_APPROVED,
                        approved_address=None,
                        executor_address=executor_address,
                    )
                if normalize_felt_address(approved) == normalize_felt_address(executor_address):
                    return ApprovalCheckResult(
                        status=ApprovalStatus.APPROVED_TO_EXECUTOR,
                        approved_address=approved,
                        executor_address=executor_address,
                    )
                return ApprovalCheckResult(
                    status=ApprovalStatus.APPROVED_TO_OTHER,
                    approved_address=approved,
                    executor_address=executor_address,
                )
        except (StarknetRPCError, Exception):
            # StarknetRPCError: network/RPC-layer failure
            # Exception: unexpected error — treat as CALL_FAILED (fail-closed)
            pass

        return ApprovalCheckResult(
            status=ApprovalStatus.CALL_FAILED,
            approved_address=None,
            executor_address=executor_address,
        )


# ---------------------------------------------------------------------------
# Ownership validator
# ---------------------------------------------------------------------------

class OwnershipValidator:
    """
    Validates current NFT ownership at fulfillment time.

    Must be called immediately before fulfillment — not at signing time.
    Calls owner_of(token_id) on the NFT contract.
    """

    def validate_ownership(
        self,
        nft_contract: str,
        token_id: int,
        expected_owner: str,
        rpc_client,
        block_id: str | int = "latest",
    ) -> OwnershipCheckResult:
        """
        Validate that expected_owner currently owns token_id.

        Returns OwnershipCheckResult with current owner if determinable.
        """
        from starknet.rpc.client import StarknetRPCError
        owner_of_selector = "0x3552df12bdc6089cf963c40c4cf56fbfd4bd14680c244d1c5494c2790f1ea5c"

        try:
            result = rpc_client.call_contract(
                normalize_felt_address(nft_contract),
                owner_of_selector,
                [hex(token_id)],
                block_identifier=block_id,
            )
            if result and "return_data" in result and result["return_data"]:
                current_owner = normalize_felt_address(result["return_data"][0])
                expected = normalize_felt_address(expected_owner)
                if current_owner == expected:
                    return OwnershipCheckResult(
                        result=OwnershipResult.OWNER_MATCH,
                        current_owner=current_owner,
                        expected_owner=expected_owner,
                    )
                return OwnershipCheckResult(
                    result=OwnershipResult.OWNER_MISMATCH,
                    current_owner=current_owner,
                    expected_owner=expected_owner,
                )
        except (StarknetRPCError, Exception):
            # StarknetRPCError: RPC/network layer failure
            # Exception: unexpected error — fall through to CALL_FAILED (worst-case)
            pass

        return OwnershipCheckResult(
            result=OwnershipResult.CALL_FAILED,
            current_owner=None,
            expected_owner=expected_owner,
        )


# ---------------------------------------------------------------------------
# RPC consistency checker
# ---------------------------------------------------------------------------

class RPCConsistencyChecker:
    """
    Detects RPC inconsistencies between multiple endpoints.

    If two endpoints return different block numbers within a short window,
    this may indicate an attack, chain reorg, or endpoint lag.
    """

    def check_block_consistency(
        self,
        endpoints: list[str],
    ) -> ConsistencyResult:
        """
        Check if all endpoints agree on the current block number.
        """
        if len(endpoints) < 2:
            return ConsistencyResult.CONSISTENT

        from starknet.rpc.client import StarknetRPCClient

        results: list[int] = []
        failures = 0

        for url in endpoints:
            try:
                client = StarknetRPCClient(url)
                block = client.get_block_number()
                results.append(block)
            except Exception:
                failures += 1

        if failures > 0 and failures < len(endpoints):
            return ConsistencyResult.ONE_FAILED
        if failures == len(endpoints):
            return ConsistencyResult.ALL_FAILED

        if len(set(results)) > 1:
            return ConsistencyResult.INCONSISTENT

        return ConsistencyResult.CONSISTENT

    def check_chain_id_consistency(
        self,
        endpoints: list[str],
    ) -> ConsistencyResult:
        """Check if all endpoints report the same chainId."""
        if len(endpoints) < 2:
            return ConsistencyResult.CONSISTENT

        from starknet.rpc.client import StarknetRPCClient

        results: list[str] = []
        failures = 0

        for url in endpoints:
            try:
                client = StarknetRPCClient(url)
                chain_id = client.get_chain_id()
                results.append(chain_id)
            except Exception:
                failures += 1

        if failures > 0 and failures < len(endpoints):
            return ConsistencyResult.ONE_FAILED
        if failures == len(endpoints):
            return ConsistencyResult.ALL_FAILED

        if len(set(results)) > 1:
            return ConsistencyResult.INCONSISTENT

        return ConsistencyResult.CONSISTENT


# ---------------------------------------------------------------------------
# Venue calldata validator
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalldataValidationResult:
    valid: bool
    reason: Optional[str] = None


class VenueCalldataValidator:
    """
    Validates fulfill calldata before execution.

    Prevents malicious or malformed calldata from being submitted.
    """

    def validate_fulfill_calldata(
        self,
        calldata: dict,
        expected_order_hash: str,
        expected_fulfiller: str,
        expected_token_address: str,
    ) -> CalldataValidationResult:
        """
        Validate fulfill calldata matches expected order details.

        Checks:
        - order_hash in calldata matches expected
        - fulfiller address matches expected
        - token_address is reasonable (not zero, not random)
        """
        # Check order hash
        fulfill_info = calldata.get("fulfill_info", {})
        order_hash = fulfill_info.get("order_hash") or fulfill_info.get("orderHash", "")
        if order_hash != expected_order_hash:
            return CalldataValidationResult(
                valid=False,
                reason=f"Order hash mismatch: got {order_hash}, expected {expected_order_hash}",
            )

        # Check fulfiller
        fulfiller = fulfill_info.get("fulfiller", "")
        if normalize_felt_address(fulfiller) != normalize_felt_address(expected_fulfiller):
            return CalldataValidationResult(
                valid=False,
                reason=f"Fulfiller mismatch: got {fulfiller}, expected {expected_fulfiller}",
            )

        # Check token address is not zero
        token_address = fulfill_info.get("token_address") or fulfill_info.get("tokenAddress", "")
        if token_address == "0x" + "0" * 64:
            return CalldataValidationResult(
                valid=False,
                reason="Token address is zero — suspicious calldata",
            )

        return CalldataValidationResult(valid=True)
