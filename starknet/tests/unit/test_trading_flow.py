# starknet/tests/unit/test_trading_flow.py
"""
Tests for the trading flow orchestration layer.
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from starknet.execution.trading_flow import (
    TradingContext,
    PortfolioView,
    ListingResult,
    FulfillmentResult,
    CancellationResult,
    SUPPORTED_CURRENCIES,
    create_trading_context,
    connect_wallet,
    get_portfolio,
    get_listings_for_token,
    create_listing,
    fulfill_listing,
    cancel_listing,
)


class TestTradingContext:
    def test_create_trading_context_sepolia(self):
        """Context creation with explicit RPC URL."""
        with patch("starknet.execution.trading_flow.StarknetRPCClient") as mock_rpc:
            mock_rpc.return_value = MagicMock()
            ctx = create_trading_context(
                network="sepolia",
                rpc_url="https://example-rpc.io/rpc",
            )
            assert ctx.network == "sepolia"
            assert ctx.rpc_url == "https://example-rpc.io/rpc"
            assert ctx.medialane is not None
            assert ctx.ark is not None
            assert ctx.stale_detector is not None
            assert ctx.replay_detector is not None

    def test_create_trading_context_default_rpc(self):
        """Default RPC is used when not specified."""
        with patch("starknet.execution.trading_flow.StarknetRPCClient") as mock_rpc:
            mock_rpc.return_value = MagicMock()
            ctx = create_trading_context(network="sepolia")
            assert "starknet" in ctx.rpc_url or "blastapi" in ctx.rpc_url or "infura" in ctx.rpc_url


class TestSupportedCurrencies:
    def test_eth_addresses_exist(self):
        """ETH address is defined for sepolia."""
        assert "ETH" in SUPPORTED_CURRENCIES
        assert "sepolia" in SUPPORTED_CURRENCIES["ETH"]
        addr = SUPPORTED_CURRENCIES["ETH"]["sepolia"]
        assert addr.startswith("0x")
        assert len(addr) == 66

    def test_strk_addresses_exist(self):
        """STRK address is defined for sepolia."""
        assert "STRK" in SUPPORTED_CURRENCIES
        assert "sepolia" in SUPPORTED_CURRENCIES["STRK"]
        addr = SUPPORTED_CURRENCIES["STRK"]["sepolia"]
        assert addr.startswith("0x")
        assert len(addr) == 66

    def test_usdc_addresses_exist(self):
        """USDC address is defined for sepolia."""
        assert "USDC" in SUPPORTED_CURRENCIES
        assert "sepolia" in SUPPORTED_CURRENCIES["USDC"]


class TestConnectWallet:
    @pytest.mark.asyncio
    async def test_connect_wallet_local_account(self):
        """Local account adapter connects and canonicalizes address."""
        ctx = create_trading_context(rpc_url="https://example.io/rpc")
        mock_adapter = MagicMock()
        mock_conn = MagicMock()
        mock_conn.address = "0x" + "0" * 62 + "1"  # 65 chars total → normalized to 64 hex (padded with leading zeros)
        mock_adapter.connect.return_value = mock_conn
        mock_adapter.execute_calls.return_value = "0xabcdef"

        with patch("starknet.execution.trading_flow.LocalAccountAdapter", return_value=mock_adapter):
            addr = await connect_wallet(
                ctx,
                wallet_type="local",
                private_key="0x" + "00" * 31 + "01",
                account_address="0x" + "0" * 62 + "1",
            )

        assert addr == "0x" + "0" * 63 + "1"  # 64 hex digits after 0x prefix
        assert ctx.wallet is mock_adapter

    @pytest.mark.asyncio
    async def test_connect_wallet_not_connected(self):
        """Must connect before using wallet-dependent functions."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        with pytest.raises(RuntimeError, match="Wallet not connected"):
            await get_portfolio(ctx)


class TestGetPortfolio:
    @pytest.mark.asyncio
    async def test_get_portfolio_empty(self):
        """Empty portfolio when user has no tokens."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        mock_adapter = MagicMock()
        mock_adapter.get_owned_tokens.return_value = []
        ctx.medialane = mock_adapter
        ctx.wallet_address = "0x" + "0" * 62 + "abc"

        result = await get_portfolio(ctx)
        assert isinstance(result, PortfolioView)
        assert result.wallet_address == ctx.wallet_address
        assert result.tokens == []

    @pytest.mark.asyncio
    async def test_get_portfolio_with_tokens(self):
        """Portfolio returns owned tokens from Medialane."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        mock_token = MagicMock()
        mock_token.contract_address = "0x" + "ab" * 32
        mock_token.token_id = 42
        mock_adapter = MagicMock()
        mock_adapter.get_owned_tokens.return_value = [mock_token]
        ctx.medialane = mock_adapter
        ctx.wallet_address = "0x" + "0" * 62 + "abc"

        result = await get_portfolio(ctx)
        assert len(result.tokens) == 1
        assert result.tokens[0].token_id == 42


class TestGetListingsForToken:
    @pytest.mark.asyncio
    async def test_get_listings_filters_stale(self):
        """Expired listings are filtered out."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        stale_order = MagicMock()
        stale_order.end_date = int(time.time()) - 3600  # 1 hour ago
        fresh_order = MagicMock()
        fresh_order.end_date = int(time.time()) + 86400  # 1 day from now

        mock_adapter = MagicMock()
        mock_adapter.get_active_orders_for_token.return_value = [stale_order, fresh_order]
        ctx.medialane = mock_adapter

        result = await get_listings_for_token(ctx, "0x" + "ab" * 32, 1)
        assert fresh_order in result
        assert stale_order not in result


class TestCreateListing:
    @pytest.mark.asyncio
    async def test_create_listing_requires_signature(self):
        """Create listing returns typed data when requiresSignature=True."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        mock_adapter = MagicMock()
        mock_intent = MagicMock()
        mock_intent.requires_signature = True
        mock_intent.typed_data = {"types": {"EIP712Domain": []}, "primaryType": "Order"}
        mock_intent.executable_calls = None
        mock_adapter.create_listing_intent.return_value = mock_intent
        ctx.medialane = mock_adapter
        ctx.wallet_address = "0x" + "0" * 62 + "abc"
        ctx.rpc = None  # Bypass ownership check — test intent flow only

        result = await create_listing(
            ctx,
            nft_contract="0x" + "ab" * 32,
            token_id=1,
            price=1000000000000000000,
        )
        assert result.success is True
        assert result.requires_signature is True
        assert result.typed_data is not None

    @pytest.mark.asyncio
    async def test_create_listing_no_signature_executes_directly(self):
        """Create listing executes calls directly when requiresSignature=False."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        mock_adapter = MagicMock()
        mock_intent = MagicMock()
        mock_intent.requires_signature = False
        mock_intent.executable_calls = [
            {"contractAddress": "0x" + "ab" * 32, "entrypoint": "approve", "calldata": [1]}
        ]
        mock_adapter.create_listing_intent.return_value = mock_intent
        ctx.medialane = mock_adapter
        ctx.wallet_address = "0x" + "0" * 62 + "abc"
        ctx.rpc = None  # Bypass ownership check

        mock_wallet = MagicMock()
        mock_wallet.execute_calls.return_value = "0xtxhash"
        ctx.wallet = mock_wallet

        result = await create_listing(ctx, "0x" + "ab" * 32, 1, 1000000000000000000)
        assert result.success is True
        assert result.requires_signature is False
        assert result.transaction_hash == "0xtxhash"

    @pytest.mark.asyncio
    async def test_create_listing_no_wallet_raises(self):
        """Create listing without wallet raises RuntimeError when trying to execute."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        ctx.wallet_address = "0x" + "0" * 62 + "abc"
        ctx.wallet = None
        ctx.rpc = None
        mock_adapter = MagicMock()
        mock_intent = MagicMock()
        mock_intent.requires_signature = False
        mock_intent.executable_calls = [{"contractAddress": "0x" + "ab" * 32, "entrypoint": "approve", "calldata": [1]}]
        mock_adapter.create_listing_intent.return_value = mock_intent
        ctx.medialane = mock_adapter

        result = await create_listing(ctx, "0x" + "ab" * 32, 1, 1000000000000000000)
        assert result.success is False
        assert "no wallet" in (result.error or "").lower()


class TestFulfillListing:
    @pytest.mark.asyncio
    async def test_fulfill_listing_replay_protection(self):
        """Cannot fulfill the same order twice (replay protection)."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        ctx.wallet_address = "0x" + "0" * 62 + "abc"
        ctx.replay_detector.mark_used("order123", ctx.wallet_address)

        result = await fulfill_listing(ctx, "order123", "0x" + "ab" * 32, 1)
        assert result.success is False
        assert "replay" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_fulfill_listing_not_found(self):
        """Fulfill fails gracefully when order not found."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        ctx.wallet_address = "0x" + "0" * 62 + "abc"
        mock_adapter = MagicMock()
        mock_adapter.get_active_orders_for_token.return_value = []
        ctx.medialane = mock_adapter

        result = await fulfill_listing(ctx, "nonexistent", "0x" + "ab" * 32, 1)
        assert result.success is False
        assert "not found" in (result.error or "").lower()


class TestCancelListing:
    @pytest.mark.asyncio
    async def test_cancel_unauthorized(self):
        """Non-offerer cannot cancel a listing."""
        ctx = TradingContext(network="sepolia", rpc_url="https://example.io/rpc")
        ctx.wallet_address = "0x" + "0" * 62 + "abc"  # not the offerer
        mock_adapter = MagicMock()
        mock_order = MagicMock()
        mock_order.offerer = "0x" + "0" * 62 + "xyz"  # different address
        mock_order.order_hash = "order123"  # must match the order_hash arg
        mock_adapter.get_active_orders_for_token.return_value = [mock_order]
        ctx.medialane = mock_adapter

        result = await cancel_listing(ctx, "order123", "0x" + "ab" * 32, 1)
        assert result.success is False
        assert "unauthorized" in (result.error or "").lower() or "valid" in (result.error or "").lower()


class TestResultTypes:
    def test_listing_result_dataclass(self):
        r = ListingResult(success=True, order_hash="0xabc", transaction_hash="0xdef")
        assert r.success is True
        assert r.order_hash == "0xabc"
        assert r.transaction_hash == "0xdef"
        assert r.requires_signature is False
        assert r.error is None

    def test_fulfillment_result_dataclass(self):
        r = FulfillmentResult(success=True, transaction_hash="0xtx")
        assert r.success is True
        assert r.transaction_hash == "0xtx"

    def test_cancellation_result_dataclass(self):
        r = CancellationResult(success=False, error="Not authorized")
        assert r.success is False
        assert r.error == "Not authorized"
