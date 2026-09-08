"""
Migrate the correlation graph onto canonical entity keys.

Changing how node keys are built orphans everything already stored: the old
rows keep their old keys, new writes create fresh nodes beside them, and the
graph either looks empty or shows every entity twice. Rewriting the stored
keys is therefore part of the change, not a follow-up.

The rewrite also merges. Keys that were distinct only because of spelling -
`drug_Heroin / Chitta`, `drug_chitta`, `drug_smack` - collapse onto one
canonical node, and their observation counts and evidence ids are combined
rather than one row winning and the rest being dropped.

Run:  python scripts/migrate_graph_identity.py [--dry-run]

Safe to run more than once: keys already canonical are left alone.
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.identity import slugify_entity_key  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "drug_intel.db")

# Old prefix -> entity type, so a stored key can be re-keyed without guessing.
PREFIX_TYPES = {
    "suspect_": "suspect", "actor_": "suspect", "vendor_": "vendor",
    "drug_": "drug", "wallet_": "wallet", "intercept_": "intercept",
    "phone_": "phone", "upi_": "upi", "pgp_": "pgp", "device_": "device",
}

NEW_COLUMNS = {
    "graph_nodes": [("label_verified", "BOOLEAN DEFAULT 0")],
    "graph_edges": [
        ("evidence_record_ids", "JSON"),
        ("status", "VARCHAR(20) DEFAULT 'PENDING'"),
        ("reviewed_by", "VARCHAR(200)"),
        ("reviewed_at", "DATETIME"),
        ("review_note", "TEXT"),
    ],
}


def add_missing_columns(conn, dry_run: bool) -> None:
    """SQLAlchemy's create_all does not alter existing tables; do it here."""
    for table, columns in NEW_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns:
            if name in existing:
                continue
            print(f"  + {table}.{name}")
            if not dry_run:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def canonical_key(old_key: str) -> str:
    """Re-key one stored node id, keeping its entity type."""
    for prefix, entity_type in PREFIX_TYPES.items():
        if old_key.startswith(prefix):
            return slugify_entity_key(old_key[len(prefix):], entity_type)
    # No recognised prefix: leave it alone rather than invent a type for it.
    return old_key


def migrate_nodes(conn, dry_run: bool):
    rows = list(conn.execute(
        "SELECT id, node_key, label, node_type, threat_level, first_seen, "
        "last_seen, mention_count FROM graph_nodes"))

    mapping, groups = {}, defaultdict(list)
    for row in rows:
        new_key = canonical_key(row[1])
        mapping[row[1]] = new_key
        groups[new_key].append(row)

    merged = renamed = 0
    for new_key, members in groups.items():
        if len(members) > 1:
            merged += len(members) - 1
            print(f"  merge {len(members)} -> {new_key}")
            for m in members:
                print(f"        was: {m[1]}")
        elif members[0][1] != new_key:
            renamed += 1

        keep = min(members, key=lambda r: r[0])
        total_mentions = sum(m[7] or 0 for m in members)
        # The most recently seen label, not the longest one.
        newest = max(members, key=lambda r: (r[6] or "", r[0]))

        if not dry_run:
            # Delete first. One of the duplicates may already hold the
            # canonical key - renaming the survivor onto it before removing
            # the others violates the unique constraint.
            for extra in members:
                if extra[0] != keep[0]:
                    conn.execute("DELETE FROM graph_nodes WHERE id=?", (extra[0],))
            conn.execute(
                "UPDATE graph_nodes SET node_key=?, label=?, mention_count=?, "
                "first_seen=?, last_seen=? WHERE id=?",
                (new_key, newest[2], total_mentions,
                 min(m[5] or "" for m in members),
                 max(m[6] or "" for m in members), keep[0]))

    return mapping, renamed, merged


def migrate_edges(conn, mapping, dry_run: bool):
    rows = list(conn.execute(
        "SELECT id, edge_key, source_key, target_key, relation, "
        "observation_count, first_seen, last_seen, evidence_record_ids "
        "FROM graph_edges"))

    groups = defaultdict(list)
    for row in rows:
        source = mapping.get(row[2], canonical_key(row[2]))
        target = mapping.get(row[3], canonical_key(row[3]))
        groups[f"{source}|{row[4]}|{target}"].append((row, source, target))

    merged = renamed = 0
    for edge_key, members in groups.items():
        if len(members) > 1:
            merged += len(members) - 1
        elif members[0][0][1] != edge_key:
            renamed += 1

        keep, source, target = min(members, key=lambda m: m[0][0])
        observations = sum(m[0][5] or 0 for m in members)

        # Backfill evidence: an edge whose endpoint is intercept_<id> was
        # produced by that record, so the link is recoverable for existing
        # rows rather than only for ones collected from now on.
        evidence = set()
        for member in members:
            stored = member[0][8] if len(member[0]) > 8 else None
            if stored:
                try:
                    evidence.update(json.loads(stored))
                except (ValueError, TypeError):
                    pass
            for key in (member[1], member[2]):
                if key.startswith("intercept_") and key[len("intercept_"):].isdigit():
                    evidence.add(int(key[len("intercept_"):]))

        if not dry_run:
            for member in members:
                if member[0][0] != keep[0]:
                    conn.execute("DELETE FROM graph_edges WHERE id=?", (member[0][0],))
            conn.execute(
                "UPDATE graph_edges SET edge_key=?, source_key=?, target_key=?, "
                "observation_count=?, first_seen=?, last_seen=?, "
                "evidence_record_ids=? WHERE id=?",
                (edge_key, source, target, observations,
                 min(m[0][6] or "" for m in members),
                 max(m[0][7] or "" for m in members),
                 json.dumps(sorted(evidence)), keep[0]))

    return renamed, merged


def prune_orphans(conn, dry_run: bool):
    """
    Remove intercept nodes whose record no longer exists.

    Deduplicating collected records left their graph nodes behind, so the map
    still drew "Intercept #22" for a record that had been folded away. Clicking
    one showed a node with no evidence, which is exactly the dead end the
    evidence work was meant to remove. Only intercept nodes are pruned - a
    substance node legitimately has no record of its own.
    """
    live = {row[0] for row in conn.execute("SELECT id FROM scraped_data")}
    orphan_keys = []
    for (key,) in conn.execute(
            "SELECT node_key FROM graph_nodes WHERE node_key LIKE 'intercept_%'"):
        tail = key.split("_", 1)[1]
        if tail.isdigit() and int(tail) not in live:
            orphan_keys.append(key)

    if not orphan_keys:
        return 0, 0

    edge_count = 0
    for key in orphan_keys:
        edge_count += conn.execute(
            "SELECT COUNT(*) FROM graph_edges WHERE source_key=? OR target_key=?",
            (key, key)).fetchone()[0]
        print(f"  orphan: {key} (record no longer in the database)")
        if not dry_run:
            conn.execute(
                "DELETE FROM graph_edges WHERE source_key=? OR target_key=?",
                (key, key))
            conn.execute("DELETE FROM graph_nodes WHERE node_key=?", (key,))

    return len(orphan_keys), edge_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"No database at {DB_PATH}")
        return 1

    if not args.dry_run:
        backup = f"{DB_PATH}.pre-identity-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(DB_PATH, backup)
        print(f"Backup: {os.path.basename(backup)}")

    conn = sqlite3.connect(DB_PATH)
    try:
        print("Schema:")
        add_missing_columns(conn, args.dry_run)

        print("Nodes:")
        mapping, n_renamed, n_merged = migrate_nodes(conn, args.dry_run)
        print(f"  {n_renamed} re-keyed, {n_merged} merged away")

        print("Edges:")
        e_renamed, e_merged = migrate_edges(conn, mapping, args.dry_run)
        print(f"  {e_renamed} re-keyed, {e_merged} merged away")

        print("Orphans:")
        o_nodes, o_edges = prune_orphans(conn, args.dry_run)
        print(f"  {o_nodes} nodes and {o_edges} edges removed")

        if args.dry_run:
            conn.rollback()
            print("\nDRY RUN - nothing written.")
        else:
            conn.commit()
            nodes = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
            traced = conn.execute(
                "SELECT COUNT(*) FROM graph_edges "
                "WHERE evidence_record_ids IS NOT NULL "
                "AND evidence_record_ids != '[]'").fetchone()[0]
            print(f"\nDone: {nodes} nodes, {edges} edges, "
                  f"{traced} edges with traceable evidence.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
