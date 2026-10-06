# starknet/indexer/discovery.py
"""
Starknet NFT contract discovery.

CRITICAL DESIGN INVARIANTS:

1. NFT CONTRACT = EVENT EMITTER, NOT from/to
   The Transfer event is emitted BY the NFT contract.
   The event's `address` field = the NFT contract address.
   The event's `from` and `to` fields = account addresses (wallets).

   INCORRECT: iterate from/to fields, call supports_interface on them
   CORRECT:   use the event's address field as the NFT contract candidate

2. NO starknet_getContractAddresses RPC METHOD EXISTS
   There is no RPC method to enumerate all contracts.
   Discovery must use event emitters, registries, and venue APIs.

3. CONTRACT CLASSIFICATION FLOW
   For each candidate contract address:
   a. Call supports_interface(SRC5_ID)
      → if false: skip (not SRC5-compliant)
   b. Call supports_interface(IERC721_ID)
      → if true: mark as ERC721
   c. Call supports_interface(IERC1155_ID)
      → if true: mark as ERC1155
   d. Fetch name(), symbol(), token_uri() as available

ATTESTATION STATUS:
  - Event emitter = NFT contract: IMPLEMENTATION_ASSUMPTION based on OZ Cairo source
  - from/to = account addresses: IMPLEMENTATION_ASSUMPTION based on OZ Cairo source
  - Discovery from event emitters: IMPLEMENTATION_ASSUMPTION
  - SRC5 detection flow: IMPLEMENTATION_ASSUMPTION
"""

from dataclasses import dataclass

from starknet.standards.interfaces import (
    SRC5_ID,
    IERC721_ID,
    IERC1155_ID,
    NFT_TYPE_ERC721,
    NFT_TYPE_ERC1155,
    NFT_TYPE_UNKNOWN,
)


@dataclass
class DiscoveredContract:
    address: str          # Normalized felt252 address
    nft_type: str         # NFT_TYPE_ERC721, NFT_TYPE_ERC1155, or NFT_TYPE_UNKNOWN
    supports_src5: bool   # Passed SRC5 check
    name: str | None = None
    symbol: str | None = None
    discovered_via: str = ""  # "event_emitter", "registry", "venue_api", "known_list"


class ContractDiscovery:
    """
    Discovers and classifies Starknet NFT contracts.

    Thread-safe for concurrent indexer workers (via external locking if needed).
    """

    def __init__(self, rpc_client):
        self.rpc = rpc_client
        # Cache of already-processed contract addresses
        self._checked: dict[str, DiscoveredContract] = {}

    def discover_from_event_emitter(self, event_address: str) -> DiscoveredContract | None:
        """
        Process an event's address field as a candidate NFT contract.

        CRITICAL: The event's `address` field is the NFT contract that EMITTED
        the event. This is NOT the same as `from` or `to` fields.

        Example:
            Transfer(event_address=0xNFTContract, from=0xSeller, to=0xBuyer)
            → candidate = 0xNFTContract (the contract)
            → NOT 0xSeller or 0xBuyer (those are wallets)
        """
        return self._discover_and_classify(event_address, "event_emitter")

    def discover_from_registry(self, contract_address: str) -> DiscoveredContract | None:
        """
        Process an address from a collection registry (e.g. Medialane Collection Registry).
        """
        return self._discover_and_classify(contract_address, "registry")

    def discover_from_venue_api(self, contract_address: str) -> DiscoveredContract | None:
        """
        Process an address returned by a venue REST API (e.g. Ark Project, Medialane).
        """
        return self._discover_and_classify(contract_address, "venue_api")

    def discover_from_known_list(self, contract_address: str) -> DiscoveredContract | None:
        """
        Process an address from a known list of NFT contracts.
        """
        return self._discover_and_classify(contract_address, "known_list")

    def _discover_and_classify(
        self,
        contract_address: str,
        discovered_via: str,
    ) -> DiscoveredContract | None:
        """
        Core discovery + classification pipeline.

        Does NOT call supports_interface on wallets.
        Does NOT call supports_interface on already-checked addresses.
        """
        if not contract_address or not contract_address.startswith("0x") or len(contract_address) < 4:
            return None

        # Normalize address
        addr = contract_address.lower()

        # Skip if already processed
        if addr in self._checked:
            return self._checked[addr]

        # Step 1: Check SRC5 support
        supports_src5 = self._check_supports_interface(contract_address, SRC5_ID)
        if not supports_src5:
            # Not a recognized contract — cache as unknown
            result = DiscoveredContract(
                address=contract_address,
                nft_type=NFT_TYPE_UNKNOWN,
                supports_src5=False,
                discovered_via=discovered_via,
            )
            self._checked[addr] = result
            return result

        # Step 2: Check ERC721
        supports_erc721 = self._check_supports_interface(contract_address, IERC721_ID)
        if supports_erc721:
            name, symbol = self._fetch_name_symbol(contract_address)
            result = DiscoveredContract(
                address=contract_address,
                nft_type=NFT_TYPE_ERC721,
                supports_src5=True,
                name=name,
                symbol=symbol,
                discovered_via=discovered_via,
            )
            self._checked[addr] = result
            return result

        # Step 3: Check ERC1155
        supports_erc1155 = self._check_supports_interface(contract_address, IERC1155_ID)
        if supports_erc1155:
            name, symbol = self._fetch_name_symbol(contract_address)
            result = DiscoveredContract(
                address=contract_address,
                nft_type=NFT_TYPE_ERC1155,
                supports_src5=True,
                name=name,
                symbol=symbol,
                discovered_via=discovered_via,
            )
            self._checked[addr] = result
            return result

        # SRC5 but not ERC721/ERC1155
        result = DiscoveredContract(
            address=contract_address,
            nft_type=NFT_TYPE_UNKNOWN,
            supports_src5=True,
            discovered_via=discovered_via,
        )
        self._checked[addr] = result
        return result

    def _check_supports_interface(self, address: str, interface_id: int) -> bool:
        """Make a single supports_interface call via RPC."""
        try:
            return self.rpc.supports_interface(address, interface_id)
        except Exception:
            return False

    def _fetch_name_symbol(self, address: str) -> tuple[str | None, str | None]:
        """Fetch name() and symbol() from a contract (best-effort)."""
        # name() selector
        name_selector = "0x361458367e696363fbcc70777d07ebbd2394e89fd0adcaf147faccd1d294d60"
        # symbol() selector
        symbol_selector = "0x216b05c387bab9ac31918a3e61672f4618601f3c598a2f3f2710f37053e1ea4"
        name, symbol = None, None
        try:
            result = self.rpc.call_contract(address, name_selector)
            if result and "return_data" in result and result["return_data"]:
                name = self._parse_short_string(result["return_data"])
        except Exception:
            pass
        try:
            result = self.rpc.call_contract(address, symbol_selector)
            if result and "return_data" in result and result["return_data"]:
                symbol = self._parse_short_string(result["return_data"])
        except Exception:
            pass
        return name, symbol

    @staticmethod
    def _parse_short_string(return_data: list) -> str | None:
        """Parse a short string from a starknet_call return_data array."""
        if not return_data:
            return None
        try:
            felt = int(return_data[0])
            if felt == 0:
                return ""
            # Convert felt to bytes (big-endian, stripping leading zeros)
            byte_len = (felt.bit_length() + 7) // 8 or 1
            return bytes.fromhex(felt.to_bytes(byte_len, "big").lstrip(b"\x00")).decode("ascii")
        except Exception:
            return None
