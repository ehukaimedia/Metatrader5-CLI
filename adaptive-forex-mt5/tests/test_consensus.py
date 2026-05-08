"""Strict 2-of-2 consensus.evaluate() — every invariant from the spec."""
from __future__ import annotations

import consensus


FP = "deadbeef"


def _vote(reviewer="A", *, decision="take", direction="buy", confidence=0.84,
          accepted_levels=True, fingerprint=FP):
    return {
        "reviewer": reviewer,
        "decision": decision,
        "direction": direction,
        "confidence": confidence,
        "accepted_levels": accepted_levels,
        "reviewed_fingerprint": fingerprint,
    }


def test_strict_take_passes_all_invariants():
    out = consensus.evaluate([_vote("A"), _vote("B", confidence=0.79)],
                             alert_fingerprint=FP, min_confidence=0.75)
    assert out["consensus"] == "take"
    assert "2-of-2 take" in out["consensus_reason"]


def test_one_skip_blocks():
    out = consensus.evaluate(
        [_vote("A"), _vote("B", decision="skip", accepted_levels=False)],
        alert_fingerprint=FP, min_confidence=0.75,
    )
    assert out["consensus"] == "no_consensus"
    assert "one_skipped" in out["consensus_reason"] or "not_both_take" in out["consensus_reason"]


def test_one_adjust_blocks_levels_not_accepted():
    out = consensus.evaluate(
        [_vote("A"), _vote("B", decision="adjust", accepted_levels=False)],
        alert_fingerprint=FP, min_confidence=0.75,
    )
    assert out["consensus"] == "no_consensus"


def test_direction_mismatch_blocks():
    out = consensus.evaluate([_vote("A"), _vote("B", direction="sell")],
                             alert_fingerprint=FP, min_confidence=0.75)
    assert out["consensus"] == "no_consensus"
    assert "direction_mismatch" in out["consensus_reason"]


def test_confidence_below_threshold_blocks():
    out = consensus.evaluate([_vote("A"), _vote("B", confidence=0.50)],
                             alert_fingerprint=FP, min_confidence=0.75)
    assert out["consensus"] == "no_consensus"
    assert "confidence_below_threshold" in out["consensus_reason"]


def test_levels_not_accepted_blocks():
    out = consensus.evaluate([_vote("A"), _vote("B", accepted_levels=False)],
                             alert_fingerprint=FP, min_confidence=0.75)
    assert out["consensus"] == "no_consensus"
    assert "levels_not_accepted" in out["consensus_reason"]


def test_fingerprint_mismatch_blocks():
    out = consensus.evaluate([_vote("A"), _vote("B", fingerprint="cafebabe")],
                             alert_fingerprint=FP, min_confidence=0.75)
    assert out["consensus"] == "no_consensus"
    assert "fingerprint_mismatch" in out["consensus_reason"]


def test_wrong_vote_count_blocks():
    out = consensus.evaluate([_vote("A")],
                             alert_fingerprint=FP, min_confidence=0.75)
    assert out["consensus"] == "no_consensus"
    assert "wrong_vote_count" in out["consensus_reason"]
    out = consensus.evaluate([_vote("A"), _vote("B"), _vote("C")],
                             alert_fingerprint=FP, min_confidence=0.75)
    assert out["consensus"] == "no_consensus"
