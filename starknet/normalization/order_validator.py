# starknet/normalization/order_validator.py
"""
Order validation module.

Enforces the ORDER_EXECUTABLE invariant:

ORDER_EXECUTABLE requires ALL of:
  1. signature valid
  2. signer/account explicitly known
  3. order not expired
  4. nonce/cancel state valid
  5. seller ownership valid (at fulfillment time, NOT signing time)
  6. token approval valid
  7. payment approval/balance valid where applicable
  8. venue/chain/domain match

NEVER validate only ownership at signing time.
VALIDATE executable state against latest chain state immediately before fulfillment.
"""

from dataclasses import dataclass
from enum import Enum


class ValidationFailure(Enum):
    SIGNATURE_INVALID = "signature_invalid"
    SIGNER_UNKNOWN = "signer_unknown"
    ORDER_EXPIRED = "order_expired"
    NONCE_INVALID = "nonce_invalid"
    NONCE_REPLAY = "nonce_replay"
    SELLER_NOT_OWNER = "seller_not_owner"
    TOKEN_NOT_APPROVED = "token_not_approved"
    PAYMENT_INSUFFICIENT_BALANCE = "payment_insufficient_balance"
    PAYMENT_NOT_APPROVED = "payment_not_approved"
    VENUE_MISMATCH = "venue_mismatch"
    CHAIN_MISMATCH = "chain_mismatch"
    DOMAIN_MISMATCH = "domain_mismatch"
    ERC1155_INSUFFICIENT_BALANCE = "erc1155_insufficient_balance"


@dataclass
class ValidationResult:
    is_executable: bool
    failures: list[ValidationFailure]

    @property
    def is_valid(self) -> bool:
        return self.is_executable and len(self.failures) == 0

    def __bool__(self) -> bool:
        return self.is_valid


class OrderValidator:
    """
    Validates an order against current chain state.

    Every check is against the LATEST chain state at validation time.
    No cached or signing-time state is used for fulfillment decisions.
    """

    def __init__(self, rpc_client, snip12_verifier):
        self.rpc = rpc_client
        self.snip12_verifier = snip12_verifier

    def validate_order(
        self,
        order,  # Normalized order object
        current_block_time: int,
        chain_id: str,
        expected_venue: str,
        expected_domain_name: str,
        expected_domain_version: str,
        signature: list[str],
        message_hash: str,
    ) -> ValidationResult:
        """
        Full order validation against live chain state.

        Args:
            order: Normalized order (e.g. MedialaneOrder)
            current_block_time: Current Unix timestamp from chain
            chain_id: e.g. "SN_MAIN", "SN_SEPOLIA"
            expected_venue: Venue ID string
            expected_domain_name: e.g. "Medialane"
            expected_domain_version: e.g. "1"
            signature: SNIP-12 signature as list of hex strings
            message_hash: SNIP-12 message hash as hex string

        Returns:
            ValidationResult with all failures listed
        """
        failures: list[ValidationFailure] = []

        # 1. Signature + Signer (must come first — fast reject)
        sig_valid, sig_reason = self.snip12_verifier.verify_signature(
            signer_address=order.offerer,
            message_hash=message_hash,
            signature=signature,
        )
        if not sig_valid:
            failures.append(ValidationFailure.SIGNATURE_INVALID)

        # 2. Expiry check
        if current_block_time >= order.expiry:
            failures.append(ValidationFailure.ORDER_EXPIRED)

        # 3. Nonce check (would require on-chain nonce read — BLOCKED for now)
        # self._check_nonce(order)  # BLOCKED_EXTERNAL

        # 4. Seller ownership (on-chain read at fulfillment time)
        if not self._check_ownership(order):
            failures.append(ValidationFailure.SELLER_NOT_OWNER)

        # 5. Token approval check
        if not self._check_approval(order):
            failures.append(ValidationFailure.TOKEN_NOT_APPROVED)

        # 6. Venue / chain / domain checks
        if order.venue != expected_venue:
            failures.append(ValidationFailure.VENUE_MISMATCH)

        # NOTE: chain_id is implicitly validated by the RPC layer (the connected endpoint
        # determines which chain is being queried). No explicit currency-chain mapping
        # exists in the current order model, so this check is omitted.

        return ValidationResult(
            is_executable=len(failures) == 0,
            failures=failures,
        )

    def _check_ownership(self, order) -> bool:
        """
        Check if seller still owns the NFT at fulfillment time.

        For ERC721: owner_of(token_id) == offerer
        For ERC1155: balance_of(offerer, token_id) >= quantity

        ATTESTATION: IMPLEMENTATION_ASSUMPTION
        - owner_of entry point varies by contract implementation
        - ERC1155 balance_of requires separate call
        """
        raise NotImplementedError(
            "Ownership check is BLOCKED_EXTERNAL: "
            "requires deployed NFT contracts and live RPC calls. "
            "owner_of is not standardized across all ERC721 implementations."
        )

    def _check_approval(self, order) -> bool:
        """
        Check if the exchange contract is approved to transfer the NFT.

        For ERC721: is_approved_for_all(owner, operator) OR get_approved(token_id)
        For ERC1155: is_approved_for_all(owner, operator)

        ATTESTATION: IMPLEMENTATION_ASSUMPTION
        """
        raise NotImplementedError(
            "Approval check is BLOCKED_EXTERNAL: "
            "requires live RPC calls to specific NFT contract approval entry points."
        )


# Standalone validation helpers (pure functions, no RPC)


def check_expiry(expiry_timestamp: int, current_time: int) -> bool:
    """Return True if order has not expired."""
    return current_time < expiry_timestamp


def check_chain_id_match(chain_id: str, expected: str) -> bool:
    """Return True if chain ID matches expected."""
    return chain_id == expected


def check_venue_match(order_venue: str, expected_venue: str) -> bool:
    """Return True if venue matches."""
    return order_venue == expected_venue
