"""
Remove fabricated records left behind by the old seed script.

The retired database/seed_data.py wrote invented intelligence records, targets
and wallets straight into the operational database. They are indistinguishable
from collected evidence in the UI, and they distort every count, hotspot and
correlation the system produces.

Seeded records are identified by an "origin" key at the top level of
metadata_json - a marker the seed script wrote and no ingest path produces.
Records collected by a scraper or entered through the simulator do not carry
it, so genuine evidence is never matched.

Reports only by default. Deletion requires --apply.

    python scripts/purge_demo_data.py
    python scripts/purge_demo_data.py --apply
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _is_seeded(record) -> bool:
    """
    True when a record carries the retired seed script's marker.

    Deliberately narrow: it is far better to leave a fabricated record in place
    for a human to review than to delete a real piece of evidence.
    """
    meta = record.metadata_json or {}
    return isinstance(meta, dict) and "origin" in meta


async def find_seeded():
    from sqlalchemy import select
    from database.postgres import (
        AsyncSessionLocal, ScrapedData, Target, CryptoWalletIntel, init_db,
    )

    # A database created before the current schema is missing later columns;
    # init_db() creates missing tables and applies them. Safe to repeat.
    await init_db()

    async with AsyncSessionLocal() as db:
        records = [r for r in (await db.execute(select(ScrapedData))).scalars().all()
                   if _is_seeded(r)]
        seeded_urls = {r.source_url or "" for r in records}

        # Targets the seed script created. Matching on "..." alone missed the
        # ones with plausible identifiers - t.me/border_transit_alert and the
        # like - which then sat on the Sources page failing forever. A seeded
        # target is one whose identifier appears in a seeded record's URL,
        # which cannot match a source the operator added themselves.
        def _normalise(value: str) -> str:
            # Telegram's public preview inserts "/s/" into the path, so a
            # target of t.me/channel never appears verbatim in the record URL
            # t.me/s/channel/481. Removing it makes the two comparable.
            out = (value or "").strip().lower()
            for prefix in ("https://", "http://"):
                if out.startswith(prefix):
                    out = out[len(prefix):]
            return out.replace("t.me/s/", "t.me/").rstrip("/")

        normalised_seeded = {_normalise(url) for url in seeded_urls}

        def _is_seeded_target(t) -> bool:
            identifier = (t.identifier or "").strip()
            if not identifier:
                return False
            if "..." in identifier:
                return True
            bare = _normalise(identifier)
            if not bare:
                return False
            return any(bare in url for url in normalised_seeded)

        targets = [t for t in (await db.execute(select(Target))).scalars().all()
                   if _is_seeded_target(t)]
        wallets = [w for w in (await db.execute(select(CryptoWalletIntel))).scalars().all()
                   if w.associated_source_url in seeded_urls
                   or "..." in (w.associated_source_url or "")]
    return records, targets, wallets


async def main(apply: bool):
    from database.postgres import AsyncSessionLocal, ScrapedData, MediaArtifact
    from sqlalchemy import select

    records, targets, wallets = await find_seeded()

    print("=" * 72)
    print("FABRICATED RECORDS FOUND")
    print("=" * 72)

    if not records and not targets and not wallets:
        print("\nNothing to remove - the database contains no seeded material.")
        return

    if records:
        print(f"\nIntelligence records ({len(records)}):")
        for r in records:
            impossible = " [IMPOSSIBLE .onion]" if "..." in (r.source_url or "") else ""
            print(f"  id={r.id:<4} {r.source_type:<12} {(r.source_url or '')[:56]}{impossible}")
            print(f"           {(r.cleaned_text or '')[:70].strip()}")

    if targets:
        print(f"\nSurveillance targets ({len(targets)}):")
        for t in targets:
            print(f"  id={t.id:<4} {t.source_type:<12} {t.identifier}")

    if wallets:
        print(f"\nCrypto wallets ({len(wallets)}):")
        for w in wallets:
            print(f"  id={w.id:<4} {w.crypto_type:<5} {w.wallet_address[:44]}")

    if not apply:
        print("\n" + "-" * 72)
        print("Report only. Nothing has been deleted.")
        print("Re-run with --apply to remove these records.")
        print("Records collected by a scraper or entered through the simulator")
        print("are not matched and will not be touched.")
        return

    async with AsyncSessionLocal() as db:
        deleted_media = 0
        for record in records:
            fresh = await db.get(ScrapedData, record.id)
            if not fresh:
                continue
            artifacts = (await db.execute(
                select(MediaArtifact).where(MediaArtifact.scraped_data_id == record.id)
            )).scalars().all()
            for artifact in artifacts:
                await db.delete(artifact)
                deleted_media += 1
            await db.delete(fresh)

        for target in targets:
            fresh = await db.get(type(target), target.id)
            if fresh:
                await db.delete(fresh)
        for wallet in wallets:
            fresh = await db.get(type(wallet), wallet.id)
            if fresh:
                await db.delete(fresh)

        await db.commit()

    # The correlation graph is derived data: its nodes point at record ids
    # that no longer exist. Leaving them would keep deleted suspects on the
    # network page. Clearing it is safe - sync_graph rebuilds it from the
    # remaining records on the next analysis run.
    from database.postgres import GraphNode, GraphEdge

    graph_rows = 0
    async with AsyncSessionLocal() as db:
        for model in (GraphEdge, GraphNode):
            for row in (await db.execute(select(model))).scalars().all():
                await db.delete(row)
                graph_rows += 1
        await db.commit()

    print("\n" + "-" * 72)
    print(f"Deleted {len(records)} record(s), {len(targets)} target(s), "
          f"{len(wallets)} wallet(s), {deleted_media} media artifact(s), "
          f"{graph_rows} graph row(s).")
    print("Re-run the analysis pipeline so counts and correlations reflect the change:")
    print("  POST /api/ai/run-pipeline")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually delete; without this the script only reports")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
