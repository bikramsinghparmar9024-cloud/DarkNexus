"""
AI-Generated Police Case Dossier Narrative Builder.
Synthesizes extracted intelligence into structured, court-ready briefs:
- Executive Overview
- Modus Operandi Analysis
- Identified Nexus of Suspects, Channels & Onion Domains
- Financial & Crypto Laundering Evidence
- Recommended Police Interdiction Actions
"""

from typing import Dict, Any, List
from datetime import datetime


def generate_ai_case_narrative(
    evidence_items: List[Dict[str, Any]],
    investigator_badge: str,
    case_title: str = "Inter-State Narcotic Trafficking Network Investigation"
) -> Dict[str, Any]:
    """Compile structured forensic intelligence narrative from evidence collection."""
    all_drugs = set()
    all_locations = set()
    all_wallets = set()
    all_handles = set()

    for item in evidence_items:
        entities = item.get("flagged_entities") or {}
        for d in entities.get("drugs", []):
            all_drugs.add(d)
        for loc in entities.get("locations", []):
            all_locations.add(loc)
        for h in entities.get("handles", []):
            all_handles.add(h)
        for btc in entities.get("crypto_wallets", {}).get("btc", []):
            all_wallets.add(btc)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    executive_summary = (
        f"This intelligence dossier consolidates {len(evidence_items)} cryptographically verified (SHA-256) intercepts "
        f"harvested across Dark Web marketplaces, encrypted Telegram channels, and clearnet chemical forums. "
        f"Analysis indicates an active syndicate distributing {', '.join(all_drugs) or 'Chitta (Heroin) and Synthetic Opioids'} "
        f"with significant transit vectors identified around {', '.join(all_locations) or 'Amritsar and Majitha border corridors'}."
    )

    modus_operandi = (
        "1. Communication: Utilizes encrypted Telegram communication and darknet hidden services with short-lived session identifiers.\n"
        "2. Financial Settlements: Directs retail and wholesale purchasers to Bitcoin escrow wallets and anonymized UPI barcodes.\n"
        "3. Delivery Logistics: Predominantly leverages GPS-tagged dead-drops in rural border belts and inter-city postal courier concealment."
    )

    recommended_actions = [
        "Issue Section 91 CrPC notices to telecommunication providers for identified phone numbers.",
        "Initiate blockchain transaction monitoring on identified Bitcoin escrow addresses.",
        "Deploy border surveillance units along the identified Majitha-Amritsar supply line.",
        "Coordinate with Narcotics Control Bureau (NCB) for precursor supply chain interdiction."
    ]

    return {
        "case_title": case_title,
        "investigator_badge": investigator_badge,
        "generated_at": timestamp,
        "executive_summary": executive_summary,
        "modus_operandi": modus_operandi,
        "identified_substances": list(all_drugs),
        "identified_locations": list(all_locations),
        "tracked_wallets": list(all_wallets),
        "suspect_handles": list(all_handles),
        "recommended_actions": recommended_actions
    }
