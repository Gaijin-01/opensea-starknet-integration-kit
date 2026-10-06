# starknet/tests/unit/test_interfaces.py
import pytest
from starknet.standards.interfaces import (
    SRC5_ID, IERC721_ID, IERC1155_ID,
    VALIDATED, normalize_felt_address, classify_contract,
    NFT_TYPE_ERC721, NFT_TYPE_ERC1155, NFT_TYPE_UNKNOWN,
    ETH_MAINNET, STRK_MAINNET, TRANSFER_EVENT_KEY,
)


class TestInterfaceIDs:
    def test_src5_id_not_zero(self):
        assert SRC5_ID == 0x3f918d17e5ee77373b56385708f855659a07f75997f365cf87748628532a055

    def test_ierc721_id_correct(self):
        # Correct value from OZ Cairo v2.2.0 (not the stale 0x89c8fc3d)
        assert IERC721_ID == 0x33eb2f84c309543403fd69f0d0f363781ef06ef6faeb0131ff16ea3175bd943

    def test_ierc1155_id_correct(self):
        # Correct value from OZ Cairo v2.2.0 (not the stale 0x8b9a7a9d)
        assert IERC1155_ID == 0x6114a8f75559e1b39fcba08ce02961a1aa082d9256a158dd3e64964e4b1b52

    def test_validated_is_ascii_valid(self):
        # VALIDATED = 0x56414C4944 = bytes('VALID') in ASCII
        assert VALIDATED == 0x56414C4944
        assert VALIDATED.to_bytes(5, 'big') == b'VALID'


class TestNormalizeFeltAddress:
    def test_wire_to_canonical(self):
        # Wire format: no leading zeros
        wire = "0x7b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        canonical = normalize_felt_address(wire)
        assert canonical == "0x007b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a"
        assert len(canonical) == 66  # 0x + 64 hex chars

    def test_zero_address(self):
        assert normalize_felt_address("0x0") == "0x" + "0" * 64
        assert normalize_felt_address("0x00") == "0x" + "0" * 64

    def test_invalid_address_rejected(self):
        with pytest.raises(ValueError):
            normalize_felt_address("invalid")
        with pytest.raises(ValueError):
            normalize_felt_address("0x")

    def test_strk_mainnet_correct_full_address(self):
        # STRK address ends with 'd', not truncated
        assert STRK_MAINNET == "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d"
        assert len(STRK_MAINNET) == 66


class TestClassifyContract:
    def test_erc721_classification(self):
        assert classify_contract(True, IERC721_ID) == NFT_TYPE_ERC721
        assert classify_contract(False, IERC721_ID) == NFT_TYPE_UNKNOWN

    def test_erc1155_classification(self):
        assert classify_contract(True, IERC1155_ID) == NFT_TYPE_ERC1155

    def test_unknown_if_false(self):
        assert classify_contract(False, IERC721_ID) == NFT_TYPE_UNKNOWN

    def test_unknown_if_different_id(self):
        assert classify_contract(True, SRC5_ID) == NFT_TYPE_UNKNOWN


class TestTransferEventKey:
    def test_transfer_event_key_nonzero(self):
        assert TRANSFER_EVENT_KEY != 0
        assert TRANSFER_EVENT_KEY == 0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
