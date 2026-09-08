"""
Zero-Shot Semantic Classifier - ADVISORY ONLY.

This was built to separate a dealer's offer from a news report about dealing.
It does not achieve that. Measured against real examples:

    dealer's message  -> "ordinary conversation unrelated to drugs"  (55%)
    news report       -> "offering illegal drugs for sale"           (39%)
    Wikipedia article -> "smuggling drugs across a border"           (72%)

The failure is structural, not a tuning problem. Zero-shot NLI scores whether
a text is *about* a topic; an encyclopedia entry about smuggling genuinely is
about smuggling. The distinction that matters here is not topic but speech act
- who is speaking, and what they are doing with the words - which is handled
by ai/speech_act.py instead.

The model is kept because its label distribution is useful context for an
analyst, and because a better model (a multilingual NLI model, or one
fine-tuned on labelled intercepts) could be dropped in here later. It is
disabled by default and its output never changes a threat level.
"""

from typing import Any, Dict, List, Optional
import logging
import threading

from config import settings

logger = logging.getLogger("semantic_classifier")

# Hypotheses the model scores the text against. The first four describe
# operational activity; the last two describe talking *about* it.
OPERATIONAL_LABELS = [
    "offering illegal drugs for sale",
    "arranging a drug delivery or dead drop",
    "smuggling drugs across a border",
    "asking to buy illegal drugs",
]

CONTEXTUAL_LABELS = [
    "news reporting or an encyclopedia article about drugs",
    "ordinary conversation unrelated to drugs",
]

CANDIDATE_LABELS = OPERATIONAL_LABELS + CONTEXTUAL_LABELS

# Confidence needed before the model is allowed to move the rule score.
# Speech-act confidence needed before the rule score is moved.
REPORT_CONFIDENCE = 0.60
OFFER_CONFIDENCE = 0.60
# Retained for callers that still import these names.
UPGRADE_CONFIDENCE = OFFER_CONFIDENCE
DOWNGRADE_CONFIDENCE = REPORT_CONFIDENCE

# Transformer inference is quadratic in sequence length; truncate long pages.
MAX_CHARS = 1200


class SemanticClassifier:
    """Lazy-loading wrapper around a zero-shot NLI pipeline."""

    def __init__(self):
        self._pipeline = None
        self._attempted = False
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._pipeline is not None

    def load(self) -> bool:
        """
        Load the model on first use.

        Held behind a lock because FastAPI may call this from several request
        handlers at once, and loading twice would double the memory footprint.
        """
        if self._attempted:
            return self._pipeline is not None

        with self._lock:
            if self._attempted:
                return self._pipeline is not None
            self._attempted = True

            if not settings.SEMANTIC_CLASSIFIER_ENABLED:
                logger.info("Semantic classifier disabled by configuration.")
                return False

            try:
                from transformers import pipeline
                logger.info("Loading zero-shot model %s (first run downloads weights)...",
                            settings.SEMANTIC_CLASSIFIER_MODEL)
                self._pipeline = pipeline(
                    "zero-shot-classification",
                    model=settings.SEMANTIC_CLASSIFIER_MODEL,
                    device=-1,  # CPU
                )
                logger.info("Zero-shot semantic classifier ready.")
            except Exception as e:
                logger.warning("Semantic classifier unavailable (%s). "
                               "Threat scoring stays rule-only.", e)
                self._pipeline = None

        return self._pipeline is not None

    def classify(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Score the text against the candidate hypotheses.

        Returns None when the model is unavailable, so callers fall back to
        rules cleanly rather than erroring.
        """
        if not text or not text.strip():
            return None
        if not self.load():
            return None

        snippet = text.strip()[:MAX_CHARS]

        try:
            result = self._pipeline(snippet, CANDIDATE_LABELS, multi_label=False)
        except Exception as e:
            logger.warning("Zero-shot inference failed: %s", e)
            return None

        scores = dict(zip(result["labels"], result["scores"]))
        top_label = result["labels"][0]
        top_score = float(result["scores"][0])

        operational_score = sum(scores.get(l, 0.0) for l in OPERATIONAL_LABELS)
        contextual_score = sum(scores.get(l, 0.0) for l in CONTEXTUAL_LABELS)

        return {
            "model": settings.SEMANTIC_CLASSIFIER_MODEL,
            "top_label": top_label,
            "top_confidence": round(top_score, 4),
            "is_operational": top_label in OPERATIONAL_LABELS,
            "operational_score": round(operational_score, 4),
            "contextual_score": round(contextual_score, 4),
            "all_scores": {k: round(v, 4) for k, v in scores.items()},
        }


semantic_classifier = SemanticClassifier()


# Threat bands, lowest to highest, for stepping a level up or down.
_LADDER = ["LOW", "MEDIUM", "HIGH", "SEVERE"]


def _step(level: str, delta: int) -> str:
    try:
        idx = _LADDER.index(level)
    except ValueError:
        return level
    return _LADDER[max(0, min(len(_LADDER) - 1, idx + delta))]


def reconcile(rule_threat: Dict[str, Any],
              speech_act: Optional[Dict[str, Any]] = None,
              semantic: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Combine the keyword score with the speech-act verdict.

    The speech act drives the adjustment, not the transformer. Measured on
    real examples the zero-shot model rated a Wikipedia article about
    smuggling as operational trafficking at 72% confidence - higher than an
    actual dealer's message - because NLI scores topical entailment, not who
    is speaking. Its output is retained here as advisory context only.

    The rule score is never overwritten: it stays as `rule_threat_level`, and
    every adjustment records the evidence that caused it.
    """
    threat = dict(rule_threat)
    threat["rule_threat_level"] = rule_threat.get("threat_level")
    threat["speech_act"] = speech_act
    threat["semantic_advisory"] = semantic

    if not speech_act:
        threat["semantic_adjustment"] = None
        return threat

    level = threat["threat_level"]
    act = speech_act.get("act")
    confidence = speech_act.get("confidence", 0.0)
    adjustment = None

    if act == "REPORT" and confidence >= REPORT_CONFIDENCE:
        # Keywords fired, but this is someone describing trafficking, not
        # conducting it - a news story, a court record, a reference article.
        if level in ("MEDIUM", "HIGH", "SEVERE"):
            # Drop two bands when the reading is decisive. Dominance is used
            # rather than raw confidence so long pages are judged the same way
            # short intercepts are.
            decisive = speech_act.get("is_decisive") or confidence >= 0.8
            new_level = _step(level, -2 if decisive else -1)
            adjustment = {
                "direction": "DOWNGRADE",
                "from": level, "to": new_level,
                "reason": "keywords matched but the text %s" % speech_act.get("reason", ""),
            }
            level = new_level

    elif act in ("OFFER", "DEMAND") and confidence >= OFFER_CONFIDENCE:
        # An explicit offer or request, even where the keyword list is thin.
        if level in ("LOW", "MEDIUM"):
            new_level = _step(level, 1)
            adjustment = {
                "direction": "UPGRADE",
                "from": level, "to": new_level,
                "reason": "low keyword score but the text %s" % speech_act.get("reason", ""),
            }
            level = new_level

    threat["threat_level"] = level
    threat["semantic_adjustment"] = adjustment
    threat["requires_immediate_action"] = level in ("HIGH", "SEVERE")
    return threat
