# starknet/execution/trading_flow.py
"""
Full trading flow orchestration for the OpenSea × Starknet integration.

Implements the complete user journey:
  wallet connect
    → user address
    → NFT portfolio visible
    → Medialane listings visible
    → select owned NFT
    → create listing intent
    → sign in wallet
    → execute transaction
    → listing visible
    → second wallet can fulfill
    → NFT ownership/order state updates

Architecture:
  MedialaneAdapter (REST) ← → MedialaneBackend (portal.medialane.io)
  ArkAdapter (on-chain) ← → ArkExecutor (Starknet L3)
  WalletAdapter ← → Starknet wallet (browser extension / backend account)

Prerequisites:
  - MEDIALANE_API_KEY from portal.medialane.io/account
  - STARKNET_RPC_URL (default: Infura Sepolia)
  - Wallet: either browser wallet (SNIP-12 signing) or STARKNET_ACCOUNT_ADDRESS+PRIVATE_KEY
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

from starknet.standards.interfaces import normalize_felt_address
from starknet.rpc.client import StarknetRPCClient
from starknet.venues.medialane.adapter import (
    MedialaneAdapter,
    ActiveOrder,
    OwnedToken,
    ListingIntentResult,
    FulfillIntentResult,
    CancelIntentResult,
    VenueAdapterError,
    ConfigurationError,
)
from starknet.venues.ark.adapter import ArkAdapter
from starknet.wallets.adapter import WalletAdapter, LocalAccountAdapter, get_wallet, Call
from starknet.security.venue_security import (
    StaleListingDetector,
    NonceReplayDetector,
    CancellationSecurity,
    OwnershipValidator,
    ApprovalRaceGuard,
)
from starknet.normalization.order_validator import OrderValidator, ValidationResult


# ---------------------------------------------------------------------------
# Currency constants (CONFIRMED from Medialane SDK getListableTokens)
# ---------------------------------------------------------------------------

SUPPORTED_CURRENCIES = {
    "ETH": {
        "mainnet": "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7",
        "sepolia": "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7",
    },
    "STRK": {
        "mainnet": "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
        "sepolia": "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",  # fixed: was 0x04718f...729f8a58... (wrong suffix)
    },
    "USDC": {
        "mainnet": "0x053c91253bc9682c04929ca02ed00b3e423f4d0f37a2bee9d647e2a4a5eb0d",
        "sepolia": "0x02cdac70c94447189af0389dfea63f4d5e4154ea8a563de288a5ab1c39e37843",
    },
}


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class TradingContext:
    """
    Immutable context for a trading session.

    All addresses are stored in canonical form (0x + 64 hex digits).
    """
    network: str = "sepolia"
    wallet_address: str = ""
    rpc_url: str = ""
    rpc: Optional[StarknetRPCClient] = None
    medialane: Optional[MedialaneAdapter] = None
    ark: Optional[ArkAdapter] = None
    wallet: Optional[WalletAdapter] = None
    stale_detector: StaleListingDetector = field(default_factory=StaleListingDetector)
    replay_detector: NonceReplayDetector = field(default_factory=NonceReplayDetector)
    cancellation_security: CancellationSecurity = field(default_factory=CancellationSecurity)
    ownership_validator: OwnershipValidator = field(default_factory=OwnershipValidator)
    approval_guard: ApprovalRaceGuard = field(default_factory=ApprovalRaceGuard)


@dataclass
class PortfolioView:
    """Portfolio of NFTs owned by a wallet."""
    wallet_address: str
    tokens: list[OwnedToken]
    venues: list[str] = field(default_factory=lambda: ["medialane"])


@dataclass
class ListingResult:
    """Result of creating and executing a listing."""
    success: bool
    order_hash: Optional[str] = None
    transaction_hash: Optional[str] = None
    requires_signature: bool = False
    typed_data: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class FulfillmentResult:
    """Result of fulfilling a listing."""
    success: bool
    transaction_hash: Optional[str] = None
    all_hashes: Optional[list[str]] = None
    requires_signature: bool = False
    error: Optional[str] = None


@dataclass
class CancellationResult:
    """Result of cancelling a listing."""
    success: bool
    transaction_hash: Optional[str] = None
    all_hashes: Optional[list[str]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Trading flow factory
# ---------------------------------------------------------------------------

def create_trading_context(
    network: str = "sepolia",
    rpc_url: Optional[str] = None,
    wallet_type: str = "local",
) -> TradingContext:
    """
    Create a fully wired TradingContext for the given network.

    Raises ConfigurationError if required credentials are absent.
    """
    # Resolve RPC URL
    if not rpc_url:
        if network == "sepolia":
            rpc_url = os.environ.get(
                "STARKNET_RPC_URL",
                "https://starknet-sepolia.public.blastapi.io",
            )
        else:
            rpc_url = os.environ.get(
                "STARKNET_RPC_URL",
                "https://starknet-mainnet.public.blastapi.io/rpc/v0_6",
            )

    rpc = StarknetRPCClient(rpc_url)

    # Medialane adapter
    medialane = MedialaneAdapter(network=network)

    # Ark adapter (on-chain only, requires starknet.js Account for signing)
    ark = ArkAdapter(network=network, rpc_url=rpc_url)

    return TradingContext(
        network=network,
        rpc_url=rpc_url,
        rpc=rpc,
        medialane=medialane,
        ark=ark,
    )


# ---------------------------------------------------------------------------
# Step 1: Wallet connection
# ---------------------------------------------------------------------------

async def connect_wallet(
    ctx: TradingContext,
    wallet_type: str = "local",
    private_key: Optional[str] = None,
    account_address: Optional[str] = None,
) -> str:
    """
    Connect a wallet and populate ctx.wallet_address.

    For local backend accounts: provide private_key + account_address.
    For browser wallets: use get_wallet("braavos") etc. in the frontend.

    Returns the connected wallet address in canonical form.
    """
    if wallet_type == "local":
        adapter = LocalAccountAdapter(
            private_key=private_key or os.environ.get("STARKNET_PRIVATE_KEY"),
            account_address=account_address or os.environ.get("STARKNET_ACCOUNT_ADDRESS"),
            rpc_url=ctx.rpc_url,
        )
        conn = adapter.connect()
    else:
        adapter = get_wallet(wallet_type)
        conn = adapter.connect()

    canonical = normalize_felt_address(conn.address)
    ctx.wallet_address = canonical
    ctx.wallet = adapter
    return canonical


# ---------------------------------------------------------------------------
# Step 2: Portfolio — what NFTs does the user own?
# ---------------------------------------------------------------------------

async def get_portfolio(ctx: TradingContext) -> PortfolioView:
    """
    Fetch all NFTs owned by the connected wallet.

    Uses Medialane REST API: GET /v1/tokens/{owner_address}

    Raises:
      RuntimeError if wallet not connected.
      ConfigurationError if MEDIALANE_API_KEY is not set.
    """
    if not ctx.wallet_address:
        raise RuntimeError("Wallet not connected. Call connect_wallet first.")

    if ctx.medialane is None:
        raise RuntimeError("Medialane adapter not initialized.")

    tokens = ctx.medialane.get_owned_tokens(ctx.wallet_address)
    return PortfolioView(
        wallet_address=ctx.wallet_address,
        tokens=tokens,
    )


# ---------------------------------------------------------------------------
# Step 3: Active listings for a token
# ---------------------------------------------------------------------------

async def get_listings_for_token(
    ctx: TradingContext,
    nft_contract: str,
    token_id: int,
) -> list[ActiveOrder]:
    """
    Get active (open) listings for a specific NFT.

    Checks staleness (expired listings filtered out).
    """
    if ctx.medialane is None:
        raise RuntimeError("Medialane adapter not initialized.")
    orders = ctx.medialane.get_active_orders_for_token(
        normalize_felt_address(nft_contract),
        token_id,
    )

    # Filter stale orders
    now = int(time.time())
    fresh = []
    for order in orders:
        if order.end_date and ctx.stale_detector.check_stale(order.end_date, now).is_stale:
            continue  # Skip expired listings
        fresh.append(order)

    return fresh


# ---------------------------------------------------------------------------
# Step 4: Create a listing
# ---------------------------------------------------------------------------

async def create_listing(
    ctx: TradingContext,
    nft_contract: str,
    token_id: int,
    price: int,
    currency: str = "ETH",
    end_time: Optional[int] = None,
) -> ListingResult:
    """
    Create a listing intent for an NFT.

    Flow:
      1. Validate ownership (current owner == wallet_address) at block
      2. POST /v1/intents/listing
      3. If requiresSignature=True: return typed_data for client to sign
      4. Client signs SNIP-12, submits via submit_signature()
      5. Returns executable calls → execute via wallet

    Raises:
      RuntimeError if wallet not connected.
      VenueAdapterError if API call fails.
    """
    if not ctx.wallet_address:
        raise RuntimeError("Wallet not connected.")

    if not end_time:
        end_time = int(time.time()) + 30 * 24 * 3600  # 30 days

    # Step 1: Validate ownership at latest block
    if ctx.rpc:
        ownership_result = ctx.ownership_validator.validate_ownership(
            nft_contract=normalize_felt_address(nft_contract),
            token_id=token_id,
            expected_owner=ctx.wallet_address,
            rpc_client=ctx.rpc,
            block_id="latest",
        )
        if ownership_result.result.value != "OWNER_MATCH":
            return ListingResult(
                success=False,
                error=f"Ownership check failed: {ownership_result.result.value}. "
                      f"Current owner: {ownership_result.current_owner}",
            )

    if ctx.medialane is None:
        raise RuntimeError("Medialane adapter not initialized.")

    # Step 2: Create listing intent
    try:
        intent = ctx.medialane.create_listing_intent(
            offerer=ctx.wallet_address,
            nft_contract=normalize_felt_address(nft_contract),
            token_id=token_id,
            price=price,
            currency=currency,
            end_time=end_time,
        )
    except ConfigurationError as e:
        return ListingResult(success=False, error=f"Configuration error: {e}")
    except VenueAdapterError as e:
        return ListingResult(success=False, error=f"API error: {e}")

    if intent.requires_signature:
        # Client must sign SNIP-12 typed data
        return ListingResult(
            success=True,
            requires_signature=True,
            typed_data=intent.typed_data,
            error=None,
        )
    else:
        # Calls returned directly — execute them
        if not ctx.wallet:
            return ListingResult(
                success=False,
                error="No wallet configured for execution. "
                      "Connect a wallet to execute calls.",
            )
        try:
            from starknet.wallets.adapter import Call
            tx_hashes = []
            for call_dict in intent.executable_calls or []:
                call = Call(
                    contract_address=call_dict["contractAddress"],
                    entrypoint=call_dict["entrypoint"],
                    calldata=[str(x) for x in call_dict.get("calldata", [])],
                )
                tx_hash = ctx.wallet.execute_calls([call])
                tx_hashes.append(tx_hash)

            return ListingResult(
                success=True,
                transaction_hash=tx_hashes[0] if tx_hashes else None,
                requires_signature=False,
            )
        except Exception as e:
            return ListingResult(success=False, error=f"Execution failed: {e}")


async def submit_listing_signature(
    ctx: TradingContext,
    intent_id: str,
    signature: list[str],
    submit_url: str,
) -> ListingResult:
    """
    Submit a SNIP-12 signature for a pending listing intent.

    Returns the result of submitting the signature (executable calls or confirmation).
    """
    if not ctx.wallet:
        return ListingResult(success=False, error="No wallet configured.")

    try:
        if ctx.medialane is None:
            raise RuntimeError("Medialane adapter not initialized.")
        result = ctx.medialane.submit_signature(submit_url, signature)
        calls = result.get("calls", [])
        if not calls:
            return ListingResult(success=True, order_hash=intent_id)

        tx_hashes = []
        for call_dict in calls:
            call = Call(
                contract_address=call_dict["contractAddress"],
                entrypoint=call_dict["entrypoint"],
                calldata=[str(x) for x in call_dict.get("calldata", [])],
            )
            tx_hash = ctx.wallet.execute_calls([call])
            tx_hashes.append(tx_hash)

        return ListingResult(
            success=True,
            order_hash=intent_id,
            transaction_hash=tx_hashes[0] if tx_hashes else None,
        )
    except Exception as e:
        return ListingResult(success=False, error=f"Signature submission failed: {e}")


# ---------------------------------------------------------------------------
# Step 5: Fulfill a listing
# ---------------------------------------------------------------------------

async def fulfill_listing(
    ctx: TradingContext,
    order_hash: str,
    nft_contract: str,
    token_id: int,
    amount: int = 1,
) -> FulfillmentResult:
    """
    Fulfill (buy) an active listing.

    Flow (CONFIRMED: requiresSignature=False for fulfill):
      1. Validate order not stale, not already fulfilled (nonce replay)
      2. Validate ownership of seller's NFT at latest block
      3. POST /v1/intents/fulfill
      4. Execute returned calls (approve ERC-20 + transfer)
      5. Mark order_hash as used in replay detector

    Note: Fulfiller does NOT sign the order (buyer=fulfiller).
    """
    if not ctx.wallet_address:
        raise RuntimeError("Wallet not connected.")

    # Step 1: Check stale / replay
    if ctx.replay_detector.is_replay(order_hash, ctx.wallet_address):
        return FulfillmentResult(success=False, error="Order already fulfilled (replay)")

    # Step 2: Fetch order details to get seller info
    try:
        if ctx.medialane is None:
            raise RuntimeError("Medialane adapter not initialized.")
        orders = ctx.medialane.get_active_orders_for_token(nft_contract, token_id)
        order = next((o for o in orders if o.order_hash == order_hash), None)
        if not order:
            return FulfillmentResult(success=False, error=f"Order {order_hash} not found or not active")
    except Exception as e:
        return FulfillmentResult(success=False, error=f"Failed to fetch order: {e}")

    # Step 3: Validate ownership at latest block
    if ctx.rpc:
        ownership_result = ctx.ownership_validator.validate_ownership(
            nft_contract=normalize_felt_address(nft_contract),
            token_id=token_id,
            expected_owner=order.offerer,
            rpc_client=ctx.rpc,
            block_id="latest",
        )
        if ownership_result.result.value != "OWNER_MATCH":
            return FulfillmentResult(
                success=False,
                error=f"Seller no longer owns the NFT: {ownership_result.result.value}",
            )

    # Step 4: Create fulfill intent (requiresSignature=False)
    try:
        if ctx.medialane is None:
            raise RuntimeError("Medialane adapter not initialized.")
        intent = ctx.medialane.fulfill_listing_intent(
            fulfiller=ctx.wallet_address,
            order_hash=order_hash,
            amount=amount,
        )
    except ConfigurationError as e:
        return FulfillmentResult(success=False, error=f"Configuration error: {e}")
    except VenueAdapterError as e:
        return FulfillmentResult(success=False, error=f"API error: {e}")

    if not intent.executable_calls:
        return FulfillmentResult(success=False, error="No executable calls returned from fulfill intent")

    # Step 5: Execute calls
    if not ctx.wallet:
        return FulfillmentResult(
            success=False,
            error="No wallet configured for execution.",
        )

    try:
        from starknet.wallets.adapter import Call
        tx_hashes = []
        for call_dict in intent.executable_calls:
            call = Call(
                contract_address=call_dict["contractAddress"],
                entrypoint=call_dict["entrypoint"],
                calldata=[str(x) for x in call_dict.get("calldata", [])],
            )
            tx_hash = ctx.wallet.execute_calls([call])
            tx_hashes.append(tx_hash)

        # Mark as fulfilled (replay protection)
        ctx.replay_detector.mark_used(order_hash, ctx.wallet_address)

        return FulfillmentResult(success=True, transaction_hash=tx_hash, all_hashes=tx_hashes)
    except Exception as e:
        return FulfillmentResult(success=False, error=f"Execution failed: {e}")


# ---------------------------------------------------------------------------
# Step 6: Cancel a listing
# ---------------------------------------------------------------------------

async def cancel_listing(
    ctx: TradingContext,
    order_hash: str,
    nft_contract: str,
    token_id: int,
) -> CancellationResult:
    """
    Cancel a listing.

    Flow (CONFIRMED: requiresSignature=True for cancel):
      1. Validate canceller == offerer
      2. POST /v1/intents/cancel
      3. Sign SNIP-12 cancellation intent
      4. Submit signature
      5. Execute returned calls

    The seller (offerer) must be the one cancelling.
    """
    if not ctx.wallet_address:
        raise RuntimeError("Wallet not connected.")

    # Step 1: Validate cancellation authority
    try:
        if ctx.medialane is None:
            raise RuntimeError("Medialane adapter not initialized.")
        orders = ctx.medialane.get_active_orders_for_token(nft_contract, token_id)
        order = next((o for o in orders if o.order_hash == order_hash), None)
    except Exception as e:
        return CancellationResult(success=False, error=f"Failed to fetch order: {e}")

    if not order:
        return CancellationResult(success=False, error=f"Order {order_hash} not found")

    validation = ctx.cancellation_security.validate_cancel_authority(
        canceller=ctx.wallet_address,
        order_offerer=order.offerer,
        order_hash=order_hash,
    )
    if not validation.valid:
        return CancellationResult(success=False, error=f"Unauthorized: {validation.reason}")

    # Step 2: Create cancel intent
    try:
        if ctx.medialane is None:
            raise RuntimeError("Medialane adapter not initialized.")
        intent = ctx.medialane.cancel_listing_intent(
            seller=ctx.wallet_address,
            order_hash=order_hash,
            token_address=normalize_felt_address(nft_contract),
            token_id=token_id,
        )
    except Exception as e:
        return CancellationResult(success=False, error=f"API error: {e}")

    if not intent.requires_signature:
        # No signing needed, execute directly
        if ctx.wallet:
            try:
                from starknet.wallets.adapter import Call
                tx_hashes = []
                for call_dict in intent.executable_calls or []:
                    call = Call(
                        contract_address=call_dict["contractAddress"],
                        entrypoint=call_dict["entrypoint"],
                        calldata=[str(x) for x in call_dict.get("calldata", [])],
                    )
                    tx_hash = ctx.wallet.execute_calls([call])
                    tx_hashes.append(tx_hash)
                return CancellationResult(success=True, transaction_hash=tx_hash, all_hashes=tx_hashes)
            except Exception as e:
                return CancellationResult(success=False, error=f"Execution failed: {e}")
        else:
            return CancellationResult(success=False, error="No wallet configured")

    # Step 3: Return typed data for signing
    # Client must sign, then call submit_cancel_signature()
    return CancellationResult(success=False, error="Cancellation requires SNIP-12 signature. Use submit_cancel_signature().")


async def submit_cancel_signature(
    ctx: TradingContext,
    intent_id: str,
    signature: list[str],
    submit_url: str,
    order_hash: str,
) -> CancellationResult:
    """
    Submit a SNIP-12 signature for a pending cancel intent.
    """
    if not ctx.wallet:
        return CancellationResult(success=False, error="No wallet configured.")

    try:
        if ctx.medialane is None:
            raise RuntimeError("Medialane adapter not initialized.")
        result = ctx.medialane.submit_signature(submit_url, signature)
        calls = result.get("calls", [])
        if not calls:
            return CancellationResult(success=True)

        for call_dict in calls:
            call = Call(
                contract_address=call_dict["contractAddress"],
                entrypoint=call_dict["entrypoint"],
                calldata=[str(x) for x in call_dict.get("calldata", [])],
            )
            tx_hash = ctx.wallet.execute_calls([call])

        return CancellationResult(success=True, transaction_hash=tx_hash)
    except Exception as e:
        return CancellationResult(success=False, error=f"Cancel submission failed: {e}")
