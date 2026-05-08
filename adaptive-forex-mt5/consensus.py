"""Strict 2-of-2 consensus on a pair of phase-1 reviewer verdicts.

The autopilot consensus rule (per spec): both reviewers must vote `take`
with the same direction, both must accept the deterministic levels (no
adjustment), both reviewed_fingerprint must match the alert's fingerprint,
and both confidences must meet the threshold. Anything else → no_consensus.

This is a pure function — no I/O, no state.db, no journal. The caller
journals `kind=consensus_verdict` regardless of outcome (shadow mode).
"""
from __future__ import annotations


def evaluate(votes: list[dict], *, alert_fingerprint: str,
             min_confidence: float) -> dict:
    """Return `{"consensus": "take" | "no_consensus", "consensus_reason": str}`.

    Each vote is the phase-1 reviewer verdict shape (decision, direction,
    confidence, accepted_levels, reviewed_fingerprint, ...). For phase-2
    autopilot we require exactly 2 votes and every invariant below.
    """
    if len(votes) != 2:
        return {"consensus": "no_consensus",
                "consensus_reason": f"wrong_vote_count={len(votes)}"}
    a, b = votes
    decisions = (a.get("decision"), b.get("decision"))
    if decisions != ("take", "take"):
        if "skip" in decisions:
            return {"consensus": "no_consensus", "consensus_reason": "one_skipped"}
        return {"consensus": "no_consensus", "consensus_reason": "not_both_take"}
    if not (a.get("accepted_levels") and b.get("accepted_levels")):
        return {"consensus": "no_consensus", "consensus_reason": "levels_not_accepted"}
    if a.get("direction") != b.get("direction"):
        return {"consensus": "no_consensus", "consensus_reason": "direction_mismatch"}
    if a.get("reviewed_fingerprint") != alert_fingerprint or \
       b.get("reviewed_fingerprint") != alert_fingerprint:
        return {"consensus": "no_consensus",
                "consensus_reason": "fingerprint_mismatch"}
    min_conf = min(float(a.get("confidence") or 0), float(b.get("confidence") or 0))
    if min_conf < float(min_confidence):
        return {"consensus": "no_consensus",
                "consensus_reason": f"confidence_below_threshold (min={min_conf:.2f}, "
                                    f"required={min_confidence:.2f})"}
    return {
        "consensus": "take",
        "consensus_reason": (f"2-of-2 take, conf min={min_conf:.2f} >= "
                             f"{float(min_confidence):.2f}, levels accepted, "
                             "fingerprints match"),
    }
