"""BERT-based intent classifier — replaces LocalMatcher for voice L0 routing."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np
from tokenizers import Tokenizer

logger = logging.getLogger(__name__)

_DEFAULT_MARGIN_THRESHOLD = 0.12
_MODEL_DIR = Path.home() / ".evoloop" / "models" / "action_classifier"
_MODEL_PATH = _MODEL_DIR / "classifier.onnx"
_LABEL_PATH = _MODEL_DIR / "labels.json"

_session: Any = None
_tokenizer: Any = None
_id2name: dict[str, str] = {}
_lock = threading.Lock()


def _get_threshold() -> float:
    """Read the L0 intent-classifier margin threshold from env or system config."""
    if env_val := os.getenv("EVOLOOP_L0_MARGIN_THRESHOLD"):
        try:
            return float(env_val)
        except ValueError:
            logger.warning("Invalid EVOLOOP_L0_MARGIN_THRESHOLD=%s, using default", env_val)
    try:
        from app.infrastructure.config.service import SystemConfigService

        cfg = SystemConfigService.get_value("EVOLOOP_L0_MARGIN_THRESHOLD")
        if cfg is not None:
            return float(cfg)
    except Exception as exc:
        logger.debug("Could not read L0 threshold from system config: %s", exc)
    return _DEFAULT_MARGIN_THRESHOLD


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
        tokenizer = Tokenizer.from_file(str(_MODEL_DIR / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=32)
        tokenizer.enable_padding(length=32)
        _session, _tokenizer, _id2name = session, tokenizer, id2name
        logger.info(
            "Intent classifier loaded from %s (%d labels, default_margin_threshold=%.2f)",
            _MODEL_DIR, len(_id2name), _DEFAULT_MARGIN_THRESHOLD,
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
    top1_prob, top2_prob = float(probs[0][sorted_idx[0]]), float(probs[0][sorted_idx[1]])
    margin = top1_prob - top2_prob
    idx = int(sorted_idx[0])

    if margin >= _get_threshold() and str(idx) in _id2name:
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


def initialize() -> bool:
    """服务启动时主动加载模型，避免首次语音请求时冷加载。"""
    with _lock:
        if _session is not None and _tokenizer is not None:
            return True
        return _load()


# 启动时立即加载（保持低延迟首响应）
initialize()
