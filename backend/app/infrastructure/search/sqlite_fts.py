class SQLiteFTSBackend:
    def __init__(self):
        self._initialized = False

    async def initialize(self):
        self._initialized = True

    async def search(self, query: str, **kwargs):
        return []

    async def index(self, documents):
        pass

    async def close(self):
        pass
