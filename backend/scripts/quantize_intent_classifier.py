#!/usr/bin/env python3
"""INT8 动态量化 action_classifier ONNX，输出内嵌单文件。

完整流程（规避 onnx 1.22 strict shape-inference 对 dynamo 导出模型的 768/297 冲突）：
  1. 源 fp32 ONNX（可含 external data）→ 加载 + 清空 value_info 的 shape 标注（仅元数据，
     不影响执行）→ 保存内嵌单文件临时模型
  2. quantize_dynamic(QInt8, MatMul, per_channel) → 内嵌 int8 单文件
  3. 验证：无 external data、输入 input_ids/attention_mask、输出 logits (1,297)、
     目标句子命中"登录"

用法：
    python3 scripts/quantize_intent_classifier.py [源onnx] [输出onnx]
    默认：models/action_classifier/classifier.onnx -> classifier.int8.onnx
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MAX_LEN = 32


def _make_inline_clean(src: Path, tmp: Path) -> None:
    """加载源 ONNX（含 external data），清空 value_info shape 标注，保存内嵌单文件。"""
    import onnx

    m = onnx.load(str(src))
    for vi in m.graph.value_info:
        if vi.type.HasField("tensor_type") and vi.type.tensor_type.HasField("shape"):
            vi.type.tensor_type.ClearField("shape")
    onnx.save(m, str(tmp), save_as_external_data=False)


def _check_single_file(path: Path) -> None:
    import onnx

    m = onnx.load(str(path), load_external_data=False)
    external = [
        e.value
        for init in m.graph.initializer
        if init.HasField("data_location")
        and init.data_location == onnx.TensorProto.EXTERNAL
        for e in init.external_data
        if e.key == "location"
    ]
    if external:
        print(f"[check] ⚠ still references external data: {set(external)}", file=sys.stderr)
        sys.exit(1)
    print(f"[check] single-file ONNX (no external data): {path.stat().st_size / 1e6:.1f} MB")


def _verify(path: Path) -> None:
    import onnxruntime as ort
    from tokenizers import Tokenizer

    sess = ort.InferenceSession(str(path))
    print(f"[verify] inputs: {[i.name for i in sess.get_inputs()]} | outputs: {[o.name for o in sess.get_outputs()]}")

    with open(ROOT / "models" / "action_classifier" / "labels.json", encoding="utf-8") as f:
        id2name = json.load(f).get("id2name", {})

    tokenizer = Tokenizer.from_file(str(ROOT / "models" / "action_classifier" / "tokenizer.json"))
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

    for text in ["帮我登录商城后台", "登录后台", "注销", "帮我退出登录"]:
        top = predict(text)
        margin = top[0][1] - top[1][1]
        print(f"[verify] {text!r} -> top3={top} margin={margin:.4f}")


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "models" / "action_classifier" / "classifier.onnx"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "models" / "action_classifier" / "classifier.int8.onnx"

    if not src.exists():
        print(f"[quant] source not found: {src}", file=sys.stderr)
        sys.exit(1)

    from onnxruntime.quantization import QuantType, quantize_dynamic

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "inline_clean.onnx"
        print(f"[quant] preprocess {src} -> inline-clean...")
        _make_inline_clean(src, tmp)
        print(f"[quant] quantizing -> {out} (QInt8 dynamic, MatMul, per_channel)...")
        quantize_dynamic(
            str(tmp),
            str(out),
            weight_type=QuantType.QInt8,
            op_types_to_quantize=["MatMul"],
            per_channel=True,
        )
    print("[quant] done")

    _check_single_file(out)
    _verify(out)
    print("[quant] DONE")


if __name__ == "__main__":
    main()
