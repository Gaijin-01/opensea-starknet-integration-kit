# starknet/tests/unit/test_medialane_adapter.py
"""Unit tests for MedialaneAdapter — tests the adapter interface, address normalization, and intent flow."""

import pytest
from unittest.mock import patch, MagicMock
from starknet.venues.medialane.adapter import (
    MedialaneAdapter,
    VenueAdapter,
    ConfigurationError,
    ActiveOrder,
    ListingIntentResult,
    FulfillIntentResult,
    CancelIntentResult,
)


class TestMedialaneAdapterInterface:
    """Test the Medialane adapter conforms to VenueAdapter interface."""

    def test_adapter_has_required_methods(self):
        adapter = MedialaneAdapter()
        assert hasattr(adapter, "create_listing_intent")
        assert hasattr(adapter, "fulfill_listing_intent")
        assert hasattr(adapter, "cancel_listing_intent")
        assert hasattr(adapter, "get_active_orders_for_token")
        assert hasattr(adapter, "get_orders_by_user")
        assert hasattr(adapter, "get_owned_tokens")

    def test_adapter_stores_network(self):
        adapter = MedialaneAdapter(network="mainnet")
        assert adapter.network == "mainnet"


class TestMedialaneCreateListing:
    """Test create listing intent flow."""

    def test_raises_configuration_error_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            adapter = MedialaneAdapter()
            with pytest.raises(ConfigurationError) as exc_info:
                adapter.create_listing_intent(
                    offerer="0x123",
                    nft_contract="0x456",
                    token_id=1,
                    price=500000,
                    currency="USDC",
                    end_time=9999999999,
                )
            assert "MEDIALANE_API_KEY" in str(exc_info.value)

    @patch("starknet.venues.medialane.adapter._api_post")
    def test_create_listing_requires_signature_true(self, mock_post):
        """Create listing returns typed_data when requiresSignature=True."""
        mock_post.return_value = {
            "intentId": "intent_123",
            "requiresSignature": True,
            "typedData": {"domain": {}, "types": {}, "message": {}},
            "submitSignatureUrl": "/v1/intents/submit",
        }

        adapter = MedialaneAdapter()
        result = adapter.create_listing_intent(
            offerer="0xABC",
            nft_contract="0xDEF",
            token_id=42,
            price=500000,
            currency="USDC",
            end_time=9999999999,
        )

        assert isinstance(result, ListingIntentResult)
        assert result.requires_signature is True
        assert result.typed_data is not None
        assert result.signature_submit_url is not None
        assert result.intent_id == "intent_123"
        assert result.executable_calls is None

    @patch("starknet.venues.medialane.adapter._api_post")
    def test_create_listing_requires_signature_false(self, mock_post):
        """Create listing returns calls directly when requiresSignature=False."""
        mock_post.return_value = {
            "intentId": "intent_456",
            "requiresSignature": False,
            "calls": [{"contractAddress": "0xABC", "entrypoint": "transfer"}],
        }

        adapter = MedialaneAdapter()
        result = adapter.create_listing_intent(
            offerer="0xABC",
            nft_contract="0xDEF",
            token_id=42,
            price=500000,
            currency="USDC",
            end_time=9999999999,
        )

        assert result.requires_signature is False
        assert result.executable_calls is not None
        assert len(result.executable_calls) == 1


class TestMedialaneFulfill:
    """Test fulfill listing intent flow."""

    def test_raises_configuration_error_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            adapter = MedialaneAdapter()
            with pytest.raises(ConfigurationError):
                adapter.fulfill_listing_intent(
                    fulfiller="0x123",
                    order_hash="0xorderhash",
                    amount=1,
                )

    @patch("starknet.venues.medialane.adapter._api_post")
    def test_fulfill_returns_calls_directly(self, mock_post):
        """Fulfillment returns calls without signing (current Medialane protocol)."""
        mock_post.return_value = {
            "intentId": "intent_789",
            "requiresSignature": False,
            "calls": [{"contractAddress": "0xEXE", "entrypoint": "transfer"}],
        }

        adapter = MedialaneAdapter()
        result = adapter.fulfill_listing_intent(
            fulfiller="0xBUYER",
            order_hash="0xorderhash",
            amount=1,
        )

        assert result.requires_signature is False
        assert result.executable_calls is not None


class TestMedialaneCancel:
    """Test cancel listing intent flow."""

    @patch("starknet.venues.medialane.adapter._api_post")
    def test_cancel_requires_signature(self, mock_post):
        """Cancellation requires SNIP-12 signature per current Medialane protocol."""
        mock_post.return_value = {
            "intentId": "intent_cancel",
            "requiresSignature": True,
            "typedData": {"domain": {}, "types": {}, "message": {}},
            "submitSignatureUrl": "/v1/intents/submit",
        }

        adapter = MedialaneAdapter()
        result = adapter.cancel_listing_intent(
            seller="0xSELLER",
            order_hash="0xorderhash",
            token_address="0xTOKEN",
            token_id=42,
        )

        assert result.requires_signature is True
        assert result.typed_data is not None


class TestMedialaneQuery:
    """Test query methods."""

    @patch("starknet.venues.medialane.adapter._api_get")
    def test_get_active_orders_parses_remaining_amount(self, mock_get):
        """ERC-1155 remainingAmount is parsed correctly."""
        mock_get.return_value = {
            "data": [
                {
                    "orderHash": "0xHASH",
                    "offerer": "0xOFFERER",
                    "tokenAddress": "0xTOKEN",
                    "tokenId": "42",
                    "price": "500000",
                    "currency": "USDC",
                    "quantity": "10",
                    "remainingAmount": "7",
                }
            ]
        }

        adapter = MedialaneAdapter()
        orders = adapter.get_active_orders_for_token("0xTOKEN", 42)

        assert len(orders) == 1
        assert orders[0].remaining_amount == 7
        assert orders[0].is_erc1155 is True

    @patch("starknet.venues.medialane.adapter._api_get")
    def test_get_active_orders_no_remaining(self, mock_get):
        """ERC-721 orders have no remainingAmount field."""
        mock_get.return_value = {
            "data": [
                {
                    "orderHash": "0xHASH2",
                    "offerer": "0xOFFERER",
                    "tokenAddress": "0xTOKEN",
                    "tokenId": "99",
                    "price": "1000000",
                    "currency": "ETH",
                }
            ]
        }

        adapter = MedialaneAdapter()
        orders = adapter.get_active_orders_for_token("0xTOKEN", 99)

        assert len(orders) == 1
        assert orders[0].remaining_amount is None
        assert orders[0].is_erc1155 is False

    @patch("starknet.venues.medialane.adapter._api_get")
    def test_get_owned_tokens(self, mock_get):
        """get_owned_tokens returns owned NFT tokens."""
        mock_get.return_value = {
            "data": [
                {"contract": "0xNFT1", "tokenId": "1", "name": "Token #1"},
                {"contract": "0xNFT2", "tokenId": "2", "name": "Token #2"},
            ]
        }

        adapter = MedialaneAdapter()
        tokens = adapter.get_owned_tokens("0xOWNER")

        assert len(tokens) == 2
        assert tokens[0].contract == "0xNFT1"
        assert tokens[1].token_id == 2
