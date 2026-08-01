#!/usr/bin/env python3
"""
Train a BERT-based intent classifier from intents.yaml.
Outputs: onnx model + label mapping + optional Core ML model.

Usage:
    uv run python scripts/train_intent_classifier.py \
        --data data/intents.yaml \
        --output models/action_classifier
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import torch
import yaml
from datasets import Dataset
from transformers import (
    BertForSequenceClassification,
    BertTokenizer,
    Trainer,
    TrainingArguments,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_data(path: str) -> tuple[list[str], list[str]]:
    """Load intents from YAML. Returns (texts, label_names)."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    texts: list[str] = []
    labels: list[str] = []
    for intent_name, examples in raw["intents"].items():
        if not isinstance(examples, list):
            continue
        for ex in examples:
            if isinstance(ex, str) and ex.strip():
                texts.append(ex.strip())
                labels.append(intent_name)
    return texts, labels


def build_label_map(names: list[str]) -> tuple[dict[str, int], dict[int, str]]:
    """Build str→int and int→str mappings sorted by name for determinism."""
    unique = sorted(set(names))
    name2id = {n: i for i, n in enumerate(unique)}
    id2name = {i: n for n, i in name2id.items()}
    return name2id, id2name


def main():
    parser = argparse.ArgumentParser(description="Train BERT intent classifier")
    parser.add_argument("--data", default="data/intents.yaml", help="Training data YAML")
    parser.add_argument("--output", default="models/action_classifier", help="Output directory")
    parser.add_argument("--model-name", default="bert-base-chinese", help="Base model")
    parser.add_argument("--epochs", type=int, default=10, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=16, help="Per-device batch size")
    parser.add_argument("--lr", type=float, default=3e-5, help="Learning rate")
    parser.add_argument("--max-length", type=int, default=32, help="Max token length")
    parser.add_argument("--export-onnx", action=argparse.BooleanOptionalAction, default=True, help="Export ONNX")
    parser.add_argument("--export-coreml", action="store_true", help="Export Core ML (macOS only)")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load data ──
    logger.info("Loading data from %s", args.data)
    texts, labels = load_data(args.data)
    logger.info("Loaded %d examples across %d intent classes",
                len(texts), len(set(labels)))

    name2id, id2name = build_label_map(labels)
    label_ids = [name2id[l] for l in labels]

    # Save label mapping
    mapping_path = out_dir / "labels.json"
    with open(mapping_path, "w") as f:
        json.dump({"id2name": id2name, "name2id": name2id}, f, ensure_ascii=False, indent=2)
    logger.info("Label mapping saved to %s (%d classes)", mapping_path, len(id2name))

    # ── 2. Tokenize ──
    logger.info("Loading tokenizer: %s", args.model_name)
    tokenizer = BertTokenizer.from_pretrained(args.model_name)

    dataset = Dataset.from_dict({"text": texts, "label": label_ids})

    def tokenize_fn(examples):
        return tokenizer(
            examples["text"],
            padding="max_length",
            truncation=True,
            max_length=args.max_length,
        )

    dataset = dataset.map(tokenize_fn, batched=True)
    dataset = dataset.train_test_split(test_size=0.1, seed=42)
    logger.info("Train: %d, Eval: %d", len(dataset["train"]), len(dataset["test"]))

    # ── 3. Train ──
    logger.info("Loading model: %s (%d labels)", args.model_name, len(id2name))
    model = BertForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=len(id2name),
        hidden_dropout_prob=0.1,
    )

    training_args = TrainingArguments(
        output_dir=str(out_dir / "checkpoints"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="loss",
        greater_is_better=False,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["test"],
    )

    trainer.train()

    # ── 4. Save HuggingFace model ──
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    logger.info("Model saved to %s", out_dir)

    # ── 5. Export ONNX ──
    if args.export_onnx:
        logger.info("Exporting ONNX...")
        import onnxruntime as ort

        model.eval()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)

        dummy = tokenizer(
            "测试文本",
            padding="max_length",
            truncation=True,
            max_length=args.max_length,
            return_tensors="pt",
        )

        torch.onnx.export(
            model,
            (dummy["input_ids"].to(device), dummy["attention_mask"].to(device)),
            str(out_dir / "classifier.onnx"),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch_size"},
                "attention_mask": {0: "batch_size"},
            },
            opset_version=18,
        )
        logger.info("ONNX model exported to %s/classifier.onnx", out_dir)

        # Validate ONNX
        session = ort.InferenceSession(str(out_dir / "classifier.onnx"))
        inputs = {
            session.get_inputs()[0].name: dummy["input_ids"].numpy(),
            session.get_inputs()[1].name: dummy["attention_mask"].numpy(),
        }
        output = session.run(None, inputs)
        logger.info("ONNX validation OK — output shape: %s", output[0].shape)

    # ── 6. Export Core ML (macOS ANE) ──
    if args.export_coreml:
        try:
            import coremltools as ct

            logger.info("Exporting Core ML...")
            device = torch.device("cpu")  # Core ML export needs CPU
            model.to(device)
            model.eval()

            traced = torch.jit.trace(
                model.bert,
                (dummy["input_ids"].to("cpu"), dummy["attention_mask"].to("cpu")),
            )
            mlmodel = ct.convert(
                traced,
                inputs=[ct.TensorType(
                    name="input_ids",
                    shape=(1, args.max_length),
                    dtype=int,
                )],
                compute_units=ct.ComputeUnit.ALL,
                minimum_deployment_target=ct.target.macOS,
            )
            mlmodel.save(str(out_dir / "classifier.mlpackage"))
            logger.info("Core ML model exported to %s/classifier.mlpackage", out_dir)
        except Exception as e:
            logger.warning("Core ML export failed (skipping): %s", e)

    logger.info("Done. Model files in %s:", out_dir)
    for f in out_dir.iterdir():
        if not f.is_dir():
            logger.info("  %s (%d bytes)", f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
