# starknet/tests/unit/test_discovery.py
from starknet.indexer.discovery import ContractDiscovery, DiscoveredContract
from starknet.standards.interfaces import (
    NFT_TYPE_ERC721, NFT_TYPE_ERC1155, NFT_TYPE_UNKNOWN,
)


# Constants from OZ Cairo v2.2.0 (same as in interfaces.py)
SRC5_ID = 0x3f918d17e5ee77373b56385708f855659a07f75997f365cf87748628532a055
IERC721_ID = 0x33eb2f84c309543403fd69f0d0f363781ef06ef6faeb0131ff16ea3175bd943
IERC1155_ID = 0x6114a8f75559e1b39fcba08ce02961a1aa082d9256a158dd3e64964e4b1b52


class MockRPC:
    """Minimal mock RPC client for unit testing."""

    def __init__(self, responses: dict):
        # responses: dict of (address_lower, interface_id) -> bool
        self._responses = responses
        self.calls = []

    def supports_interface(self, address: str, interface_id: int) -> bool:
        self.calls.append(("supports_interface", address.lower(), interface_id))
        return self._responses.get((address.lower(), interface_id), False)

    def call_contract(self, address: str, selector: str, calldata=None):
        self.calls.append(("call_contract", address.lower(), selector))
        return {"return_data": []}


class TestContractDiscoveryInvariants:
    """
    Tests that enforce the CRITICAL INVARIANTS of contract discovery:

    INVARIANT 1: NFT contract = EVENT EMITTER, NOT from/to
      The Transfer event is emitted BY the NFT contract.
      The event's `address` field = the NFT contract address.
      from/to = account addresses (wallets).

    INVARIANT 2: Never call supports_interface on wallet addresses.
    """

    def test_nft_contract_is_event_emitter(self):
        """
        The NFT contract is identified by the event's address field,
        NOT the from/to fields.
        """
        mock = MockRPC({})
        discovery = ContractDiscovery(mock)

        nft_contract = "0x007b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        result = discovery.discover_from_event_emitter(nft_contract)

        # First call was to the NFT contract address
        assert result is not None
        assert mock.calls[0][1] == nft_contract.lower()

    def test_wallet_address_classified_as_unknown(self):
        """
        Wallet addresses (from/to of Transfer) should NOT be passed
        to supports_interface as NFT candidates.

        When a wallet IS passed (as a test), it should be classified as unknown.
        This proves we don't assume all addresses are NFT contracts.
        """
        wallet_addr = "0x061a6c9c6f7e1c4d3e2b5a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1900"
        mock = MockRPC({})
        discovery = ContractDiscovery(mock)

        result = discovery.discover_from_event_emitter(wallet_addr)

        assert result.nft_type == NFT_TYPE_UNKNOWN
        assert result.supports_src5 is False

    def test_discovery_via_enum_is_explicit(self):
        """
        Each discovery path (event_emitter, registry, venue_api, known_list)
        must be called explicitly on the right address type.
        There is no auto-discovery from from/to fields.
        """
        mock = MockRPC({})
        discovery = ContractDiscovery(mock)

        # Via registry (fresh address)
        result1 = discovery.discover_from_registry(
            "0x007b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        )
        assert result1.discovered_via == "registry"

        # Via venue_api (different address to bypass cache)
        result2 = discovery.discover_from_venue_api(
            "0x008b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        )
        assert result2.discovered_via == "venue_api"


class TestContractClassificationFlow:
    """Test the full SRC5 → ERC721 → ERC1155 classification pipeline."""

    def test_erc721_contract_classified_correctly(self):
        erc721_addr = "0x007b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        mock = MockRPC({
            (erc721_addr, SRC5_ID): True,
            (erc721_addr, IERC721_ID): True,
        })
        discovery = ContractDiscovery(mock)
        result = discovery.discover_from_event_emitter(erc721_addr)

        assert result.nft_type == NFT_TYPE_ERC721
        assert result.supports_src5 is True
        assert result.discovered_via == "event_emitter"

    def test_erc1155_contract_classified_correctly(self):
        erc1155_addr = "0x008b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        mock = MockRPC({
            (erc1155_addr, SRC5_ID): True,
            (erc1155_addr, IERC1155_ID): True,
        })
        discovery = ContractDiscovery(mock)
        result = discovery.discover_from_event_emitter(erc1155_addr)

        assert result.nft_type == NFT_TYPE_ERC1155
        assert result.supports_src5 is True

    def test_non_nft_contract_classified_unknown(self):
        unknown_addr = "0x009b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        mock = MockRPC({
            (unknown_addr, SRC5_ID): False,
        })
        discovery = ContractDiscovery(mock)
        result = discovery.discover_from_event_emitter(unknown_addr)

        assert result.nft_type == NFT_TYPE_UNKNOWN
        assert result.supports_src5 is False

    def test_src5_without_721_or_1155_is_unknown(self):
        """A contract may support SRC5 but not be an NFT contract."""
        other_addr = "0x00ab42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        mock = MockRPC({
            (other_addr, SRC5_ID): True,
            (other_addr, IERC721_ID): False,
            (other_addr, IERC1155_ID): False,
        })
        discovery = ContractDiscovery(mock)
        result = discovery.discover_from_event_emitter(other_addr)

        assert result.nft_type == NFT_TYPE_UNKNOWN
        assert result.supports_src5 is True  # Has SRC5 but not NFT


class TestDeduplicationCache:
    """Each address is checked at most once regardless of discovery path."""

    def test_same_address_checked_once(self):
        addr = "0x007b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        mock = MockRPC({
            (addr, SRC5_ID): True,
            (addr, IERC721_ID): True,
        })
        discovery = ContractDiscovery(mock)

        # Multiple discovery calls for the same address
        discovery.discover_from_event_emitter(addr)
        discovery.discover_from_event_emitter(addr)
        discovery.discover_from_venue_api(addr)

        support_calls = [c for c in mock.calls if c[0] == "supports_interface"]
        assert len(support_calls) == 2  # SRC5 + ERC721 only

    def test_address_normalized_to_lowercase_for_cache(self):
        """Cache key is lowercase, so mixed-case addresses are deduplicated."""
        addr = "0x007b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        mock = MockRPC({
            (addr.lower(), SRC5_ID): True,
            (addr.lower(), IERC721_ID): True,
        })
        discovery = ContractDiscovery(mock)

        discovery.discover_from_event_emitter(addr.upper())
        discovery.discover_from_event_emitter(addr.lower())

        support_calls = [c for c in mock.calls if c[0] == "supports_interface"]
        assert len(support_calls) == 2


class TestInvalidInput:
    def test_invalid_address_rejected(self):
        mock = MockRPC({})
        discovery = ContractDiscovery(mock)

        assert discovery.discover_from_event_emitter("not-an-address") is None
        assert discovery.discover_from_event_emitter("") is None
        assert discovery.discover_from_event_emitter("0x") is None
