#!/usr/bin/env python3
"""训练 L0 意图分类器（BERT）并导出 ONNX。

用法：
    python3 scripts/train_intent_classifier.py

数据：data/intents.yaml（intents 字典，297 个意图）
输出：models/action_classifier/{classifier.onnx, labels.json, tokenizer.json, ...}
推理端：app/core/routing/action_classifier.py（ONNX Runtime，输入 input_ids/attention_mask）
"""
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from torch.utils.data import Dataset

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "intents.yaml"
OUT_DIR = ROOT / "models" / "action_classifier"
BACKUP_DIR = ROOT / "models" / "action_classifier.pre_train"

MAX_LEN = 32
NUM_EPOCHS = 12
BATCH_SIZE = 32
LR = 3e-5

LABEL_IDS_TO_SKIP = set()


class IntentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        enc = self.tokenizer(
            self.texts[idx],
            padding="max_length",
            truncation=True,
            max_length=MAX_LEN,
        )
        return {
            "input_ids": torch.tensor(enc["input_ids"], dtype=torch.long),
            "attention_mask": torch.tensor(enc["attention_mask"], dtype=torch.long),
            "labels": torch.tensor(self.labels[idx], dtype=torch.long),
        }


def main():
    from transformers import BertForSequenceClassification, BertTokenizer

    if not DATA_PATH.exists():
        print(f"[train] intents.yaml not found: {DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(DATA_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    intents = data.get("intents", {})
    intent_names = list(intents.keys())
    name2id = {n: i for i, n in enumerate(intent_names)}
    id2name = {str(i): n for i, n in enumerate(intent_names)}
    print(f"[train] loaded {len(intent_names)} intents from {DATA_PATH.name}")

    texts, labels = [], []
    per_intent = {}
    for name, examples in intents.items():
        n = len(examples)
        per_intent[name] = n
        for ex in examples:
            texts.append(str(ex))
            labels.append(name2id[name])
    print(f"[train] total examples: {len(texts)}")
    print(f"[train] 登录 examples: {per_intent.get('登录', 0)} | 注销: {per_intent.get('注销', 0)}")

    # 备份现有模型（防止训练中断破坏生产模型）
    if OUT_DIR.exists():
        if BACKUP_DIR.exists():
            shutil.rmtree(BACKUP_DIR)
        shutil.copytree(OUT_DIR, BACKUP_DIR)
        print(f"[train] backed up current model -> {BACKUP_DIR}")

    tokenizer = BertTokenizer.from_pretrained("bert-base-chinese", local_files_only=True)
    model = BertForSequenceClassification.from_pretrained(
        "bert-base-chinese", num_labels=len(intent_names), local_files_only=True
    )

    dataset = IntentDataset(texts, labels, tokenizer)

    from torch.utils.data import DataLoader

    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"[train] device={device}")

    model.to(device)
    model.train()
    for epoch in range(NUM_EPOCHS):
        total_loss, total = 0.0, 0
        for batch in loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels_b = batch["labels"].to(device)
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels_b)
            loss = outputs.loss
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(labels_b)
            total += len(labels_b)
        print(f"[train] epoch {epoch + 1}/{NUM_EPOCHS} loss={total_loss / total:.4f}")

    # 保存 PyTorch 模型（便于后续继续训练）
    model.save_pretrained(str(OUT_DIR))
    tokenizer.save_pretrained(str(OUT_DIR))
    print(f"[train] saved pytorch model -> {OUT_DIR}")

    # 写 labels.json
    labels = {"id2name": id2name, "name2id": name2id}
    with open(OUT_DIR / "labels.json", "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    print(f"[train] saved labels.json ({len(intent_names)} labels)")

    # 导出 ONNX（推理端期望 input_ids + attention_mask, int64）
    model.eval()
    dummy_ids = torch.randint(0, 30522, (1, MAX_LEN), dtype=torch.long).to(device)
    dummy_mask = torch.ones((1, MAX_LEN), dtype=torch.long).to(device)
    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy_ids, dummy_mask),
            str(OUT_DIR / "classifier.onnx"),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch"},
                "attention_mask": {0: "batch"},
                "logits": {0: "batch"},
            },
            opset_version=14,
        )
    print(f"[train] exported ONNX -> {OUT_DIR / 'classifier.onnx'}")

    # 快速验证：用 onnxruntime 检查输出维度
    import onnxruntime as ort

    sess = ort.InferenceSession(str(OUT_DIR / "classifier.onnx"))
    inp = {sess.get_inputs()[0].name: dummy_ids.cpu().numpy(),
           sess.get_inputs()[1].name: dummy_mask.cpu().numpy()}
    logits = sess.run(None, inp)[0]
    print(f"[train] ONNX verify: logits shape={logits.shape} (expected [{1}, {len(intent_names)}])")
    assert logits.shape[1] == len(intent_names), "ONNX output dim mismatch"

    print("[train] DONE")


if __name__ == "__main__":
    main()
