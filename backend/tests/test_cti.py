"""
Tests for CTI projects and suspect correlation.

The previous implementation kept projects in a module-level list seeded with
invented operations, and scored suspects by substring:

    if "lahori" in handle: risk = 96
    else: risk = 75

Any handle produced a confident number, including one never observed. These
tests assert that a score now reflects evidence, and that its absence is
reported rather than filled in.
"""

import pytest

WALLET = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"


async def _seed_records(db, posts):
    from ai.enrichment import store_intelligence
    for i, (source, author, text) in enumerate(posts):
        await store_intelligence(
            source_type=source, source_url=f"https://src/{i}",
            raw_content=text, author=author, session=db,
        )


class TestSuspectCorrelation:

    async def test_unknown_account_scores_zero_and_says_so(self, db):
        """
        The decisive test. 'lahori' previously scored 96 on the strength of the
        substring alone, with no record behind it.
        """
        from ai.suspect_correlation import correlate_suspect

        for handle in ("@Tariq_Lahori", "@jagga_majitha", "@anyone_at_all"):
            result = await correlate_suspect(handle)
            assert result["found"] is False
            assert result["risk_score"] == 0
            assert result["matched_sources"] == []
            assert "no activity found" in result["correlation_summary"].lower()

    async def test_absence_of_evidence_is_not_called_low_risk(self, db):
        """These are different claims and must not be conflated."""
        from ai.suspect_correlation import correlate_suspect
        summary = (await correlate_suspect("@ghost"))["correlation_summary"].lower()
        assert "absence of evidence" in summary

    async def test_score_derives_from_collected_records(self, db):
        from ai.suspect_correlation import correlate_suspect
        await _seed_records(db, [
            ("TELEGRAM", "@jagga_drops", f"Veere Attari chitta ready aa, crypto {WALLET} te bhejo."),
            ("DARK_WEB", "@jagga_drops", f"Grade-A heroin available. Escrow {WALLET}."),
        ])
        result = await correlate_suspect("@jagga_drops")

        assert result["found"] is True
        assert result["risk_score"] > 0
        assert result["correlation_count"] == 2
        assert set(result["platforms"]) == {"TELEGRAM", "DARK_WEB"}
        assert all(m["record_id"] for m in result["matched_sources"])

    async def test_score_is_explainable(self, db):
        """A number an analyst cannot check is not an assessment."""
        from ai.suspect_correlation import correlate_suspect
        await _seed_records(db, [
            ("TELEGRAM", "@actor", "Chitta ready aa, Attari border te. Contact me."),
        ])
        breakdown = (await correlate_suspect("@actor"))["score_breakdown"]

        for key in ("highest_threat", "threat_points", "record_count",
                    "volume_points", "platform_count", "reach_points"):
            assert key in breakdown

    async def test_more_evidence_scores_higher(self, db):
        from ai.suspect_correlation import correlate_suspect
        await _seed_records(db, [
            ("TELEGRAM", "@quiet", "chitta available, contact me"),
            ("TELEGRAM", "@busy", f"Attari chitta ready, crypto {WALLET}, call 9814098211"),
            ("DARK_WEB", "@busy", f"Grade-A heroin available, escrow {WALLET}"),
            ("SURFACE_WEB", "@busy", "chitta supply Majitha corridor, bulk available"),
        ])
        quiet = await correlate_suspect("@quiet")
        busy = await correlate_suspect("@busy")
        assert busy["risk_score"] > quiet["risk_score"]

    async def test_shared_identifiers_surface_linked_actors(self, db):
        from ai.suspect_correlation import correlate_suspect
        await _seed_records(db, [
            ("TELEGRAM", "@alias_one", f"chitta ready, crypto {WALLET} te bhejo"),
            ("DARK_WEB", "alias_two", f"heroin available, escrow to {WALLET}"),
        ])
        result = await correlate_suspect("@alias_one")
        assert result["linked_actors"], "a reused wallet must surface the other actor"
        assert any("alias_two" in a for a in result["linked_actors"])


class TestProjectPersistence:

    async def test_no_seeded_projects_exist(self, db):
        from sqlalchemy import select
        from database.postgres import CTIProject
        assert (await db.execute(select(CTIProject))).scalars().all() == []

    async def test_projects_and_suspects_survive(self, db):
        """
        Projects lived in a Python list and emptied on restart, so nothing an
        investigator built was ever kept.
        """
        from sqlalchemy import select
        from database.postgres import CTIProject, CTIProjectSuspect

        project = CTIProject(name="Operation Test", topic="Drug Trafficking",
                             topic_key="drug_trafficking", is_observing=True)
        db.add(project)
        await db.commit()
        await db.refresh(project)

        db.add(CTIProjectSuspect(project_id=project.id, username="@tracked",
                                 risk_score=42, correlation_count=1))
        await db.commit()

        from database.postgres import AsyncSessionLocal
        async with AsyncSessionLocal() as fresh:          # new connection
            reloaded = (await fresh.execute(
                select(CTIProject).where(CTIProject.id == project.id)
            )).scalars().first()
            suspects = (await fresh.execute(
                select(CTIProjectSuspect)
                .where(CTIProjectSuspect.project_id == project.id)
            )).scalars().all()

        assert reloaded.name == "Operation Test"
        assert len(suspects) == 1
        assert suspects[0].risk_score == 42

    async def test_adding_a_source_starts_surveillance(self, db):
        """
        A project source that does not drive collection is a note, not
        surveillance. Adding one must register a real target.
        """
        from sqlalchemy import select
        from database.postgres import CTIProject, CTIProjectSource, Target

        project = CTIProject(name="Op", topic="Drug Trafficking", is_observing=True)
        db.add(project)
        await db.commit()
        await db.refresh(project)

        target = Target(identifier="t.me/test_channel", source_type="TELEGRAM",
                        label="Test", status="ACTIVE", scan_interval_minutes=60)
        db.add(target)
        await db.flush()
        db.add(CTIProjectSource(project_id=project.id, target_id=target.id,
                                identifier="t.me/test_channel",
                                source_type="TELEGRAM", label="Test"))
        await db.commit()

        linked = (await db.execute(
            select(CTIProjectSource).where(CTIProjectSource.project_id == project.id)
        )).scalars().first()
        assert linked.target_id == target.id


class TestVaultEncryption:

    def test_round_trip_recovers_the_payload(self):
        import asyncio
        from routes.cti_routes import (
            compress_and_encrypt, decrypt_and_decompress,
            CompressEncryptRequest, DecryptDecompressRequest,
        )

        payload = "Intercept dump: " + ("chitta ready aa, Attari border. " * 50)
        enc = asyncio.run(compress_and_encrypt(
            CompressEncryptRequest(data_payload=payload, passphrase="correct-horse-battery")))

        assert enc["compression_ratio_pct"] > 0
        dec = asyncio.run(decrypt_and_decompress(DecryptDecompressRequest(
            encrypted_payload_b64=enc["encrypted_payload_b64"],
            nonce_b64=enc["nonce_b64"], passphrase="correct-horse-battery")))
        assert dec["data_payload"] == payload

    def test_wrong_passphrase_is_rejected(self):
        import asyncio
        from fastapi import HTTPException
        from routes.cti_routes import (
            compress_and_encrypt, decrypt_and_decompress,
            CompressEncryptRequest, DecryptDecompressRequest,
        )

        enc = asyncio.run(compress_and_encrypt(
            CompressEncryptRequest(data_payload="secret", passphrase="right-passphrase")))

        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(decrypt_and_decompress(DecryptDecompressRequest(
                encrypted_payload_b64=enc["encrypted_payload_b64"],
                nonce_b64=enc["nonce_b64"], passphrase="wrong-passphrase")))
        assert excinfo.value.status_code == 400

    def test_passphrase_has_no_default(self):
        """
        The old models defaulted to a shared passphrase baked into the source,
        so an omitted passphrase produced confidently encrypted, publicly
        decryptable data.
        """
        from pydantic import ValidationError
        from routes.cti_routes import CompressEncryptRequest

        with pytest.raises(ValidationError):
            CompressEncryptRequest(data_payload="x")
