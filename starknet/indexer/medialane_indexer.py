# starknet/indexer/medialane_indexer.py
"""
Medialane REST-based order indexer.

Ground truth source: Medialane official SDK docs
  - REST API: GET /v1/orders?status=ACTIVE&token_address=...&token_id=...
  - REST API: GET /v1/orders?address=...  (by user)
  - REST API: GET /v1/tokens/{owner_address}
  - REST API base: https://api.medialane.io
  - Event types: order.created, order.fulfilled, token.minted (via SSE webhooks)
  - Medialane ERC-721 marketplace (mainnet): 0x03eda9a2b6ad90845a43591bac8083ebaf677d51fdf20f503b2c01889e3131fc
  - Medialane ERC-1155 marketplace (mainnet): 0x07c4ce1c19ea48cc11135ed22b19ff745f5aec508c3828593002e4f76fdb1b38
  - Start blocks (mainnet): ERC721=11198146, ERC1155=11198267

Indexer model: deterministic event reducer.
  The database is a reduction of on-chain events, rebuildable at any time.
  This module polls the REST API (which wraps the indexer cache) for active orders.
"""

from __future__ import annotations

import os
import urllib.request
import urllib.error
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from starknet.venues.medialane.adapter import _api_get, ConfigurationError


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndexedOrder:
    """
    Internal representation of an indexed Medialane order.
    Combines REST API order data with indexing metadata.
    """
    order_hash: str
    offerer: str
    token_address: str
    token_id: int
    price: int
    currency: str
    quantity: int = 1
    remaining_amount: Optional[int] = None  # ERC-1155 partial fill
    start_date: Optional[int] = None
    end_date: Optional[int] = None
    broker_id: Optional[str] = None
    # Indexing metadata
    indexed_at: int = field(default_factory=lambda: int(time.time()))
    source: str = "medialane_rest"
    is_erc1155: bool = False

    @classmethod
    def from_rest_order(cls, raw: dict) -> "IndexedOrder":
        """Parse a raw Medialane REST API order dict into an IndexedOrder."""
        # ERC-1155 has remainingAmount field
        remaining = None
        if "remainingAmount" in raw:
            raw_remaining = raw.get("remainingAmount")
            if raw_remaining is not None:
                if isinstance(raw_remaining, str):
                    remaining = int(raw_remaining, 16) if raw_remaining.startswith("0x") else int(raw_remaining)
                else:
                    remaining = int(raw_remaining)

        price = _coerce_int(raw.get("price") or raw.get("startAmount", 0))
        token_id = _coerce_int(raw.get("tokenId") or raw.get("token_id", 0))

        return cls(
            order_hash=raw.get("orderHash") or raw.get("hash") or "",
            offerer=raw.get("offerer", ""),
            token_address=raw.get("tokenAddress") or raw.get("nftContract", ""),
            token_id=token_id,
            price=price,
            currency=raw.get("currency", "ETH"),
            quantity=_coerce_int(raw.get("quantity", 1)),
            remaining_amount=remaining,
            start_date=_coerce_int(raw["startDate"]) if raw.get("startDate") else None,
            end_date=_coerce_int(raw["endDate"]) if raw.get("endDate") else None,
            broker_id=raw.get("brokerId"),
            is_erc1155=remaining is not None,
        )


def _coerce_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("0x") or value.startswith("0X"):
            return int(value, 16)
        return int(value)
    return int(value)


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

class MedialaneIndexer:
    """
    Indexes active orders from the Medialane REST API.

    Implements idempotent restart: tracks `last_indexed_at` and re-fetches
    only orders updated since that timestamp.

    ERC-1155 partial fills: remainingAmount field is tracked per order.
    """

    DEFAULT_API_BASE = "https://api.medialane.io"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("MEDIALANE_API_KEY")
        if not self.api_key:
            raise ConfigurationError(
                "MEDIALANE_API_KEY is not set. "
                "Get a key from portal.medialane.io."
            )
        self.api_base = api_base or self.DEFAULT_API_BASE

        # Indexing state
        self.last_indexed_at: Optional[int] = None
        self.total_indexed: int = 0
        self.reorg_count: int = 0

    def _get(self, path: str) -> dict:
        """Authenticated GET to Medialane REST API."""
        url = f"{self.api_base}{path}"
        headers: dict[str, str] = {
            "x-api-key": self.api_key,
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500]
            raise Exception(f"Medialane API error {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise Exception(f"Medialane network error: {e.reason}") from e

    def index_orders(
        self,
        since_timestamp: Optional[int] = None,
        page: int = 1,
        limit: int = 100,
    ) -> list[IndexedOrder]:
        """
        Fetch active orders updated since `since_timestamp`.

        Pagination: fetches all pages up to `limit` per page.
        Returns deduplicated list (by order_hash).
        """
        since = since_timestamp or self.last_indexed_at or 0
        path = (
            f"/v1/orders"
            f"?status=ACTIVE"
            f"&sort=updated_at"
            f"&page={page}"
            f"&limit={limit}"
        )
        if since:
            path += f"&since={since}"

        resp = self._get(path)
        raw_orders = resp.get("data") or resp.get("orders") or []
        if isinstance(raw_orders, dict):
            raw_orders = raw_orders.get("data", [])

        orders = []
        seen: set[str] = set()
        for raw in raw_orders:
            order = IndexedOrder.from_rest_order(raw)
            if order.order_hash in seen:
                continue
            seen.add(order.order_hash)
            orders.append(order)

        # Track last indexed time
        if orders:
            self.last_indexed_at = max(
                o.indexed_at for o in orders
            )
            self.total_indexed += len(orders)

        return orders

    def index_orders_for_token(
        self,
        token_address: str,
        token_id: int,
    ) -> list[IndexedOrder]:
        """Fetch active orders for a specific token."""
        path = (
            f"/v1/orders"
            f"?status=ACTIVE"
            f"&token_address={token_address}"
            f"&token_id={token_id}"
        )
        resp = self._get(path)
        raw_orders = resp.get("data") or resp.get("orders") or []
        if isinstance(raw_orders, dict):
            raw_orders = raw_orders.get("data", [])
        return [IndexedOrder.from_rest_order(raw) for raw in raw_orders]

    def index_orders_by_user(
        self,
        address: str,
        include_inactive: bool = False,
    ) -> list[IndexedOrder]:
        """Fetch all orders for a user (listings + offers)."""
        path = f"/v1/orders?address={address}"
        if not include_inactive:
            path += "&status=ACTIVE"
        resp = self._get(path)
        raw_orders = resp.get("data") or resp.get("orders") or []
        if isinstance(raw_orders, dict):
            raw_orders = raw_orders.get("data", [])
        return [IndexedOrder.from_rest_order(raw) for raw in raw_orders]

    def get_erc1155_remaining_amount(self, order_hash: str) -> Optional[int]:
        """Fetch remaining amount for a specific ERC-1155 order."""
        path = f"/v1/orders/{order_hash}"
        try:
            resp = self._get(path)
        except Exception:
            return None
        raw = resp.get("data") or resp
        remaining = raw.get("remainingAmount")
        if remaining is None:
            return None
        return _coerce_int(remaining)

    def index_all_active(self, max_pages: int = 10) -> list[IndexedOrder]:
        """Index all active orders across multiple pages."""
        all_orders: list[IndexedOrder] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            orders = self.index_orders(page=page)
            if not orders:
                break
            for order in orders:
                if order.order_hash not in seen:
                    seen.add(order.order_hash)
                    all_orders.append(order)
        return all_orders

    @property
    def state(self) -> dict:
        """Return current indexer state for persistence."""
        return {
            "last_indexed_at": self.last_indexed_at,
            "total_indexed": self.total_indexed,
            "reorg_count": self.reorg_count,
        }
