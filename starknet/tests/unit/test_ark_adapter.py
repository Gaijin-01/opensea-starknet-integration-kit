# starknet/tests/unit/test_ark_adapter.py
"""Unit tests for ArkAdapter — tests address normalization and calldata construction."""

import pytest
from starknet.venues.ark.adapter import (
    ArkAdapter,
    ARK_CONTRACTS,
    build_approve_nft_call,
    build_approve_erc20_call,
    build_fulfill_order_call,
    build_cancel_order_call,
    ArkRouteType,
    ArkOrderStatus,
    compute_order_hash,
)


class TestArkContracts:
    """Test that Ark contract addresses are correct."""

    def test_sepolia_executor_address(self):
        # CONFIRMED from github.com/ArkProjectNFTs/ark-project/contracts.json
        addr = ARK_CONTRACTS["sepolia"]["executor"]
        # Raw hex: 62 chars → 0x + 62 = 64 total
        assert len(addr) == 64
        assert addr.startswith("0x")
        assert addr == "0xb86ab357c15c12fb78f9b0a19fa974c730fcbab96f17881827dde871665f0b"

    def test_mainnet_executor_address(self):
        addr = ARK_CONTRACTS["mainnet"]["executor"]
        assert len(addr) == 64
        assert addr == "0x7b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"

    def test_sepolia_orderbook_address(self):
        addr = ARK_CONTRACTS["sepolia"]["orderbook"]
        assert addr == "0x795b605fa3144afd6f11a4499f71b9cf373bcba3f1b2835d51f65ab59392261"

    def test_route_type_erc721_to_erc20(self):
        assert ArkRouteType.ERC721_TO_ERC20 == 1


class TestArkAdapterInit:
    """Test ArkAdapter initialization."""

    def test_default_network_sepolia(self):
        adapter = ArkAdapter(network="sepolia")
        assert adapter.network == "sepolia"
        assert adapter.get_executor_address() == "0xb86ab357c15c12fb78f9b0a19fa974c730fcbab96f17881827dde871665f0b"

    def test_unknown_network_raises(self):
        with pytest.raises(ValueError):
            ArkAdapter(network="unknown")


class TestArkCalldataBuilders:
    """Test Ark calldata construction matching confirmed source code."""

    def test_build_approve_nft_call(self):
        # Explicit 66-char full felt252 addresses (0x + 64 hex digits)
        full_nft = "0x" + "0" * 62 + "ab"   # 66 chars: 0x + 62 zeros + ab
        full_executor = "0x" + "0" * 62 + "bc"
        call = build_approve_nft_call(
            nft_contract=full_nft,
            token_id=42,
            executor_address=full_executor,
        )
        assert call["contractAddress"] == full_nft
        assert call["entrypoint"] == "approve"
        assert full_executor in call["calldata"]

    def test_build_approve_erc20_call(self):
        full_usdc = "0x" + "0" * 62 + "11"
        full_executor = "0x" + "0" * 62 + "bc"
        call = build_approve_erc20_call(
            currency_contract=full_usdc,
            amount=500000,
            executor_address=full_executor,
        )
        assert call["contractAddress"] == full_usdc
        assert call["entrypoint"] == "approve"
        assert full_executor in call["calldata"]

    def test_build_fulfill_order_call(self):
        call = build_fulfill_order_call(
            order_hash="0xHASH123",
            fulfiller="0xBUYER",
            token_address="0xTOKEN",
            token_id=42,
            broker_id="0xBROKER",
            chain_id="0x534e5f5345504f4c4941",
            executor_address="0xEXECUTOR",
        )
        assert call["entrypoint"] == "fulfill_order"
        assert "fulfill_info" in call["calldata"]

    def test_build_cancel_order_call(self):
        call = build_cancel_order_call(
            order_hash="0xHASH456",
            token_address="0xTOKEN",
            token_id=99,
            executor_address="0xEXECUTOR",
        )
        assert call["entrypoint"] == "cancel_order"
        assert "cancel_info" in call["calldata"]


class TestArkOrderStatus:
    """Test ArkOrderStatus enum."""

    def test_active_status(self):
        assert ArkOrderStatus.ACTIVE.value == 2

    def test_fulfilled_status(self):
        assert ArkOrderStatus.FULFILLED.value == 3

    def test_cancelled_status(self):
        assert ArkOrderStatus.CANCELLED.value == 4


class TestArkAdapterListingBuilder:
    """Test OrderV1 construction."""

    def test_build_listing_v1_defaults(self):
        adapter = ArkAdapter(network="sepolia")
        # Use full 66-char addresses
        full_offerer = "0x" + "00" * 31 + "aa"
        full_token = "0x" + "00" * 31 + "bb"
        full_broker = "0x" + "00" * 31 + "cc"
        order = adapter.build_listing_v1(
            offerer=full_offerer,
            token_address=full_token,
            token_id=42,
            start_amount=500000,
            broker_id=full_broker,
        )
        assert order["route"] == ArkRouteType.ERC721_TO_ERC20
        assert order["offerer"] == full_offerer
        assert order["quantity"] == "1"
        assert order["endAmount"] == "0"
        assert "startDate" in order
        assert "endDate" in order
        assert order["currencyChainId"] == "0x534e5f5345504f4c4941"  # SN_SEPOLIA

    def test_build_fulfill_info(self):
        adapter = ArkAdapter(network="sepolia")
        full_buyer = "0x" + "00" * 31 + "dd"
        full_token = "0x" + "00" * 31 + "bb"
        full_broker = "0x" + "00" * 31 + "cc"
        fulfill_info = adapter.build_fulfill_info(
            order_hash="0xHASH",
            fulfiller=full_buyer,
            token_address=full_token,
            token_id=42,
            broker_id=full_broker,
        )
        assert fulfill_info["orderHash"] == "0xHASH"
        assert fulfill_info["fulfiller"] == full_buyer
        assert fulfill_info["tokenChainId"] == "0x534e5f5345504f4c4941"
