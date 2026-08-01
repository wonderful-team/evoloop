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

from app.core.routing.schemas import IntentHint

logger = logging.getLogger(__name__)

# Inference-time confidence threshold.  Below this we let the agent engine's
# fallback mapping take over.
CONFIDENCE_THRESHOLD = 0.6

_MAX_LENGTH = 128

_MODEL_DIR = Path.home() / ".evoloop" / "models" / "domain_classifier"
_FALLBACK_MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "domain_classifier"
_MODEL_PATH_NAME = "classifier.onnx"
_LABEL_FILE_NAME = "labels.json"
_TOKENIZER_FILE_NAME = "tokenizer.json"

# Sentinel intent used when the router leaves the functional intent/modules
# resolution to the agent engine.
_DOMAIN_CLASSIFIED_INTENT = "domain_classified"

_session: Any = None
_tokenizer: Any = None
_id2name: dict[str, str] = {}
_lock = threading.Lock()


def _resolve_model_dir() -> Path:
    """Prefer the deployed model under ``~/.evoloop``; fall back to project path."""
    home_candidate = _MODEL_DIR
    if (home_candidate / _MODEL_PATH_NAME).exists():
        return home_candidate
    return _FALLBACK_MODEL_DIR


def _load() -> bool:
    """Load the ONNX model and tokenizer. Returns True on success."""
    global _session, _tokenizer, _id2name

    try:
        import onnxruntime as ort
    except ImportError:
        logger.warning("onnxruntime not installed, high-intent classifier unavailable")
        return False

    model_dir = _resolve_model_dir()
    model_path = model_dir / _MODEL_PATH_NAME
    label_path = model_dir / _LABEL_FILE_NAME
    tokenizer_path = model_dir / _TOKENIZER_FILE_NAME

    if not model_path.exists():
        logger.warning("High-intent ONNX model not found at %s", model_path)
        return False

    try:
        session = ort.InferenceSession(str(model_path))

        id2name: dict[str, str] = {}
        if label_path.exists():
            with open(label_path, encoding="utf-8") as f:
                mapping = json.load(f)
                id2name = mapping.get("id2name", {})

        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(max_length=_MAX_LENGTH)
        tokenizer.enable_padding(length=_MAX_LENGTH)

        _session, _tokenizer, _id2name = session, tokenizer, id2name
        logger.info(
            "Domain classifier loaded from %s (%d labels, threshold=%.2f)",
            model_dir, len(_id2name), CONFIDENCE_THRESHOLD,
        )
        return True
    except Exception:
        logger.exception("Failed to load high-intent classifier from %s", model_dir)
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
    domain = label if label else "ambiguous"
    return IntentHint(
        intent=_DOMAIN_CLASSIFIED_INTENT,
        domain=domain,
        confidence=confidence,
        suggested_modules=[],
        reason=f"domain: {domain}",
        previous_intent=previous_intent,
        session_history=session_history,
    )


def reload() -> None:
    """Hot-reload the model after retraining."""
    global _session, _tokenizer, _id2name
    with _lock:
        _session = None
        _tokenizer = None
        _id2name = {}
        _load()


def initialize() -> bool:
    """Eagerly load the model at startup to avoid cold-start latency."""
    with _lock:
        if _session is not None and _tokenizer is not None:
            return True
        return _load()


# Eager load at module import time for low-latency first request.
initialize()


__all__ = ["predict", "to_intent_hint", "reload", "initialize"]
