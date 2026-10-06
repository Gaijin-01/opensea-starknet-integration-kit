# starknet/venues/medialane/client.py
"""
Medialane venue client.

AUTHORITATIVE SOURCE: @medialane/sdk/src/chains.ts

CONTRACT ADDRESS POLICY:
  Contract addresses are sourced at runtime from the SDK's chain configuration.
  DO NOT hardcode addresses in this module.

API NOTES:
  - OrderCreated events carry primarily an order hash
  - Full order details must be fetched via get_order_details (separate RPC call)
  - ERC721 and ERC1155 marketplace contracts are SEPARATE deployments
  - ERC1155 partial fills ARE supported (remainingAmount tracked on-chain)

ATTESTATION STATUS:
  - Medialane API structure: IMPLEMENTATION_ASSUMPTION (based on public GitHub layout)
  - ERC1155 partial fill support: IMPLEMENTATION_ASSUMPTION
  - Order details RPC path: IMPLEMENTATION_ASSUMPTION
  - Full venue read path: BLOCKED_EXTERNAL (requires live credentials and running backend)
"""

from dataclasses import dataclass
from typing import Any


# Venue identifier
VENUE_ID = "medialane"


@dataclass
class MedialaneOrder:
    """Normalized representation of a Medialane order."""
    order_hash: str     # Primary key — derived from nonce
    offerer: str        # Seller ContractAddress (normalized felt252)
    token: str          # NFT contract address (normalized felt252)
    token_id: int       # u256 as int (handle low/high limbs)
    quantity: int       # u256 as int
    price: int          # u256 as int (in currency's smallest unit)
    currency: str       # ERC20 contract address
    expiry: int         # u128 Unix timestamp
    nonce: int          # felt nonce

    # Asset classification
    is_erc1155: bool = False
    remaining_amount: int | None = None  # Only for ERC1155 partial fills

    # Venue metadata
    venue: str = VENUE_ID
    raw: dict | None = None  # Original API response for debugging


class MedialaneClient:
    """
    Medialane API client.

    CONSTRUCTION POLICY:
      Pass the authoritative chain config at construction time.
      DO NOT fetch from a hardcoded URL here.
    """

    def __init__(
        self,
        api_base_url: str | None = None,
        rpc_url: str | None = None,
    ):
        """
        Args:
            api_base_url: Medialane REST API base URL (e.g. from @medialane/sdk chains.ts)
            rpc_url: Starknet RPC URL for on-chain calls (e.g. owner_of, get_order_details)
        """
        self.api_base_url = api_base_url
        self.rpc_url = rpc_url

    def fetch_active_orders(self) -> list[MedialaneOrder]:
        """
        Fetch active orders from Medialane REST API.

        ATTESTATION: BLOCKED_EXTERNAL
        - Requires live Medialane backend availability
        - Requires valid API credentials
        - Requires deployed Medialane contracts on target chain
        """
        raise NotImplementedError(
            "Medialane REST API fetch is BLOCKED_EXTERNAL: "
            "live backend not available in current environment. "
            "Use test fixtures or mock for unit tests; "
            "use live integration tests when credentials are available."
        )

    def get_order_details(self, order_hash: str) -> dict | None:
        """
        Fetch full order details for an order hash.

        The OrderCreated event carries primarily the order hash.
        Full details must be fetched via this method.

        ATTESTATION: BLOCKED_EXTERNAL
        """
        raise NotImplementedError(
            "Medialane get_order_details RPC is BLOCKED_EXTERNAL: "
            "requires live Medialane backend and deployed contract."
        )

    def normalize_from_api_response(self, raw: dict) -> MedialaneOrder:
        """
        Normalize a raw Medialane API response to MedialaneOrder.

        Field mapping (API → normalized):
        - offerer / seller → offerer
        - token / nft → token
        - token_id → token_id (handle u256 low/high)
        - quantity → quantity (1 for ERC721, N for ERC1155)
        - price / start_price → price
        - currency / currency_address → currency
        - expiry / expiration → expiry
        - nonce → nonce
        - is_erc1155 / token_type → is_erc1155
        """
        token_id = self._parse_u256(
            raw.get("token_id", raw.get("token_id_low", 0)),
            raw.get("token_id_high", 0)
        )
        quantity = self._parse_u256(
            raw.get("quantity", 1),
            raw.get("quantity_high", 0)
        )
        price = self._parse_u256(
            raw.get("price", raw.get("start_price", 0)),
            raw.get("price_high", 0)
        )
        expiry = int(raw.get("expiry", 0))
        nonce = int(raw.get("nonce", 0))

        is_erc1155 = str(raw.get("is_erc1155", raw.get("token_type", "erc721"))).lower() in ("true", "erc1155")

        return MedialaneOrder(
            order_hash=raw.get("order_hash", raw.get("id", "")),
            offerer=raw.get("offerer", raw.get("seller", "")),
            token=raw.get("token", raw.get("nft", "")),
            token_id=token_id,
            quantity=quantity,
            price=price,
            currency=raw.get("currency", raw.get("currency_address", "")),
            expiry=expiry,
            nonce=nonce,
            is_erc1155=is_erc1155,
            remaining_amount=int(raw["remaining_amount"]) if raw.get("remaining_amount") is not None else None,
            raw=raw,
        )

    @staticmethod
    def _parse_u256(low: Any, high: Any) -> int:
        """Parse u256 from low/high limbs or from a single integer."""
        if isinstance(low, dict):
            # Already a u256 dict
            low_val = int(low.get("low", 0))
            high_val = int(low.get("high", 0))
        else:
            low_val = int(low or 0)
            high_val = int(high or 0)
        return low_val + (high_val << 128)
