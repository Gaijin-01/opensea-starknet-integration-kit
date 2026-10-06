# starknet/tests/unit/test_snip12_medialane.py
"""Unit tests for Medialane SNIP-12 domain and typed data builders."""

import pytest
from starknet.snip12.medialane_domain import (
    MedialaneSNIP12Domain,
    build_medialane_domain,
    to_starknet_domain,
    build_listing_typed_data,
    build_cancel_typed_data,
    build_offer_typed_data,
)


class TestMedialaneDomain:
    """Test SNIP-12 domain construction."""

    def test_domain_erc721_version_1(self):
        domain = build_medialane_domain(
            version=1,
            chain_id="0x534e5f5345504f4c4941",  # SN_SEPOLIA
            revision=1,
        )
        assert domain.name == "Medialane-1"
        assert domain.version == "1"
        assert domain.revision == 1

    def test_domain_erc1155_version_3(self):
        """ERC-1155 uses version 3 per confirmed Medialane SDK source."""
        domain = build_medialane_domain(
            version=3,
            chain_id="0x534e5f4d41494e",  # SN_MAIN
            revision=1,
        )
        assert domain.name == "Medialane-3"
        assert domain.version == "3"
        assert domain.revision == 1

    def test_domain_revision_0_pedersen(self):
        domain = build_medialane_domain(version=1, chain_id="SN_SEPOLIA", revision=0)
        assert domain.revision == 0

    def test_to_starknet_domain(self):
        domain = build_medialane_domain(version=1, chain_id="SN_SEPOLIA", revision=1)
        starknet_domain = to_starknet_domain(domain)
        assert starknet_domain["name"] == "Medialane-1"
        assert starknet_domain["revision"] == 1  # integer, not string


class TestListingTypedData:
    """Test SNIP-12 typed data for listing intent."""

    def test_typed_data_revision_is_integer(self):
        domain = build_medialane_domain(version=1, chain_id="SN_SEPOLIA", revision=1)
        typed_data = build_listing_typed_data(
            domain=domain,
            order_hash="0xHASH",
            offerer="0xOFFERER",
            token_address="0xTOKEN",
            token_id=42,
            start_amount=500000,
            end_amount=0,
            currency="0xUSDC",
            start_date=1000,
            end_date=2000,
            broker_id="0xBROKER",
            nonce=0,
        )
        assert typed_data["domain"]["revision"] == 1  # integer, not string

    def test_typed_data_primary_type_order(self):
        domain = build_medialane_domain(version=1, chain_id="SN_SEPOLIA", revision=1)
        typed_data = build_listing_typed_data(
            domain=domain,
            order_hash="0xHASH",
            offerer="0xOFFERER",
            token_address="0xTOKEN",
            token_id=42,
            start_amount=500000,
            end_amount=0,
            currency="0xUSDC",
            start_date=1000,
            end_date=2000,
            broker_id="0xBROKER",
        )
        assert typed_data["primaryType"] == "Order"

    def test_typed_data_has_starknet_domain_type(self):
        domain = build_medialane_domain(version=1, chain_id="SN_SEPOLIA", revision=1)
        typed_data = build_listing_typed_data(
            domain=domain,
            order_hash="0xHASH",
            offerer="0xOFFERER",
            token_address="0xTOKEN",
            token_id=42,
            start_amount=500000,
            end_amount=0,
            currency="0xUSDC",
            start_date=1000,
            end_date=2000,
            broker_id="0xBROKER",
        )
        assert "StarknetDomain" in typed_data["types"]
        assert typed_data["types"]["StarknetDomain"][-1]["name"] == "revision"


class TestCancelTypedData:
    """Test SNIP-12 typed data for cancellation intent."""

    def test_cancel_typed_data_primary_type_cancel(self):
        domain = build_medialane_domain(version=1, chain_id="SN_SEPOLIA", revision=1)
        typed_data = build_cancel_typed_data(
            domain=domain,
            order_hash="0xHASH",
            offerer="0xOFFERER",
            token_address="0xTOKEN",
            token_id=42,
            nonce=0,
        )
        assert typed_data["primaryType"] == "Cancel"

    def test_cancel_typed_data_has_order_hash(self):
        domain = build_medialane_domain(version=1, chain_id="SN_SEPOLIA", revision=1)
        typed_data = build_cancel_typed_data(
            domain=domain,
            order_hash="0xCANCELHASH",
            offerer="0xOFFERER",
            token_address="0xTOKEN",
            token_id=99,
            nonce=5,
        )
        assert typed_data["message"]["orderHash"] == "0xCANCELHASH"
        assert typed_data["message"]["nonce"] == "5"
