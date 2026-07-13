class MeilisearchBackend:
    def __init__(self):
        self._initialized = False

    async def initialize(self):
        self._initialized = True

    async def search(self, query: str, limit=20):
        return []

    async def index(self, documents):
        pass

    async def close(self):
        pass