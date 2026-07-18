#!/usr/bin/env python3
"""
Pre-download GGUF models for Lightning Channel.

Usage:
    python scripts/download_models.py <name> [--output-dir PATH]

Examples:
    python scripts/download_models.py qwen3-4b-instruct-2507
    python scripts/download_models.py bge-base-zh-v1.5 --output-dir /path/to/gguf
"""

import argparse
import os
import sys
from pathlib import Path

import requests

GGUF_REGISTRY: dict[str, str] = {
    "qwen3-4b-instruct-2507": (
        "https://huggingface.co/Qwen/Qwen3-4B-Instruct-GGUF/resolve/main/"
        "qwen3-4b-instruct-2507-q4_k_m.gguf"
    ),
    "bge-base-zh-v1.5": (
        "https://huggingface.co/ChristianAzinn/bge-base-zh-v1.5-GGUF/resolve/main/"
        "bge-base-zh-v1.5-q4_k_m.gguf"
    ),
}


def download_gguf(name: str, output_dir: str) -> str:
    """Download a GGUF model file from HuggingFace."""
    url = GGUF_REGISTRY.get(name)
    if not url:
        raise ValueError(
            f"Unknown model: {name}. Available: {', '.join(GGUF_REGISTRY)}"
        )

    os.makedirs(output_dir, exist_ok=True)
    filename = url.rstrip("/").rsplit("/", 1)[-1]
    dest = os.path.join(output_dir, filename)

    if os.path.exists(dest):
        file_size = os.path.getsize(dest)
        if file_size > 1024:
            print(f"✓ Already exists: {dest} ({file_size / 1024**3:.1f} GB)")
            return dest

    print(f"Downloading {name} ({url.split('/')[-1]})...")
    print(f"  → {dest}")

    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    downloaded = 0

    with open(dest, "wb") as f:
        for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                sys.stdout.write(f"\r  {pct:.0f}% ({downloaded / 1024**3:.1f} GB)")
                sys.stdout.flush()

    print()
    print(f"✓ Downloaded: {dest} ({os.path.getsize(dest) / 1024**3:.1f} GB)")
    return dest


def main():
    parser = argparse.ArgumentParser(description="Download GGUF models")
    parser.add_argument(
        "name",
        nargs="?",
        default="",
        help=f"Model name. Available: {', '.join(GGUF_REGISTRY)}",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.expanduser("~"), ".evoloop", "models", "gguf"),
        help="GGUF output directory (default: ~/.evoloop/models/gguf)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available models and exit",
    )
    args = parser.parse_args()

    if args.list:
        print("Available GGUF models:")
        for name, url in GGUF_REGISTRY.items():
            filename = url.rstrip("/").rsplit("/", 1)[-1]
            print(f"  {name:30s} → {filename}")
        return

    if not args.name:
        parser.print_help()
        print("\nAvailable models:")
        for name in GGUF_REGISTRY:
            print(f"  {name}")
        return

    download_gguf(args.name, args.output_dir)


if __name__ == "__main__":
    main()
