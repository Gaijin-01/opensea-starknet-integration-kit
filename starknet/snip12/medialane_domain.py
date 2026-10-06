# starknet/snip12/medialane_domain.py
"""
SNIP-12 domain definitions for Medialane.

Ground truth source: Medialane official SDK docs
  - SNIP-12 domain version 1 for ERC-721 marketplace
  - SNIP-12 domain version 3 for ERC-1155 marketplace (explicitly confirmed)
  - Medialane uses SNIP-12 typed data for order signing
  - create intent: requiresSignature=True → client signs typed data
  - fulfill intent: requiresSignature=False → no signing (caller is fulfiller)
  - cancel intent: requiresSignature=True

Key SNIP-12 types:
  Message: the signed payload
  Order: the primary type for listing/offer
  StarknetDomain: chain-specific domain separator

Revision semantics (CONFIRMED):
  - revision 0: Pedersen array hash for domain
  - revision 1: Poseidon array hash for domain
  - type_hash always: starknet_keccak(encode_type(...))
  - JSON revision value: INTEGER 1 (not string "1")
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Medialane SNIP-12 domain
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MedialaneSNIP12Domain:
    """
    Medialane's SNIP-12 signing domain.

    version=1 for ERC-721 marketplace
    version=3 for ERC-1155 marketplace
    revision=1 (Poseidon) for newer contracts
    """
    name: str
    version: str
    chain_id: str  # Starknet chain ID: SN_SEPOLIA, SN_MAIN
    revision: int  # 0=Pedersen, 1=Poseidon


def build_medialane_domain(
    version: int,
    chain_id: str,
    revision: int = 1,
) -> MedialaneSNIP12Domain:
    """
    Factory for Medialane SNIP-12 domain.

    Args:
        version: 1 for ERC-721, 3 for ERC-1155 (Medialane specific)
        chain_id: Starknet chain ID (SN_SEPOLIA or SN_MAIN)
        revision: 0=Pedersen, 1=Poseidon (default 1 for new contracts)

    Returns:
        MedialaneSNIP12Domain configured for the given version/chain.
    """
    name = f"Medialane-{version}"
    version_str = str(version)

    return MedialaneSNIP12Domain(
        name=name,
        version=version_str,
        chain_id=chain_id,
        revision=revision,
    )


# ---------------------------------------------------------------------------
# Standard Starknet SNIP-12 domain (from existing verifier.py)
# ---------------------------------------------------------------------------

# Re-export SNIP12Domain from verifier for convenience
try:
    from starknet.snip12.verifier import SNIP12Domain
except ImportError:
    # Forward reference if verifier hasn't been imported yet
    SNIP12Domain = None  # type: ignore


def to_starknet_domain(domain: MedialaneSNIP12Domain) -> dict:
    """
    Convert a MedialaneSNIP12Domain to the StarknetDomain dict format
    used by SNIP-12 verifier.

    The StarknetDomain dict has:
      { "name": str, "version": str, "chain_id": str, "revision": int }
    """
    return {
        "name": domain.name,
        "version": domain.version,
        "chain_id": domain.chain_id,
        "revision": domain.revision,
    }


# ---------------------------------------------------------------------------
# Typed data builders
# ---------------------------------------------------------------------------

ORDER_TYPE = {
    "name": "Order",
    "version": "2",
    "chainId": "StarknetChainId",
    "message": (
        "Asset(tokenAddress, tokenId) Item(floor, amount, payload) "
        "Order(offerer, offer, consideration, startAmount, endAmount, startDate, endDate)"
    ),
    "primaryType": "Order",
    "domain": {
        "name": "StarknetDomain",
        "version": "1",
        "chainId": "StarknetChainId",
        "revision": "1",
    },
    "types": {
        "StarknetDomain": [
            {"name": "name", "type": "felt"},
            {"name": "version", "type": "felt"},
            {"name": "chainId", "type": "felt"},
            {"name": "revision", "type": "felt"},
        ],
        "Order": [
            {"name": "offerer", "type": "felt"},
            {"name": "offer", "type": "Asset"},
            {"name": "consideration", "type": "Asset"},
            {"name": "startAmount", "type": "felt"},
            {"name": "endAmount", "type": "felt"},
            {"name": "startDate", "type": "felt"},
            {"name": "endDate", "type": "felt"},
            {"name": "brokerId", "type": "felt"},
            {"name": "nonce", "type": "felt"},
            {"name": "orderHash", "type": "felt"},
        ],
        "Asset": [
            {"name": "tokenAddress", "type": "felt"},
            {"name": "tokenId", "type": "Uint256"},
        ],
    },
}


def build_listing_typed_data(
    domain: MedialaneSNIP12Domain,
    order_hash: str,
    offerer: str,
    token_address: str,
    token_id: int,
    start_amount: int,
    end_amount: int,
    currency: str,
    start_date: int,
    end_date: int,
    broker_id: str,
    nonce: int = 0,
) -> dict:
    """
    Build SNIP-12 typed data for a Medialane listing intent.

    This matches the Medialane API's `typedData` field returned when
    requiresSignature=True for a create listing intent.
    """
    return {
        "types": {
            "StarknetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "version", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "revision", "type": "felt"},
            ],
            "Order": [
                {"name": "offerer", "type": "felt"},
                {"name": "offer", "type": "Asset"},
                {"name": "consideration", "type": "Asset"},
                {"name": "startAmount", "type": "felt"},
                {"name": "endAmount", "type": "felt"},
                {"name": "startDate", "type": "felt"},
                {"name": "endDate", "type": "felt"},
                {"name": "brokerId", "type": "felt"},
                {"name": "nonce", "type": "felt"},
            ],
            "Asset": [
                {"name": "tokenAddress", "type": "felt"},
                {"name": "tokenId", "type": "Uint256"},
            ],
        },
        "primaryType": "Order",
        "domain": {
            "name": domain.name,
            "version": domain.version,
            "chainId": domain.chain_id,
            "revision": domain.revision,  # Integer, not string
        },
        "message": {
            "offerer": offerer,
            "offer": {
                "tokenAddress": token_address,
                "tokenId": str(token_id),
            },
            "consideration": {
                "tokenAddress": currency,
                "tokenId": "0",  # ERC-20: tokenId=0
            },
            "startAmount": str(start_amount),
            "endAmount": str(end_amount),
            "startDate": str(start_date),
            "endDate": str(end_date),
            "brokerId": broker_id,
            "nonce": str(nonce),
        },
    }


def build_cancel_typed_data(
    domain: MedialaneSNIP12Domain,
    order_hash: str,
    offerer: str,
    token_address: str,
    token_id: int,
    nonce: int,
) -> dict:
    """Build SNIP-12 typed data for a Medialane cancellation intent."""
    return {
        "types": {
            "StarknetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "version", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "revision", "type": "felt"},
            ],
            "Cancel": [
                {"name": "orderHash", "type": "felt"},
                {"name": "offerer", "type": "felt"},
                {"name": "tokenAddress", "type": "felt"},
                {"name": "tokenId", "type": "Uint256"},
                {"name": "nonce", "type": "felt"},
            ],
        },
        "primaryType": "Cancel",
        "domain": {
            "name": domain.name,
            "version": domain.version,
            "chainId": domain.chain_id,
            "revision": domain.revision,
        },
        "message": {
            "orderHash": order_hash,
            "offerer": offerer,
            "tokenAddress": token_address,
            "tokenId": str(token_id),
            "nonce": str(nonce),
        },
    }


def build_offer_typed_data(
    domain: MedialaneSNIP12Domain,
    order_hash: str,
    offerer: str,
    token_address: str,
    token_id: int,
    start_amount: int,
    start_date: int,
    end_date: int,
    broker_id: str,
    nonce: int = 0,
) -> dict:
    """Build SNIP-12 typed data for a Medialane offer intent."""
    return {
        "types": {
            "StarknetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "version", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "revision", "type": "felt"},
            ],
            "Offer": [
                {"name": "offerer", "type": "felt"},
                {"name": "offer", "type": "Asset"},
                {"name": "consideration", "type": "Asset"},
                {"name": "startAmount", "type": "felt"},
                {"name": "startDate", "type": "felt"},
                {"name": "endDate", "type": "felt"},
                {"name": "brokerId", "type": "felt"},
                {"name": "nonce", "type": "felt"},
            ],
            "Asset": [
                {"name": "tokenAddress", "type": "felt"},
                {"name": "tokenId", "type": "Uint256"},
            ],
        },
        "primaryType": "Offer",
        "domain": {
            "name": domain.name,
            "version": domain.version,
            "chainId": domain.chain_id,
            "revision": domain.revision,
        },
        "message": {
            "offerer": offerer,
            "offer": {
                "tokenAddress": token_address,
                "tokenId": str(token_id),
            },
            "consideration": {
                "tokenAddress": "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7",  # ETH
                "tokenId": "0",
            },
            "startAmount": str(start_amount),
            "startDate": str(start_date),
            "endDate": str(end_date),
            "brokerId": broker_id,
            "nonce": str(nonce),
        },
    }
