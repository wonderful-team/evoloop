#!/usr/bin/env python3
"""
Pre-download embedding models to local cache.

Usage:
    python scripts/download_models.py [model_name] [--endpoint URL]

Example:
    python scripts/download_models.py nomic-ai/nomic-embed-text-v1.5
    python scripts/download_models.py nomic-ai/nomic-embed-text-v1.5 --endpoint https://hf-mirror.com
"""

import os
import sys
import argparse


def download_model(model_name: str, endpoint: str | None = None) -> None:
    """Download a SentenceTransformer model to local cache."""
    # Ensure cache directories are set (must match config.py)
    models_dir = os.path.expanduser("~/.evoloop/models")
    os.environ.setdefault("HF_HOME", os.path.join(models_dir, "huggingface"))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.join(models_dir, "sentence_transformers"))

    # Temporarily allow network access for downloading.
    # HF_HUB_OFFLINE=1 is set in config.py, but we need to download here.
    original_hf_offline = os.environ.pop("HF_HUB_OFFLINE", None)

    # Set HuggingFace endpoint (mirror) for downloading.
    original_hf_endpoint = os.environ.get("HF_ENDPOINT")
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint

    try:
        from sentence_transformers import SentenceTransformer

        print(f"Downloading model: {model_name}")
        print(f"  HF_HOME: {os.environ.get('HF_HOME')}")
        print(f"  SENTENCE_TRANSFORMERS_HOME: {os.environ.get('SENTENCE_TRANSFORMERS_HOME')}")
        print(f"  HF_ENDPOINT: {os.environ.get('HF_ENDPOINT')}")

        # local_files_only=False allows downloading.
        # trust_remote_code=True is required for Nomic models.
        model = SentenceTransformer(
            model_name,
            device="cpu",
            trust_remote_code=True,
            local_files_only=False,
        )
        print(f"✓ Model downloaded and cached successfully: {model_name}")
    finally:
        if original_hf_offline is not None:
            os.environ["HF_HUB_OFFLINE"] = original_hf_offline
        if endpoint:
            if original_hf_endpoint is not None:
                os.environ["HF_ENDPOINT"] = original_hf_endpoint
            else:
                os.environ.pop("HF_ENDPOINT", None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-download embedding models")
    parser.add_argument(
        "model",
        nargs="?",
        default="nomic-ai/nomic-embed-text-v1.5",
        help="Model name to download (default: nomic-ai/nomic-embed-text-v1.5)",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="HuggingFace endpoint mirror URL (e.g. https://hf-mirror.com)",
    )
    args = parser.parse_args()

    download_model(args.model, endpoint=args.endpoint)


if __name__ == "__main__":
    main()
