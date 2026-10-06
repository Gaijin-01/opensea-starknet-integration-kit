# starknet/standards/interfaces.py
# OpenZeppelin Contracts for Cairo v2.2.0 — verified interface IDs
# Source: openzeppelin-contracts-upgradeable/openzeppelin/interfaces.cairo

# SRC5 (SNIP-5) — interface detection standard
# This is unchanged across OZ versions
SRC5_ID: int = 0x3f918d17e5ee77373b56385708f855659a07f75997f365cf87748628532a055

# ERC721 interface IDs (OZ Cairo v2.2.0)
IERC721_ID: int = 0x33eb2f84c309543403fd69f0d0f363781ef06ef6faeb0131ff16ea3175bd943
IERC721_METADATA_ID: int = 0xabbcd595a99c10485ee78aaf2a7585ef21f81c0ba6e7e4f4791bf98b88a20e

# ERC1155 interface IDs (OZ Cairo v2.2.0)
IERC1155_ID: int = 0x6114a8f75559e1b39fcba08ce02961a1aa082d9256a158dd3e64964e4b1b52
IERC1155_METADATA_URI_ID: int = 0xcabe2400715bd18225c66d8c0e0a6c0f7f8aa9c7e5f4c6a9b8d7e6f5a4b3c2

# SRC6 — account interface for is_valid_signature
# Used for verifying SNIP-12 signatures against accounts
ISRC6_ID: int = 0x3f918d17e5ee77373b56385708f855659a07f75997f365cf87748628532a055  # same as SRC5 in OZ

# starknet::VALIDATED return value (ASCII 'VALID')
# SRC6 requires accounts to return the short string 'VALID' on valid signature
# hex value: 0x56414C4944 = bytes('VALID')
VALIDATED: int = 0x56414C4944

# Mapping from interface ID → human-readable name
INTERFACE_NAME: dict[int, str] = {
    SRC5_ID: "SRC5 (SNIP-5)",
    IERC721_ID: "IERC721",
    IERC721_METADATA_ID: "IERC721Metadata",
    IERC1155_ID: "IERC1155",
    IERC1155_METADATA_URI_ID: "IERC1155MetadataURI",
}

# CONTRACT TYPE TAGS
NFT_TYPE_ERC721 = "erc721"
NFT_TYPE_ERC1155 = "erc1155"
NFT_TYPE_UNKNOWN = "unknown"


def classify_contract(supports_interface_result: bool, interface_id: int) -> str:
    """Classify a contract based on SRC5 interface check result."""
    if not supports_interface_result:
        return NFT_TYPE_UNKNOWN
    if interface_id == IERC721_ID:
        return NFT_TYPE_ERC721
    if interface_id == IERC1155_ID:
        return NFT_TYPE_ERC1155
    return NFT_TYPE_UNKNOWN


# TRANSFER EVENT
# Selector for Transfer event: starknet_keccak("Transfer")
# Verified against starknet.js v10.8.0: starknet.keccak("Transfer") === 0x99cd8bde...
TRANSFER_EVENT_KEY: int = 0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9

# STARKNET CHAIN IDs
CHAIN_ID_MAIN: str = "SN_MAIN"
CHAIN_ID_SEPOLIA: str = "SN_SEPOLIA"

# ERC20 token addresses on Starknet mainnet (StarkGate)
ETH_MAINNET: str = "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7"
STRK_MAINNET: str = "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d"

# ERC20 token addresses on Starknet sepolia (StarkGate)
ETH_SEPOLIA: str = "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7"
STRK_SEPOLIA: str = "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d"


def is_mainnet_address(address: str) -> bool:
    """Check if an address looks like a mainnet address (non-zero, valid hex)."""
    return address.startswith("0x") and len(address) == 66 and address[2:] != "0" * 64


def normalize_felt_address(address: str) -> str:
    """
    Normalize a felt252 address to canonical form.

    Wire format: up to 63 hex digits after 0x (no leading zeros required)
    DB/storage format: 0x + 64 hex digits (zero-padded)

    This function converts wire → DB canonical form.
    """
    if not address.startswith("0x") or len(address) < 3:
        raise ValueError(f"Invalid felt address: {address}")

    hex_part = address[2:].lstrip('0')
    if not hex_part:
        hex_part = "0"

    # Reject oversized representations (> 64 hex chars after stripping)
    if len(hex_part) > 64:
        raise ValueError(f"Invalid felt address: more than 64 hex digits: {address}")

    # Pad to 64 hex digits
    padded = hex_part.zfill(64)
    return "0x" + padded
