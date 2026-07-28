"""BERT-based intent classifier — replaces LocalMatcher for voice L0 routing."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np
from transformers import BertTokenizer

logger = logging.getLogger(__name__)

_MARGIN_THRESHOLD = 0.08
_MODEL_DIR = Path.home() / ".evoloop" / "models" / "intent_classifier"
_MODEL_PATH = _MODEL_DIR / "classifier.onnx"
_LABEL_PATH = _MODEL_DIR / "labels.json"

_session: Any = None
_tokenizer: Any = None
_id2name: dict[str, str] = {}
_lock = threading.Lock()


def _load() -> bool:
    """Load model. Returns True if loaded successfully."""
    global _session, _tokenizer, _id2name
    try:
        import onnxruntime as ort
    except ImportError:
        logger.warning("onnxruntime not installed, intent classifier unavailable")
        return False

    if not _MODEL_PATH.exists():
        logger.warning("ONNX model not found at %s", _MODEL_PATH)
        return False

    try:
        session = ort.InferenceSession(str(_MODEL_PATH))
        if _LABEL_PATH.exists():
            with open(_LABEL_PATH) as f:
                mapping = json.load(f)
                id2name = mapping.get("id2name", {})
        else:
            id2name = {}
        tokenizer = BertTokenizer.from_pretrained(str(_MODEL_DIR))
        _session, _tokenizer, _id2name = session, tokenizer, id2name
        logger.info(
            "Intent classifier loaded from %s (%d labels, margin_threshold=%.2f)",
            _MODEL_DIR, len(_id2name), _MARGIN_THRESHOLD,
        )
        return True
    except Exception as e:
        logger.warning("Failed to load intent classifier: %s", e)
        _session, _tokenizer, _id2name = None, None, {}
        return False


def predict(text: str) -> tuple[str | None, float]:
    """返回 (intent_name, margin_confidence).

    margin = top1_prob - top2_prob。模型不可用时返回 (None, 0)。
    """
    global _session, _tokenizer

    # 文本质量守卫：拒绝对无效输入做分类
    cleaned = text.strip()
    if not cleaned:
        return None, 0.0
    # 纯标点/符号（无中文、无字母）
    import re
    if not re.search(r'[\u4e00-\u9fff\w]', cleaned):
        return None, 0.0
    # 纯数字
    if cleaned.isdigit():
        return None, 0.0

    if _session is None or _tokenizer is None:
        with _lock:
            if _session is None or _tokenizer is None:
                if not _load():
                    return None, 0.0

    tokens = _tokenizer(
        text,
        padding="max_length",
        truncation=True,
        max_length=32,
        return_tensors="np",
    )
    ort_inputs = {
        _session.get_inputs()[0].name: tokens["input_ids"],
        _session.get_inputs()[1].name: tokens["attention_mask"],
    }
    logits = _session.run(None, ort_inputs)[0]

    exp = np.exp(logits - np.max(logits, axis=1, keepdims=True))
    probs = exp / exp.sum(axis=1, keepdims=True)
    sorted_idx = np.argsort(probs[0])[::-1]
    top1_prob, top2_prob = float(probs[0][sorted_idx[0]]), float(probs[0][sorted_idx[1]])
    margin = top1_prob - top2_prob
    idx = int(sorted_idx[0])

    if margin >= _MARGIN_THRESHOLD and str(idx) in _id2name:
        return _id2name[str(idx)], margin

    return None, margin


def reload():
    """热重载模型（训练后调用）。"""
    global _session, _tokenizer, _id2name
    with _lock:
        _session = None
        _tokenizer = None
        _id2name = {}
        _load()
