# starknet/venues/medialane/adapter.py
"""
Medialane venue adapter — Python implementation of Medialane REST API + on-chain intents.

Ground truth source: Medialane official SDK (@medialane/sdk, GitHub medialane-io/medialane-sdk)
  - REST API base: https://api.medialane.io
  - API key via x-api-key header
  - Client chain: STARKNET
  - Supported currencies: USDC, ETH, STRK (from getListableTokens() local helper)
  - ERC-721 marketplace (mainnet): 0x03eda9a2b6ad90845a43591bac8083ebaf677d51fdf20f503b2c01889e3131fc
  - ERC-1155 marketplace (mainnet): 0x07c4ce1c19ea48cc11135ed22b19ff745f5aec508c3828593002e4f76fdb1b38
  - Source of truth for contract addresses: getCoordinates('STARKNET') — do NOT hardcode

Cancellation intent flow (CONFIRMED from current docs):
  listing/order → POST /v1/intents/cancel → sign if required → submit signature → execute calls

Protocol key invariant (CONFIRMED):
  - create listing: requiresSignature=True → client signs SNIP-12 typed data
  - fulfill listing: requiresSignature=False (buyer is fulfiller, no order signing needed)
  - cancel listing: requiresSignature=True → client signs cancellation intent

ERC-1155 partial fills: remainingAmount field tracked per order.
"""

from __future__ import annotations

import os
import urllib.request
import urllib.error
import json
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class VenueAdapterError(Exception):
    """Base exception for venue adapters."""
    pass


class ConfigurationError(VenueAdapterError):
    """Raised when required credentials (e.g. API key) are not configured."""
    pass


class VenueAPIError(VenueAdapterError):
    """Raised when the Medialane REST API returns a non-2xx response."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Medialane API error {status_code}: {body[:200]}")


class BlockedExternalError(VenueAdapterError):
    """Raised when a feature is blocked by missing external credentials."""
    pass


# ---------------------------------------------------------------------------
# Venues base interface
# ---------------------------------------------------------------------------

class VenueOrderStatus(Enum):
    ACTIVE = "ACTIVE"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class ActiveOrder:
    """Internal representation of an active venue order."""
    order_hash: str
    offerer: str
    token_address: str
    token_id: int
    price: int
    currency: str
    quantity: int = 1  # 1 for ERC-721, N for ERC-1155
    remaining_amount: Optional[int] = None  # ERC-1155 partial fill
    start_date: Optional[int] = None
    end_date: Optional[int] = None
    broker_id: Optional[str] = None
    venue: str = "medialane"

    @property
    def is_erc1155(self) -> bool:
        return self.remaining_amount is not None


@dataclass(frozen=True)
class OwnedToken:
    """An NFT owned by a wallet."""
    contract: str
    token_id: int
    metadata_url: Optional[str] = None
    name: Optional[str] = None


@dataclass
class ListingIntentResult:
    """Result of a create-listing intent call."""
    intent_id: Optional[str] = None
    requires_signature: bool = False
    typed_data: Optional[dict] = None
    signature_submit_url: Optional[str] = None
    executable_calls: Optional[list[dict]] = None  # when requiresSignature=False


@dataclass
class FulfillIntentResult:
    """Result of a fulfill-listing intent call."""
    intent_id: Optional[str] = None
    requires_signature: bool = False
    typed_data: Optional[dict] = None
    signature_submit_url: Optional[str] = None
    executable_calls: Optional[list[dict]] = None  # when requiresSignature=False


@dataclass
class CancelIntentResult:
    """Result of a cancel-listing intent call."""
    intent_id: Optional[str] = None
    requires_signature: bool = True
    typed_data: Optional[dict] = None
    signature_submit_url: Optional[str] = None
    executable_calls: Optional[list[dict]] = None


class VenueAdapter:
    """
    Abstract base for venue adapters (Medialane, Ark, Unframed).

    Defines the interface that all venue integrations must implement.
    """

    def create_listing_intent(
        self,
        offerer: str,
        nft_contract: str,
        token_id: int,
        price: int,
        currency: str,
        end_time: int,
    ) -> ListingIntentResult:
        raise NotImplementedError

    def fulfill_listing_intent(
        self,
        fulfiller: str,
        order_hash: str,
        amount: int = 1,
    ) -> FulfillIntentResult:
        raise NotImplementedError

    def cancel_listing_intent(
        self,
        seller: str,
        order_hash: str,
        token_address: str,
        token_id: int,
    ) -> CancelIntentResult:
        raise NotImplementedError

    def get_active_orders_for_token(
        self,
        nft_contract: str,
        token_id: int,
    ) -> list[ActiveOrder]:
        raise NotImplementedError

    def get_orders_by_user(self, address: str) -> list[ActiveOrder]:
        raise NotImplementedError

    def get_owned_tokens(self, owner_address: str) -> list[OwnedToken]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Medialane adapter
# ---------------------------------------------------------------------------

_MEDIALANE_API_BASE = "https://api.medialane.io"


def _get_api_key() -> str:
    key = os.environ.get("MEDIALANE_API_KEY")
    if not key:
        raise ConfigurationError(
            "MEDIALANE_API_KEY is not set. "
            "Get an API key from portal.medialane.io and set it as an environment variable."
        )
    return key


def _api_request(method: str, path: str, body: Optional[dict] = None) -> dict:
    """Make an authenticated request to the Medialane REST API."""
    api_key = _get_api_key()
    url = f"{_MEDIALANE_API_BASE}{path}"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        raise VenueAPIError(e.code, body_text) from e
    except urllib.error.URLError as e:
        raise VenueAPIError(0, str(e.reason)) from e


def _api_get(path: str) -> dict:
    return _api_request("GET", path)


def _api_post(path: str, body: dict) -> dict:
    return _api_request("POST", path, body)


def _coerce_int(value: Any) -> int:
    """Coerce a value to int (handles string from JSON, hex, etc.)."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("0x") or value.startswith("0X"):
            return int(value, 16)
        return int(value)
    return int(value)


def _parse_order(raw: dict) -> ActiveOrder:
    """Parse a raw Medialane order dict into an internal ActiveOrder."""
    # ERC-1155 has remainingAmount; ERC-721 does not
    remaining = None
    if "remainingAmount" in raw:
        raw_remaining = raw.get("remainingAmount")
        if raw_remaining is not None:
            remaining = _coerce_int(raw_remaining)

    # Price / amount
    price_raw = raw.get("price") or raw.get("startAmount") or raw.get("consideration", {}).get("amount", 0)
    price = _coerce_int(price_raw)

    # Token ID
    token_id_raw = raw.get("tokenId") or raw.get("token_id", 0)
    token_id = _coerce_int(token_id_raw)

    # Currency
    currency = raw.get("currency", "ETH")

    return ActiveOrder(
        order_hash=raw.get("orderHash") or raw.get("order_hash") or raw.get("hash", ""),
        offerer=raw.get("offerer", ""),
        token_address=raw.get("tokenAddress") or raw.get("nftContract", ""),
        token_id=token_id,
        price=price,
        currency=currency,
        quantity=_coerce_int(raw.get("quantity", 1)),
        remaining_amount=remaining,
        start_date=_coerce_int(raw["startDate"]) if raw.get("startDate") else None,
        end_date=_coerce_int(raw["endDate"]) if raw.get("endDate") else None,
        broker_id=raw.get("brokerId"),
        venue="medialane",
    )


class MedialaneAdapter(VenueAdapter):
    """
    Medialane venue adapter using the REST API.

    Flow (CONFIRMED per current Medialane docs):
      - create_listing_intent: POST /v1/intents/listing → requiresSignature=True
      - fulfill_listing_intent: POST /v1/intents/fulfill → requiresSignature=False (buyer signs)
      - cancel_listing_intent: POST /v1/intents/cancel → requiresSignature=True
    """

    def __init__(self, network: str = "mainnet"):
        self.network = network
        self.base_url = _MEDIALANE_API_BASE

    # -- Listings ------------------------------------------------------------

    def create_listing_intent(
        self,
        offerer: str,
        nft_contract: str,
        token_id: int,
        price: int,
        currency: str,
        end_time: int,  # Unix timestamp
    ) -> ListingIntentResult:
        """
        Create a listing intent on Medialane.

        Requires SNIP-12 signature from the offerer (requiresSignature=True).
        After signing, submit signature to signature_submit_url.
        """
        body = {
            "nftContract": nft_contract,
            "tokenId": str(token_id),
            "price": str(price),
            "currency": currency,
            "offerer": offerer,
            "endTime": end_time,
        }
        resp = _api_post("/v1/intents/listing", body)

        requires_sig = resp.get("requiresSignature", False)
        result = ListingIntentResult(
            intent_id=resp.get("intentId") or resp.get("id"),
            requires_signature=requires_sig,
        )

        if requires_sig:
            result.typed_data = resp.get("typedData")
            result.signature_submit_url = resp.get("submitSignatureUrl") or resp.get("submitUrl")
        else:
            # Fulfiller path: calls returned directly
            result.executable_calls = resp.get("calls")

        return result

    def submit_signature(self, submit_url: str, signature: list[str]) -> dict:
        """
        Submit a SNIP-12 signature for a pending intent.

        Returns the executable calls (for listing/cancel) or confirms fulfillment.
        """
        body = {"signature": signature}
        # submit_url may be absolute or relative
        if not submit_url.startswith("http"):
            submit_url = f"{self.base_url}{submit_url}"
        req = urllib.request.Request(
            submit_url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-api-key": _get_api_key()},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise VenueAPIError(e.code, e.read().decode()[:500]) from e

    # -- Fulfillment ---------------------------------------------------------

    def fulfill_listing_intent(
        self,
        fulfiller: str,
        order_hash: str,
        amount: int = 1,
    ) -> FulfillIntentResult:
        """
        Attempt to fulfill an active Medialane listing.

        CONFIRMED: fulfill intent requiresSignature=False per current protocol.
        The fulfiller does NOT sign the order — they execute the calls directly.
        """
        body = {
            "orderHash": order_hash,
            "fulfiller": fulfiller,
            "amount": str(amount),
        }
        resp = _api_post("/v1/intents/fulfill", body)

        requires_sig = resp.get("requiresSignature", False)
        result = FulfillIntentResult(
            intent_id=resp.get("intentId") or resp.get("id"),
            requires_signature=requires_sig,
        )

        if requires_sig:
            result.typed_data = resp.get("typedData")
            result.signature_submit_url = resp.get("submitSignatureUrl") or resp.get("submitUrl")
        else:
            # Buyer executes calls directly — no SNIP-12 signing needed
            result.executable_calls = resp.get("calls")

        return result

    # -- Cancellation -------------------------------------------------------

    def cancel_listing_intent(
        self,
        seller: str,
        order_hash: str,
        token_address: str,
        token_id: int,
    ) -> CancelIntentResult:
        """
        Cancel a Medialane listing.

        CONFIRMED: cancellation requires SNIP-12 signature (requiresSignature=True).
        The seller must sign the cancellation intent.
        """
        body = {
            "orderHash": order_hash,
            "tokenAddress": token_address,
            "tokenId": str(token_id),
        }
        resp = _api_post("/v1/intents/cancel", body)

        requires_sig = resp.get("requiresSignature", True)
        result = CancelIntentResult(
            intent_id=resp.get("intentId") or resp.get("id"),
            requires_signature=requires_sig,
        )

        if requires_sig:
            result.typed_data = resp.get("typedData")
            result.signature_submit_url = resp.get("submitSignatureUrl") or resp.get("submitUrl")
        else:
            result.executable_calls = resp.get("calls")

        return result

    # -- Query --------------------------------------------------------------

    def get_active_orders_for_token(
        self,
        nft_contract: str,
        token_id: int,
    ) -> list[ActiveOrder]:
        """
        Get active (open) orders for a specific NFT.

        Uses Medialane REST API: GET /v1/orders?status=ACTIVE&token_address=...&token_id=...
        """
        path = (
            f"/v1/orders"
            f"?status=ACTIVE"
            f"&token_address={nft_contract}"
            f"&token_id={token_id}"
        )
        resp = _api_get(path)
        raw_orders = resp.get("data") or resp.get("orders") or resp
        if isinstance(raw_orders, dict):
            raw_orders = raw_orders.get("data", [])
        return [_parse_order(o) for o in raw_orders]

    def get_orders_by_user(self, address: str) -> list[ActiveOrder]:
        """
        Get all orders (active and historical) for a user.

        Uses Medialane REST API: GET /v1/orders?address=...
        Returns listings (offerer == address) and offers.
        """
        path = f"/v1/orders?address={address}"
        resp = _api_get(path)
        raw_orders = resp.get("data") or resp.get("orders") or resp
        if isinstance(raw_orders, dict):
            raw_orders = raw_orders.get("data", [])
        return [_parse_order(o) for o in raw_orders]

    def get_owned_tokens(self, owner_address: str) -> list[OwnedToken]:
        """
        Get all NFTs owned by an address.

        Uses Medialane REST API: GET /v1/tokens/{owner_address}
        """
        path = f"/v1/tokens/{owner_address}"
        resp = _api_get(path)
        raw_tokens = resp.get("data") or resp.get("tokens") or resp
        if isinstance(raw_tokens, dict):
            raw_tokens = raw_tokens.get("data", [])
        tokens = []
        for t in raw_tokens:
            contract = t.get("contract") or t.get("nftContract", "")
            token_id = _coerce_int(t.get("tokenId") or t.get("token_id", 0))
            tokens.append(OwnedToken(
                contract=contract,
                token_id=token_id,
                metadata_url=t.get("metadataUrl") or t.get("metadata_url"),
                name=t.get("name"),
            ))
        return tokens
