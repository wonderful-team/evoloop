"""ONNX domain classifier for the agent-delegation path.

This is the L1 classifier described in the routing design.  It runs after L0
local-action classification has failed (or returned a low-confidence result)
and provides a domain label such as ``coding``, ``business``,
``environment_query``, etc.  The label is passed to the agent engine via
``IntentHint.domain``; the engine is responsible for mapping the domain to a
concrete functional ``intent`` and ``suggested_modules``.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np
from tokenizers import Tokenizer

from app.core.config import settings
from app.core.routing.schemas import (
    DOMAIN_AMBIGUOUS,
    INTENT_DOMAIN_CLASSIFIED,
    IntentHint,
)

logger = logging.getLogger(__name__)

# Inference-time confidence threshold.  Below this we let the agent engine's
# fallback mapping take over.
CONFIDENCE_THRESHOLD = 0.6

_MAX_LENGTH = 128

_MODEL_DIR = Path(settings.MODELS_DIR) / "domain_classifier"
_MODEL_PATH = _MODEL_DIR / "classifier.onnx"
_LABEL_PATH = _MODEL_DIR / "labels.json"
_TOKENIZER_PATH = _MODEL_DIR / "tokenizer.json"

_session: Any = None
_tokenizer: Any = None
_id2name: dict[str, str] = {}
_lock = threading.Lock()


def _load() -> bool:
    """Load the ONNX model and tokenizer. Returns True on success."""
    global _session, _tokenizer, _id2name

    try:
        import onnxruntime as ort
    except ImportError:
        logger.warning("onnxruntime not installed, high-intent classifier unavailable")
        return False

    if not _MODEL_PATH.exists():
        logger.warning("High-intent ONNX model not found at %s", _MODEL_PATH)
        return False

    try:
        session = ort.InferenceSession(str(_MODEL_PATH))

        id2name: dict[str, str] = {}
        if _LABEL_PATH.exists():
            with open(_LABEL_PATH, encoding="utf-8") as f:
                mapping = json.load(f)
                id2name = mapping.get("id2name", {})

        tokenizer = Tokenizer.from_file(str(_TOKENIZER_PATH))
        tokenizer.enable_truncation(max_length=_MAX_LENGTH)
        tokenizer.enable_padding(length=_MAX_LENGTH)

        _session, _tokenizer, _id2name = session, tokenizer, id2name
        logger.info(
            "Domain classifier loaded from %s (%d labels, threshold=%.2f)",
            _MODEL_DIR, len(_id2name), CONFIDENCE_THRESHOLD,
        )
        return True
    except Exception:
        logger.exception("Failed to load high-intent classifier from %s", _MODEL_DIR)
        _session, _tokenizer, _id2name = None, None, {}
        return False


def predict(text: str) -> tuple[str | None, float]:
    """Return (high_label, confidence). Model unavailable returns (None, 0)."""
    global _session, _tokenizer

    cleaned = text.strip()
    if not cleaned:
        return None, 0.0

    if _session is None or _tokenizer is None:
        with _lock:
            if _session is None or _tokenizer is None:
                if not _load():
                    return None, 0.0

    encoding = _tokenizer.encode(text)
    input_ids = np.array([encoding.ids], dtype=np.int64)
    attention_mask = np.array([encoding.attention_mask], dtype=np.int64)

    ort_inputs = {
        _session.get_inputs()[0].name: input_ids,
        _session.get_inputs()[1].name: attention_mask,
    }
    logits = _session.run(None, ort_inputs)[0]

    exp = np.exp(logits - np.max(logits, axis=1, keepdims=True))
    probs = exp / exp.sum(axis=1, keepdims=True)
    sorted_idx = np.argsort(probs[0])[::-1]
    top_idx = int(sorted_idx[0])
    top_prob = float(probs[0][top_idx])

    label = _id2name.get(str(top_idx))
    if label is None:
        logger.warning("High-intent classifier returned unknown label index %d", top_idx)
        return None, top_prob

    return label, top_prob


def to_intent_hint(
    label: str,
    confidence: float,
    *,
    previous_intent: str | None = None,
    session_history: list[str] | None = None,
) -> IntentHint:
    """Map a domain label to the ``IntentHint`` consumed by the router.

    The router intentionally leaves ``intent`` and ``suggested_modules`` as
    placeholders; the agent engine maps ``domain`` to the concrete functional
    intent and module list.
    """
    domain = label if label else DOMAIN_AMBIGUOUS
    return IntentHint(
        intent=INTENT_DOMAIN_CLASSIFIED,
        domain=domain,
        confidence=confidence,
        suggested_modules=[],
        reason=f"domain: {domain}",
        previous_intent=previous_intent,
        session_history=session_history,
    )


# Eager load at module import time for low-latency first request.
_load()


__all__ = ["predict", "to_intent_hint"]
