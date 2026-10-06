# starknet/tests/unit/test_medialane_client.py
from starknet.venues.medialane.client import MedialaneClient, MedialaneOrder, VENUE_ID


class TestMedialaneClientUnit:
    def test_client_init_with_urls(self):
        client = MedialaneClient(
            api_base_url="https://api.medialane.io",
            rpc_url="https://starknet-mainnet.example.com",
        )
        assert client.api_base_url == "https://api.medialane.io"
        assert client.rpc_url == "https://starknet-mainnet.example.com"

    def test_client_init_defaults(self):
        client = MedialaneClient()
        assert client.api_base_url is None
        assert client.rpc_url is None


class TestMedialaneOrderNormalization:
    def test_normalize_erc721_order(self):
        raw = {
            "order_hash": "0xabc123",
            "offerer": "0x061a6c9c6f7e1c4d3e2b5a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1900",
            "token": "0x007b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a",
            "token_id": {"low": "42", "high": "0"},
            "quantity": {"low": "1", "high": "0"},
            "price": {"low": "1000000000000000000", "high": "0"},
            "currency": "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7",
            "expiry": "1735689600",
            "nonce": "42",
        }
        client = MedialaneClient()
        order = client.normalize_from_api_response(raw)

        assert order.venue == VENUE_ID
        assert order.token_id == 42
        assert order.quantity == 1
        assert order.price == 10**18
        assert order.expiry == 1735689600
        assert order.nonce == 42
        assert order.is_erc1155 is False
        assert order.offerer == raw["offerer"]
        assert order.token == raw["token"]

    def test_normalize_erc1155_order_with_remaining_amount(self):
        """ERC1155 orders support partial fills — remainingAmount is tracked."""
        raw = {
            "order_hash": "0xdef456",
            "offerer": "0x061a6c9c6f7e1c4d3e2b5a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1900",
            "token": "0x007b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a",
            "token_id": {"low": "7", "high": "0"},
            "quantity": {"low": "100", "high": "0"},  # 100 tokens listed
            "remaining_amount": "75",  # 25 already filled
            "price": {"low": "500000000000000000", "high": "0"},
            "currency": "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7",
            "expiry": "1735689600",
            "nonce": "99",
            "is_erc1155": True,
        }
        client = MedialaneClient()
        order = client.normalize_from_api_response(raw)

        assert order.is_erc1155 is True
        assert order.quantity == 100
        assert order.remaining_amount == 75
        assert order.token_id == 7

    def test_parse_u256_large(self):
        """u256 values above 2^128 use both limbs."""
        raw = {
            "order_hash": "0xtest",
            "offerer": "0x1",
            "token": "0x1",
            "token_id": {"low": "0", "high": "1"},  # high=1 means 2^128
            "quantity": 1,
            "price": 1,
            "expiry": 0,
            "nonce": 0,
        }
        client = MedialaneClient()
        order = client.normalize_from_api_response(raw)
        assert order.token_id == 2**128


class TestMedialaneBlockedExternal:
    def test_fetch_active_orders_raises_blocked(self):
        client = MedialaneClient()
        try:
            client.fetch_active_orders()
            assert False, "Should have raised NotImplementedError"
        except NotImplementedError as e:
            assert "BLOCKED_EXTERNAL" in str(e)

    def test_get_order_details_raises_blocked(self):
        client = MedialaneClient()
        try:
            client.get_order_details("0xabc")
            assert False, "Should have raised NotImplementedError"
        except NotImplementedError as e:
            assert "BLOCKED_EXTERNAL" in str(e)

    def test_blocked_external_is_correctly_classified(self):
        """
        We classify the live Medialane read path as BLOCKED_EXTERNAL
        because: no live credentials, no running backend, no deployed contracts.
        This is CORRECT classification, not a test failure.
        """
        client = MedialaneClient()
        try:
            client.fetch_active_orders()
            assert False, "Should have raised NotImplementedError"
        except NotImplementedError as e:
            assert "BLOCKED_EXTERNAL" in str(e)
