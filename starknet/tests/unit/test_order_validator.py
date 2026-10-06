# starknet/tests/unit/test_order_validator.py
from starknet.normalization.order_validator import (
    OrderValidator,
    ValidationResult,
    ValidationFailure,
    check_expiry,
    check_chain_id_match,
    check_venue_match,
)


class TestValidationResult:
    def test_valid_result(self):
        r = ValidationResult(is_executable=True, failures=[])
        assert r.is_valid is True
        assert bool(r) is True

    def test_invalid_result_has_failures(self):
        r = ValidationResult(is_executable=False, failures=[ValidationFailure.ORDER_EXPIRED])
        assert r.is_valid is False
        assert bool(r) is False
        assert ValidationFailure.ORDER_EXPIRED in r.failures

    def test_multiple_failures(self):
        r = ValidationResult(is_executable=False, failures=[
            ValidationFailure.SIGNATURE_INVALID,
            ValidationFailure.SELLER_NOT_OWNER,
        ])
        assert len(r.failures) == 2
        assert ValidationFailure.SIGNATURE_INVALID in r.failures
        assert ValidationFailure.SELLER_NOT_OWNER in r.failures


class TestCheckExpiry:
    def test_not_expired(self):
        assert check_expiry(expiry_timestamp=1735689600, current_time=1735689500) is True

    def test_expired(self):
        assert check_expiry(expiry_timestamp=1735689600, current_time=1735689600) is False
        assert check_expiry(expiry_timestamp=1735689600, current_time=1735689700) is False

    def test_expired_edge_case(self):
        # Expires at exactly current_time
        assert check_expiry(expiry_timestamp=100, current_time=100) is False


class TestCheckChainIdMatch:
    def test_match(self):
        assert check_chain_id_match("SN_MAIN", "SN_MAIN") is True
        assert check_chain_id_match("SN_SEPOLIA", "SN_SEPOLIA") is True

    def test_mismatch(self):
        assert check_chain_id_match("SN_MAIN", "SN_SEPOLIA") is False
        assert check_chain_id_match("SN_SEPOLIA", "SN_MAIN") is False


class TestCheckVenueMatch:
    def test_match(self):
        assert check_venue_match("medialane", "medialane") is True

    def test_mismatch(self):
        assert check_venue_match("medialane", "ark") is False


class TestOrderValidatorBlockedExternal:
    """Ownership and approval checks require live chain state."""

    def test_ownership_check_blocked(self):
        class MockRPC:
            pass

        class MockVerifier:
            pass

        validator = OrderValidator(MockRPC(), MockVerifier())
        try:
            class FakeOrder:
                offerer = "0x1"
                token = "0x2"
                token_id = 1
                is_erc1155 = False
            validator._check_ownership(FakeOrder())
            assert False, "Should raise NotImplementedError"
        except NotImplementedError as e:
            assert "BLOCKED_EXTERNAL" in str(e)

    def test_approval_check_blocked(self):
        class MockRPC:
            pass

        class MockVerifier:
            pass

        validator = OrderValidator(MockRPC(), MockVerifier())
        try:
            class FakeOrder:
                offerer = "0x1"
                token = "0x2"
                token_id = 1
                is_erc1155 = False
            validator._check_approval(FakeOrder())
            assert False, "Should raise NotImplementedError"
        except NotImplementedError as e:
            assert "BLOCKED_EXTERNAL" in str(e)


class TestValidationFailureEnum:
    """All failure types are present and unique."""
    def test_all_failure_types_present(self):
        failures = list(ValidationFailure)
        assert ValidationFailure.SIGNATURE_INVALID in failures
        assert ValidationFailure.SELLER_NOT_OWNER in failures
        assert ValidationFailure.ORDER_EXPIRED in failures
        assert ValidationFailure.NONCE_REPLAY in failures
        assert ValidationFailure.ERC1155_INSUFFICIENT_BALANCE in failures

    def test_failure_messages_unique(self):
        messages = [f.value for f in ValidationFailure]
        assert len(messages) == len(set(messages))
