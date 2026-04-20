"""
Intent Classifier
─────────────────
Classifies LLM response text → MotionState enum.
Runs BEFORE TTS starts so motion is ready when audio flows.
Uses a simple keyword + heuristic approach (no extra LLM call needed).
Can be swapped for a proper classifier later.
"""
import re
from enum import Enum


class MotionState(str, Enum):
    NEUTRAL   = "neutral"
    NODDING   = "nodding"
    THINKING  = "thinking"
    ENGAGED   = "engaged"
    EMPATHIC  = "empathic"
    LISTENING = "listening"


# Keyword patterns → motion state
_PATTERNS = [
    (MotionState.EMPATHIC, re.compile(
        r"\b(understand|sorry|feel|concern|difficult|hard|tough|"
        r"appreciate|empathize|sympathize|worry)\b", re.I
    )),
    (MotionState.THINKING, re.compile(
        r"\b(think|consider|analyze|let me|hmm|well|actually|"
        r"interesting|complex|depends|might|could|perhaps)\b", re.I
    )),
    (MotionState.ENGAGED, re.compile(
        r"\b(great|excellent|absolutely|exactly|perfect|wonderful|"
        r"fantastic|definitely|certainly|of course|sure)\b", re.I
    )),
    (MotionState.NODDING, re.compile(
        r"\b(yes|correct|right|agree|indeed|true|confirmed|"
        r"understood|got it|makes sense)\b", re.I
    )),
]

# Short responses → listening/engaged
_SHORT_RESPONSE_THRESHOLD = 20  # characters


def classify(text: str) -> MotionState:
    """
    Classify response text into a motion state.
    Returns the first matching state or NEUTRAL.
    """
    text = text.strip()

    if not text:
        return MotionState.NEUTRAL

    if len(text) <= _SHORT_RESPONSE_THRESHOLD:
        return MotionState.NODDING

    # Score each pattern
    scores: dict[MotionState, int] = {}
    for state, pattern in _PATTERNS:
        matches = pattern.findall(text)
        if matches:
            scores[state] = len(matches)

    if not scores:
        # Long neutral response → slight engaged head tilt
        if len(text) > 100:
            return MotionState.ENGAGED
        return MotionState.NEUTRAL

    # Return the state with the most keyword matches
    return max(scores, key=lambda s: scores[s])
