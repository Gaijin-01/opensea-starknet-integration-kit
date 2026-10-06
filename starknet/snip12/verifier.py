# starknet/snip12/verifier.py
"""
SNIP-12 typed structured data signing and verification for Starknet.

KEY IMPLEMENTATION RULES:

1. SIGNER IS NOT DERIVED FROM SIGNATURE
   On Starknet, account can use Stark curve, secp256k1, multisig, passkey/P256,
   or custom validation. There is NO account-type-agnostic way to recover the
   signer from a signature. The signer ContractAddress must be provided
   SEPARATELY (from wallet connection, from the order offerer field, etc.).

2. VERIFICATION PATH
   The ONLY correct verification path is:
   starknet_call → signer.is_valid_signature(message_hash, signature)
   Returns starknet::VALIDATED (0x56414C4944 = ASCII 'VALID') on success.

3. REVISION HASHING
   - Revision 0: Pedersen array hash for domain/message encoding
   - Revision 1: Poseidon array hash for domain/message encoding
   - type_hash ALWAYS uses starknet_keccak(encode_type(...)) regardless of revision

4. DOMAIN revision FIELD
   Must be INTEGER 1, not string "1" (SNIP-12 special rule).

5. starknet::VALIDATED
   Value: 0x56414C4944 = bytes('VALID'). NOT 0x539.

ATTESTATION STATUS:
  - SNIP-12 revision 1 Poseidon domain hash: IMPLEMENTATION_ASSUMPTION
    (requires starknet.js or OZ Cairo reference to cross-validate exact output)
  - starknet_keccak for type_hash: IMPLEMENTATION_ASSUMPTION
    (requires live starknet node to compute)
  - Signature verification via is_valid_signature: IMPLEMENTATION_ASSUMPTION
    (requires deployed account contracts to test)
"""

from dataclasses import dataclass
from typing import Any


# starknet::VALIDATED — what ISRC6 account returns on valid signature
# ASCII 'VALID' = 0x56414C4944
VALIDATED: int = 0x56414C4944


@dataclass
class SNIP12Domain:
    """SNIP-12 domain separator."""
    name: str        # e.g. "Medialane"
    version: str     # e.g. "1"
    chain_id: str    # e.g. "SN_MAIN" or "SN_SEPOLIA"
    revision: int    # MUST BE INTEGER, not string. 1 is current standard.

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "chainId": self.chain_id,
            "revision": self.revision,  # Integer, NOT string — SNIP-12 rule
        }

    def revision_is_poseidon(self) -> bool:
        """Revision 1 uses Poseidon for array hash; revision 0 uses Pedersen."""
        return self.revision == 1


@dataclass
class SNIP12Message:
    """Base SNIP-12 message struct. Subclass for venue-specific structs."""
    pass


class SNIP12Verifier:
    """
    SNIP-12 signature verifier.

    Does NOT attempt to derive signer from signature.
    Does NOT hardcode Poseidon/Pedersen implementation (delegates to caller).
    """

    def __init__(self, rpc_client):
        """
        Args:
            rpc_client: StarknetRPCClient instance for making is_valid_signature calls
        """
        self.rpc = rpc_client

    def verify_signature(
        self,
        signer_address: str,
        message_hash: str,
        signature: list[str],
    ) -> tuple[bool, str]:
        """
        Verify a SNIP-12 signature via on-chain is_valid_signature call.

        Args:
            signer_address: ContractAddress of the signer (MUST be known — not derived from sig)
            message_hash: Hex string of the SNIP-12 message hash
            signature: List of felt252 values as hex strings

        Returns:
            (is_valid: bool, reason: str)
        """
        if not signer_address or not signer_address.startswith("0x"):
            return False, "Invalid signer address"

        if not message_hash or not message_hash.startswith("0x"):
            return False, "Invalid message hash"

        # The only correct verification path: call the account's is_valid_signature
        # ISRC6 selector: starknet_keccak("is_valid_signature")
        # = 0x3f918d17e5ee77373b56385708f855659a07f75997f365cf87748628532a055 (same as SRC5)
        selector = "0x3f918d17e5ee77373b56385708f855659a07f75997f365cf87748628532a055"

        # NOTE: is_valid_signature expects (message_hash: felt, signature: felt*) calldata.
        # The message_hash is passed as-is; the signature list is appended as individual elements.
        # If the account model requires Uint256 splitting of the hash, this would need adjustment.
        calldata = [message_hash, str(len(signature))] + signature

        try:
            result = self.rpc.call_contract(signer_address, selector, calldata)
        except Exception as e:
            return False, f"RPC call failed: {e}"

        # Parse return_data
        # Starknet RPC return_data contains hex strings (e.g. "0x56414C4944")
        # Parse as hex int; fall back to direct int for raw int values
        if not result or "return_data" not in result:
            return False, "No return_data from is_valid_signature"

        return_data = result["return_data"]
        if not return_data:
            return False, "Empty return_data"

        # Valid signature returns starknet::VALIDATED = 0x56414C4944
        try:
            raw_val = return_data[0]
            if isinstance(raw_val, str):
                returned = int(raw_val, 16)  # Parse hex string from RPC
            else:
                returned = int(raw_val)
            if returned == VALIDATED:
                return True, ""
            else:
                return False, f"Account returned {hex(returned)}, expected {hex(VALIDATED)}"
        except (ValueError, IndexError) as e:
            return False, f"Failed to parse return_data: {e}"

    def verify_domain_match(
        self,
        provided_domain: SNIP12Domain,
        expected_chain_id: str,
        expected_name: str,
    ) -> bool:
        """
        Verify the domain matches expected chain and name.

        Note: This only checks structural fields. Full domain hash verification
        requires recomputing the domain hash with the correct Poseidon/Pedersen
        implementation (not implemented here — delegated to caller with proper
        hash library).
        """
        if provided_domain.chain_id != expected_chain_id:
            return False
        if provided_domain.name != expected_name:
            return False
        if provided_domain.revision not in (0, 1):
            return False
        return True


class SNIP12Encoder:
    """
    SNIP-12 struct encoder helpers.

    ATTESTATION: This module provides structure only.
    Actual Poseidon/Pedersen hashing requires a proper starknet.js or
    OZ Cairo reference implementation. This encoder documents the
    expected structure without providing runtime hash computation.
    """

    @staticmethod
    def encode_struct(struct_name: str, fields: list[tuple[str, str]]) -> str:
        """
        Return the canonical type string for a SNIP-12 struct.

        Example: "Listing(offerer:ContractAddress, token:ContractAddress, token_id:u256, ...)"

        The type_hash is then: starknet_keccak(this_string)

        Note: starknet_keccak is DIFFERENT from Ethereum's keccak256.
        """
        field_strs = [f"{name}:{type_}" for name, type_ in fields]
        return f"{struct_name}({', '.join(field_strs)})"

    @staticmethod
    def listing_struct_type() -> str:
        """Return the canonical type string for a Medialane Listing struct."""
        return SNIP12Encoder.encode_struct("Listing", [
            ("offerer", "ContractAddress"),
            ("token", "ContractAddress"),
            ("token_id", "u256"),
            ("quantity", "u256"),
            ("price", "u256"),
            ("currency", "ContractAddress"),
            ("expiry", "u128"),
            ("nonce", "felt"),
        ])
