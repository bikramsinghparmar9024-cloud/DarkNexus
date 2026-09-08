"""
Tests for cryptocurrency address validation.

Addresses reach this system through OCR of screenshots, re-typed forum posts
and truncated listings - all of which produce address-shaped strings that are
not addresses. A wrong wallet in a case file points at nobody, and a
blockchain trace against it returns nothing, which reads as a dead end rather
than a transcription error.
"""

import pytest

REAL_P2PKH = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
REAL_P2SH = "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"
REAL_BECH32 = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
REAL_ETH_EIP55 = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"


class TestBitcoinValidation:

    @pytest.mark.parametrize("address,description", [
        (REAL_P2PKH, "P2PKH"),
        (REAL_P2SH, "P2SH"),
        ("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "P2PKH"),
        (REAL_BECH32, "segwit"),
    ])
    def test_genuine_addresses_verify(self, address, description):
        from ai.crypto_validation import validate_btc_address
        assert validate_btc_address(address)["valid"] is True

    def test_ocr_misread_is_rejected(self):
        """
        The case that motivated this: Tesseract read 'f' as 'I' and 'i' in a
        screenshot of a price list. Both strings match the regex.
        """
        from ai.crypto_validation import validate_btc_address
        assert validate_btc_address("1A1zP1eP5QGefi2DMPTITL5SLmv7DiviNa")["valid"] is False

    @pytest.mark.parametrize("address", [
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb",           # last character altered
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7Div",              # truncated
        "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5",   # bech32 corrupted
        "1A1zP0eP5QGefi2DMPTfTL5SLmv7DivfNa",           # '0' is not in base58
    ])
    def test_corrupted_addresses_are_rejected(self, address):
        from ai.crypto_validation import validate_btc_address
        assert validate_btc_address(address)["valid"] is False

    def test_rejection_explains_itself(self):
        from ai.crypto_validation import validate_btc_address
        result = validate_btc_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb")
        assert "checksum" in result["reason"].lower()


class TestEthereumValidation:

    def test_eip55_address_verifies(self):
        from ai.crypto_validation import validate_eth_address
        result = validate_eth_address(REAL_ETH_EIP55)
        assert result["valid"] is True
        assert result["checksum_verified"] is True

    def test_eip55_corruption_is_caught(self):
        """One character's capitalisation changed - EIP-55 encodes that."""
        from ai.crypto_validation import validate_eth_address
        corrupted = "0x742D35Cc6634C0532925a3b844Bc454e4438f44e"
        assert validate_eth_address(corrupted)["valid"] is False

    def test_single_case_address_is_well_formed_but_unverified(self):
        """
        Distinguishing "correct" from "no checksum available to check" matters:
        the second is not a guarantee and must not be presented as one.
        """
        from ai.crypto_validation import validate_eth_address
        result = validate_eth_address(REAL_ETH_EIP55.lower())
        assert result["valid"] is True
        assert result["checksum_verified"] is False
        assert result["reason"]


class TestExtractionIntegration:

    def test_only_verified_addresses_are_exposed_for_tracing(self):
        from ai.entity_extractor import entity_extractor

        text = (f"Pay to {REAL_P2PKH} or the misread version "
                f"1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb, ETH {REAL_ETH_EIP55}")
        e = entity_extractor.extract(text)

        assert e["crypto_wallets"]["btc"] == [REAL_P2PKH]
        assert e["crypto_wallets"]["eth"] == [REAL_ETH_EIP55]

    def test_unverified_addresses_are_kept_with_a_reason(self):
        """
        Not discarded: that a wallet was referenced is intelligence even when
        the transcription is unusable.
        """
        from ai.entity_extractor import entity_extractor

        e = entity_extractor.extract("send to 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb")
        unverified = e["crypto_wallets_unverified"]

        assert len(unverified) == 1
        assert unverified[0]["address"] == "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb"
        assert unverified[0]["reason"]

    async def test_bad_addresses_never_reach_the_wallet_table(self, db):
        """
        The consequence that matters: an unverified address must not become a
        tracked wallet, or a trace will be run against something fictional.
        """
        from sqlalchemy import select
        from ai.enrichment import store_intelligence
        from database.postgres import CryptoWalletIntel

        await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/s/x/1",
            raw_content=f"chitta ready, pay {REAL_P2PKH} or "
                        f"1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb",
            author="@actor", session=db,
        )
        wallets = [w.wallet_address for w in
                   (await db.execute(select(CryptoWalletIntel))).scalars().all()]

        assert REAL_P2PKH in wallets
        assert "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb" not in wallets

    async def test_bad_addresses_do_not_create_false_links(self, db):
        """
        Two actors sharing a misread address are not connected. Correlating on
        unverified data would manufacture a relationship out of OCR noise.
        """
        from ai.enrichment import store_intelligence
        from ai.correlation import correlation_engine

        bad = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb"
        for i, author in enumerate(("@actor_one", "@actor_two")):
            await store_intelligence(
                source_type="TELEGRAM", source_url=f"https://t.me/s/x/{i}",
                raw_content=f"chitta available, escrow to {bad}",
                author=author, session=db,
            )

        picture = await correlation_engine.build_intelligence_picture()
        assert not any(l["value"] == bad
                       for l in picture["identifier_links"]["links"])
