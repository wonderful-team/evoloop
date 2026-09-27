"""Integration-style tests for media download & temp persistence.

Verifies the real helpers used by image/video generation:
- tools._media.download_bytes(url) fetches remote bytes via real httpx.
- tools._media.write_temp(data, suffix) writes bytes to a unique temp file.

Uses a local HTTP server (no external network) to serve bytes.
"""

import http.server
import threading

import pytest

from app.core.vision.tools._media import download_bytes, write_temp


@pytest.fixture
def local_server(tmp_path):
    """Serve a fixed byte payload over localhost and yield its base URL."""
    payload_file = tmp_path / "payload.bin"
    payload_file.write_bytes(b"__MEDIA_BYTES__")

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *a, directory=str(tmp_path), **kw
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


class TestDownloadBytes:
    @pytest.mark.asyncio
    async def test_downloads_exact_bytes(self, local_server):
        data = await download_bytes(f"{local_server}/payload.bin")
        assert data == b"__MEDIA_BYTES__"

    @pytest.mark.asyncio
    async def test_raises_on_missing_resource(self, local_server):
        import httpx

        with pytest.raises(httpx.HTTPStatusError):
            await download_bytes(f"{local_server}/missing.bin")


class TestWriteTemp:
    @pytest.mark.asyncio
    async def test_writes_bytes_to_unique_temp_file(self):
        path = await write_temp(b"__MEDIA_BYTES__", ".png")
        try:
            from pathlib import Path

            p = Path(path)
            assert p.read_bytes() == b"__MEDIA_BYTES__"
            assert p.suffix == ".png"
        finally:
            from app.core.vision.tools._media import remove_file

            await remove_file(path)

    @pytest.mark.asyncio
    async def test_two_writes_are_unique(self):
        path_a = await write_temp(b"a", ".bin")
        path_b = await write_temp(b"b", ".bin")
        assert path_a != path_b
        from app.core.vision.tools._media import remove_file

        for path in (path_a, path_b):
            await remove_file(path)
