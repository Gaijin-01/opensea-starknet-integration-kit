# starknet/tests/unit/test_snip12_verifier.py
from starknet.snip12.verifier import SNIP12Verifier, SNIP12Domain, SNIP12Encoder, VALIDATED


class TestVALIDATEDConstant:
    def test_validated_is_ascii_valid(self):
        assert VALIDATED == 0x56414C4944
        assert VALIDATED.to_bytes(5, 'big') == b'VALID'

    def test_validated_not_zero(self):
        assert VALIDATED != 0
        assert VALIDATED != 0x539  # The old wrong value


class TestSNIP12Domain:
    def test_revision_must_be_integer(self):
        domain = SNIP12Domain(
            name="Medialane",
            version="1",
            chain_id="SN_MAIN",
            revision=1,
        )
        assert domain.revision == 1
        assert isinstance(domain.revision, int)

    def test_to_dict_revision_is_not_string(self):
        """SNIP-12 rule: revision in domain JSON must be INTEGER 1, not string "1"."""
        domain = SNIP12Domain(name="Test", version="1", chain_id="SN_MAIN", revision=1)
        d = domain.to_dict()
        assert d["revision"] == 1
        assert not isinstance(d["revision"], str)

    def test_revision_is_poseidon(self):
        domain_r1 = SNIP12Domain(name="", version="", chain_id="", revision=1)
        domain_r0 = SNIP12Domain(name="", version="", chain_id="", revision=0)
        assert domain_r1.revision_is_poseidon() is True
        assert domain_r0.revision_is_poseidon() is False

    def test_revision_0_uses_pedersen(self):
        domain_r0 = SNIP12Domain(name="", version="", chain_id="", revision=0)
        assert domain_r0.revision_is_poseidon() is False

    def test_domain_to_dict_fields(self):
        domain = SNIP12Domain(name="Medialane", version="1", chain_id="SN_SEPOLIA", revision=1)
        d = domain.to_dict()
        assert d["name"] == "Medialane"
        assert d["version"] == "1"
        assert d["chainId"] == "SN_SEPOLIA"
        assert d["revision"] == 1


class TestSNIP12Encoder:
    def test_listing_struct_type_string(self):
        type_str = SNIP12Encoder.listing_struct_type()
        assert "Listing(" in type_str
        assert "offerer:ContractAddress" in type_str
        assert "token:ContractAddress" in type_str
        assert "token_id:u256" in type_str
        assert "quantity:u256" in type_str
        assert "price:u256" in type_str
        assert "currency:ContractAddress" in type_str
        assert "expiry:u128" in type_str
        assert "nonce:felt" in type_str

    def test_encode_struct(self):
        result = SNIP12Encoder.encode_struct(
            "Offer",
            [("offerer", "ContractAddress"), ("price", "u256")],
        )
        assert result == "Offer(offerer:ContractAddress, price:u256)"


class TestSNIP12VerifierSignaturePath:
    """Tests for the correct signature verification path (NO signer derivation)."""

    def test_verify_signature_has_signer_address_param(self):
        """verify_signature takes signer_address as explicit param — NOT derived from sig."""
        import inspect
        sig = inspect.signature(SNIP12Verifier.verify_signature)
        param_names = list(sig.parameters.keys())
        assert "signer_address" in param_names

    def test_verify_signature_rejects_empty_signer(self):
        class MockRPC:
            def call_contract(self, *args, **kwargs):
                return {"return_data": [hex(VALIDATED)]}

        verifier = SNIP12Verifier(MockRPC())
        is_valid, reason = verifier.verify_signature(
            signer_address="",
            message_hash="0x" + "ab" * 32,
            signature=["0x1", "0x2"],
        )
        assert is_valid is False
        assert "Invalid signer address" in reason

    def test_verify_signature_rejects_invalid_signer_format(self):
        class MockRPC:
            def call_contract(self, *args, **kwargs):
                return {"return_data": [hex(VALIDATED)]}

        verifier = SNIP12Verifier(MockRPC())
        is_valid, reason = verifier.verify_signature(
            signer_address="not-an-address",
            message_hash="0x" + "ab" * 32,
            signature=["0x1"],
        )
        assert is_valid is False

    def test_verify_signature_returns_validated_on_success(self):
        class MockRPC:
            def call_contract(self, *args, **kwargs):
                # is_valid_signature returns VALIDATED on success
                return {"return_data": [hex(VALIDATED)]}

        verifier = SNIP12Verifier(MockRPC())
        is_valid, reason = verifier.verify_signature(
            signer_address="0x061a6c9c6f7e1c4d3e2b5a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1900",
            message_hash="0x" + "ab" * 32,
            signature=["0x1", "0x2"],
        )
        assert is_valid is True
        assert reason == ""

    def test_verify_signature_rejects_wrong_return_value(self):
        class MockRPC:
            def call_contract(self, *args, **kwargs):
                # Account returns something other than VALIDATED
                return {"return_data": [hex(0xDEADBEEF)]}

        verifier = SNIP12Verifier(MockRPC())
        is_valid, reason = verifier.verify_signature(
            signer_address="0x061a6c9c6f7e1c4d3e2b5a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1900",
            message_hash="0x" + "ab" * 32,
            signature=["0x1"],
        )
        assert is_valid is False
        assert "expected" in reason.lower()
        assert hex(VALIDATED) in reason

    def test_verify_signature_handles_no_return_data(self):
        class MockRPC:
            def call_contract(self, *args, **kwargs):
                return {}  # No return_data

        verifier = SNIP12Verifier(MockRPC())
        is_valid, reason = verifier.verify_signature(
            signer_address="0x061a6c9c6f7e1c4d3e2b5a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1900",
            message_hash="0x" + "ab" * 32,
            signature=["0x1"],
        )
        assert is_valid is False
        assert "No return_data" in reason


class TestSNIP12VerifierDomainMatch:
    def test_domain_match_passes(self):
        domain = SNIP12Domain(name="Medialane", version="1", chain_id="SN_MAIN", revision=1)

        class MockRPC:
            pass

        verifier = SNIP12Verifier(MockRPC())
        assert verifier.verify_domain_match(domain, "SN_MAIN", "Medialane") is True

    def test_domain_rejects_wrong_chain(self):
        domain = SNIP12Domain(name="Medialane", version="1", chain_id="SN_MAIN", revision=1)

        class MockRPC:
            pass

        verifier = SNIP12Verifier(MockRPC())
        # Wrong chain
        assert verifier.verify_domain_match(domain, "SN_SEPOLIA", "Medialane") is False

    def test_domain_rejects_wrong_name(self):
        domain = SNIP12Domain(name="Medialane", version="1", chain_id="SN_MAIN", revision=1)

        class MockRPC:
            pass

        verifier = SNIP12Verifier(MockRPC())
        # Wrong name
        assert verifier.verify_domain_match(domain, "SN_MAIN", "ArkProject") is False

    def test_domain_rejects_invalid_revision(self):
        domain_bad = SNIP12Domain(name="", version="", chain_id="", revision=2)

        class MockRPC:
            pass

        verifier = SNIP12Verifier(MockRPC())
        assert verifier.verify_domain_match(domain_bad, "", "") is False
