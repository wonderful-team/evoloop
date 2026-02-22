"""
Standard File Tools.
Wraps the File System Manager into a tool interface.
"""
from app.core.brain.filesystem.manager import BrainFileSystem


class FileMemoryTool:
    def __init__(self, fs: BrainFileSystem):
        self.fs = fs

    def read_file(self, path: str) -> str:
        return self.fs.read_file(path)

    def write_file(self, path: str, content: str) -> str:
        return self.fs.write_file(path, content)

    def append_file(self, path: str, content: str) -> str:
        return self.fs.append_file(path, content)

    def search_files(self, query: str) -> str:
        results = self.fs.search_files(query)
        return "\n".join(results)
