#!/usr/bin/env python3
"""导出已训练的 action_classifier（PyTorch）为生产 ONNX，并用 onnxruntime 验证。

只做导出（不重训）。复用 models/action_classifier/ 下已训练的 model.safetensors。
输出覆盖 models/action_classifier/classifier.onnx，输入 input_ids/attention_mask（int64），
输出 logits，opset 14 —— 与推理端 app/core/routing/action_classifier.py 匹配。

用法：
    python3 scripts/export_intent_classifier_onnx.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "models" / "action_classifier"
MAX_LEN = 32

BACKUP_ONNX = ROOT / "models" / "action_classifier.pre_train" / "classifier.onnx"


def _verify_with_onnxruntime() -> None:
    """用 onnxruntime 验证输入输出 + 目标句子命中"登录"。"""
    import onnxruntime as ort
    from tokenizers import Tokenizer

    onnx_path = OUT_DIR / "classifier.onnx"
    sess = ort.InferenceSession(str(onnx_path))
    print(f"[verify] ONNX inputs: {[i.name for i in sess.get_inputs()]}")

    with open(OUT_DIR / "labels.json", encoding="utf-8") as f:
        id2name = json.load(f).get("id2name", {})

    tokenizer = Tokenizer.from_file(str(OUT_DIR / "tokenizer.json"))
    tokenizer.enable_truncation(max_length=MAX_LEN)
    tokenizer.enable_padding(length=MAX_LEN)

    def predict(text: str) -> list[tuple[str, float]]:
        enc = tokenizer.encode(text)
        logits = sess.run(
            None,
            {
                sess.get_inputs()[0].name: np.array([enc.ids], dtype=np.int64),
                sess.get_inputs()[1].name: np.array([enc.attention_mask], dtype=np.int64),
            },
        )[0]
        exp = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        probs = exp / exp.sum(axis=1, keepdims=True)
        order = np.argsort(probs[0])[::-1]
        return [(id2name.get(str(i), "?"), float(probs[0][i])) for i in order[:3]]

    print("[verify] logits shape:", sess.run(None, {
        sess.get_inputs()[0].name: np.zeros((1, MAX_LEN), dtype=np.int64),
        sess.get_inputs()[1].name: np.ones((1, MAX_LEN), dtype=np.int64),
    })[0].shape)

    for text in ["帮我登录商城后台", "登录后台", "登录管理后台", "注销登录"]:
        top = predict(text)
        margin = top[0][1] - top[1][1]
        print(f"[verify] {text!r} -> top3={top} margin={margin:.4f}")


def main() -> None:
    import torch
    from transformers import BertForSequenceClassification

    if not (OUT_DIR / "model.safetensors").exists():
        print(f"[export] model.safetensors not found in {OUT_DIR}", file=sys.stderr)
        sys.exit(1)

    # 导出前备份当前生产 ONNX（幂等：pre_train 已是最新备份时跳过覆盖）
    if BACKUP_ONNX.exists():
        prev = BACKUP_ONNX.read_bytes()
        cur = (OUT_DIR / "classifier.onnx").read_bytes() if (OUT_DIR / "classifier.onnx").exists() else b""
        if prev != cur:
            BACKUP_ONNX.write_bytes(cur)
            print(f"[export] backed up current classifier.onnx -> {BACKUP_ONNX}")
    else:
        (OUT_DIR / "classifier.onnx").rename(BACKUP_ONNX) if (OUT_DIR / "classifier.onnx").exists() else None
        print(f"[export] moved existing classifier.onnx -> {BACKUP_ONNX}")

    print(f"[export] loading pytorch model from {OUT_DIR} ...")
    model = BertForSequenceClassification.from_pretrained(str(OUT_DIR))
    model.eval()
    model.to("cpu")

    dummy_ids = torch.randint(0, 30522, (1, MAX_LEN), dtype=torch.long)
    dummy_mask = torch.ones((1, MAX_LEN), dtype=torch.long)

    onnx_path = OUT_DIR / "classifier.onnx"
    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy_ids, dummy_mask),
            str(onnx_path),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch"},
                "attention_mask": {0: "batch"},
                "logits": {0: "batch"},
            },
            opset_version=14,
        )
    print(f"[export] exported -> {onnx_path}")

    _verify_with_onnxruntime()
    print("[export] DONE")


if __name__ == "__main__":
    main()
