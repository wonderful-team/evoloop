
import asyncio
import os
import sys

# Ensure app is in path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.domain.codebase.indexing.vectors.factory import EmbedderFactory
from app.domain.system.service import SystemConfigService


def main():
    print("--- Configuration Check ---")
    print(f"Env Settings EMBEDDING_MODEL_NAME: {settings.EMBEDDING_MODEL_NAME}")
    print(f"Env Settings OPENAI_BASE_URL: {settings.OPENAI_BASE_URL}")
    print(f"Env Settings ADAPTER: {settings.OPENAI_BASE_URL}") # Duplicated?

    try:
        # SystemConfigService.get_value is synchronous
        provider = SystemConfigService.get_value("EMBEDDING_PROVIDER")
        model = SystemConfigService.get_value("EMBEDDING_MODEL")
        base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL")
        api_key = SystemConfigService.get_value("EMBEDDING_API_KEY")

        print(f"DB Config EMBEDDING_PROVIDER: {provider}")
        print(f"DB Config EMBEDDING_MODEL: {model}")
        print(f"DB Config EMBEDDING_BASE_URL: {base_url}")
        print(f"DB Config EMBEDDING_API_KEY: {'[REDACTED]' if api_key else 'None'}")

    except Exception as e:
        print(f"Could not fetch DB config: {e}")

    print("\n--- Reproduction Attempt ---")
    try:
        # get_embedder is synchronous? Yes.
        embedder = EmbedderFactory.get_embedder()
        print(f"Embedder Created: {embedder}")
        if hasattr(embedder, 'model'):
            print(f"Embedder Model: {embedder.model}")
        if hasattr(embedder, 'client'):
             print(f"Embedder Base URL: {embedder.client.base_url}")

        print("Attempting to embed 'test'...")
        # embed_query is async
        result = asyncio.run(embedder.embed_query("test"))
        print(f"Success! Embedding length: {len(result)}")
    except Exception as e:
        print(f"Caught Expected Error: {e}")

if __name__ == "__main__":
    main()
