"""
Speech-Act Detection: is this an OFFER, a DEMAND, or a REPORT?

This exists because the zero-shot transformer could not make the distinction
that actually matters. Measured on real examples, it rated a Wikipedia article
about drug smuggling as "smuggling drugs across a border" at 72% confidence -
higher than it rated an actual dealer's message. That is not a tuning problem:
an NLI model asks whether the text is *about* a topic, and an encyclopedia
entry about smuggling genuinely is.

The operative question is not the topic. It is who is speaking and what they
are doing with the words:

    OFFER   "Grade-A chitta ready, send payment to this wallet"
    DEMAND  "Looking for chitta near Amritsar, anyone?"
    REPORT  "Police seized 2kg chitta near Attari; three arrested"

All three contain the same nouns. They differ in person, tense, and framing -
which is exactly what surface markers capture well. The result is also fully
explainable: every verdict lists the phrases that produced it, which matters
for evidence that has to be defended in court.
"""

from typing import Any, Dict, List
import re

# ── Third-party reporting: someone describing events, not conducting them ──
REPORTING_MARKERS = [
    # Law enforcement outcomes
    "police", "seized", "seizure", "arrested", "arrest", "recovered",
    "busted", "raid", "raided", "custody", "accused", "convicted",
    "sentenced", "court", "fir ", "charge sheet", "chargesheet",
    "investigation", "prosecution", "confiscated", "apprehended",
    "crackdown", "operation was", "held with",
    # Journalistic / encyclopedic framing
    "according to", "reported", "reportedly", "officials said",
    "sources said", "spokesperson", "press release", "statement said",
    "has been affected", "is a major", "refers to", "is known as",
    "study found", "survey", "statistics", "data shows", "estimated",
    "drug trade", "affected by", "is a major", "commonly known",
    "authorities", "government", "ministry", "department of",
    "smuggled across", "trafficking in", "annual report",
]

# ── First-party supply: someone selling ────────────────────────────────
OFFER_MARKERS = [
    "available", "in stock", "ready", "ready aa", "for sale", "selling",
    "supply", "delivery available", "dm me", "dm for", "contact me",
    "message me", "inbox", "order now", "place order", "escrow",
    "send payment", "pay to", "advance", "rate list", "price list",
    "wholesale", "bulk available", "fresh stock", "restock",
    "pickup point", "drop point", "dead drop", "shipping",
    "barcode bhejo", "khata bhejo", "rate daso",
]

# ── First-party demand: someone buying ─────────────────────────────────
DEMAND_MARKERS = [
    "looking for", "need", "want to buy", "wtb", "anyone selling",
    "anyone have", "can i get", "where to get", "how much for",
    "miluga", "mil jau", "chahida", "kithe milega",
]

# Past-tense reporting verbs, which rarely appear in a live offer.
_PAST_REPORTING = re.compile(
    r"\b(was|were|had been|have been|has been|were arrested|was seized)\b", re.I
)

# How far the leading act must outscore the runner-up to count as decisive,
# independent of document length.
DECISIVE_DOMINANCE = 2.0

# Second-person / imperative address, typical of a live transaction.
_DIRECT_ADDRESS = re.compile(
    r"\b(send|pay|contact|call|message|order|dm|bhejo|karo|chakko|daso)\b", re.I
)


def _hits(text: str, markers: List[str]) -> List[str]:
    return [m for m in markers if m in text]


def detect_speech_act(text: str) -> Dict[str, Any]:
    """
    Classify what the text is *doing*, with the evidence for the verdict.

    Returns a dict carrying the act, a confidence in [0, 1], the matched
    phrases, and `is_operational` - False when the text is reporting on
    trafficking rather than conducting it.
    """
    if not text or not text.strip():
        return {
            "act": "UNKNOWN", "confidence": 0.0, "is_operational": False,
            "evidence": {}, "reason": "empty text",
        }

    low = text.lower()

    report_hits = _hits(low, REPORTING_MARKERS)
    offer_hits = _hits(low, OFFER_MARKERS)
    demand_hits = _hits(low, DEMAND_MARKERS)

    past_tense = bool(_PAST_REPORTING.search(low))
    direct_address = bool(_DIRECT_ADDRESS.search(low))

    # Weighted scores. Reporting markers are strong on their own because
    # words like "seized" and "arrested" almost never appear in a live offer.
    report_score = len(report_hits) * 2 + (1 if (past_tense and report_hits) else 0)
    offer_score = len(offer_hits) * 2 + (1 if direct_address else 0)
    demand_score = len(demand_hits) * 2

    # A dealer does not usually announce that police seized his own goods.
    # Where both fire, reporting language is the more reliable signal.
    scores = {"REPORT": report_score, "OFFER": offer_score, "DEMAND": demand_score}
    top_act = max(scores, key=scores.get)
    top_score = scores[top_act]

    if top_score == 0:
        return {
            "act": "CHATTER", "confidence": 0.0, "is_operational": True,
            "evidence": {}, "reason": "no speech-act markers found; treated as "
                                      "operational so the rule score stands unchanged",
        }

    total = sum(scores.values()) or 1
    confidence = round(top_score / total, 3)

    # Share of total understates dominance on long documents: a 60,000-word
    # page accumulates incidental markers of every kind, so a decisive verdict
    # still lands near 0.7. Dominance over the runner-up is the length-stable
    # measure - REPORT 41 against OFFER 13 is a clear reading whether the text
    # is two lines or two hundred.
    runner_up = max([s for k, s in scores.items() if k != top_act] or [0])
    dominance = round(top_score / runner_up, 2) if runner_up else float("inf")

    is_operational = top_act in ("OFFER", "DEMAND")

    evidence = {
        "reporting_markers": report_hits[:6],
        "offer_markers": offer_hits[:6],
        "demand_markers": demand_hits[:6],
        "past_tense_reporting": past_tense,
        "direct_address": direct_address,
    }

    if top_act == "REPORT":
        reason = ("reads as third-party reporting: matched %s%s"
                  % (", ".join("'%s'" % h for h in report_hits[:4]),
                     " with past-tense reporting verbs" if past_tense else ""))
    elif top_act == "OFFER":
        reason = ("reads as a supply offer: matched %s"
                  % ", ".join("'%s'" % h for h in offer_hits[:4]))
    else:
        reason = ("reads as buyer demand: matched %s"
                  % ", ".join("'%s'" % h for h in demand_hits[:4]))

    return {
        "act": top_act,
        "confidence": confidence,
        "dominance": dominance if dominance != float("inf") else None,
        "is_decisive": dominance >= DECISIVE_DOMINANCE,
        "is_operational": is_operational,
        "scores": scores,
        "evidence": evidence,
        "reason": reason,
    }
