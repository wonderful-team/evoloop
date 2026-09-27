"""Integration tests for the /files API routes (app/api/routes/files.py).

Exercises the real route layer while mocking service/path boundaries.
Uses tmp_path for file-system-touching endpoints where practical.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_result(content="hello"):
    return SimpleNamespace(content=content)


async def _async_return(value):
    return value


def _project_path(value):
    # 生产 get_project_path(project_id, member_id=None) 为两参签名，mock 需兼容
    return lambda *_a, **_kw: _async_return(value)


async def _search_content(q, root_path, limit=50):
    del q, limit
    return [{"file": os.path.join(root_path, "a.py"), "line": 1, "content": "match"}]


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


class TestListFiles:
    async def test_list_files(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        monkeypatch.setattr(
            "app.api.routes.files.TreeService",
            SimpleNamespace(
                get_json_tree=lambda root, rel_path="", max_depth=1: [
                    {"name": "main.py", "path": "main.py", "type": "file"},
                ]
            ),
        )
        resp = await client.get("/files/?project_id=1")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["name"] == "main.py"

    async def test_list_files_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path", _project_path(None)
        )
        resp = await client.get("/files/?project_id=999")
        assert resp.status_code == 404

    async def test_list_files_global_mode(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.get_workspace_root",
            lambda: str(Path(tempfile.mkdtemp())),
        )
        monkeypatch.setattr(
            "app.api.routes.files.TreeService",
            SimpleNamespace(
                get_json_tree=lambda root, rel_path="", max_depth=1: []
            ),
        )
        resp = await client.get("/files/?project_id=0")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_files_global_no_workspace(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.files.get_workspace_root", lambda: "")
        resp = await client.get("/files/?project_id=0")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# get_file_content
# ---------------------------------------------------------------------------


class TestFileContent:
    async def test_get_file_content(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        monkeypatch.setattr(
            "app.api.routes.files.read_file",
            lambda p: _read_result("print('hi')"),
        )
        (tmp_path / "app.py").write_text("print('hi')")
        resp = await client.get("/files/content?project_id=1&path=app.py")
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == "print('hi')"
        assert body["language"] == "py"

    async def test_get_file_content_not_found(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.get("/files/content?project_id=1&path=missing.py")
        assert resp.status_code == 404

    async def test_get_file_content_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path", _project_path(None)
        )
        resp = await client.get("/files/content?project_id=999&path=x.py")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# get_raw_file (uploads path)
# ---------------------------------------------------------------------------


class TestRawFile:
    async def test_raw_upload_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.settings",
            SimpleNamespace(CHAT_UPLOAD_DIR=tempfile.mkdtemp()),
        )
        resp = await client.get(
            "/files/raw?path=uploads/nonexistent.bin&project_id=1"
        )
        assert resp.status_code == 404

    async def test_raw_project_file_not_found(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.get(
            "/files/raw?path=missing.txt&project_id=1"
        )
        assert resp.status_code == 404

    async def test_raw_project_file(self, client, monkeypatch, tmp_path):
        (tmp_path / "photo.png").write_bytes(b"\x89PNG")
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.get(
            "/files/raw?path=photo.png&project_id=1"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/")


# ---------------------------------------------------------------------------
# open_file
# ---------------------------------------------------------------------------


class TestOpenFile:
    async def test_open_file_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path", _project_path(None)
        )
        resp = await client.post(
            "/files/open?project_id=999", json={"path": "x.py"}
        )
        assert resp.status_code == 404

    async def test_open_file_not_found(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.post(
            "/files/open?project_id=1", json={"path": "nope.py"}
        )
        assert resp.status_code == 404

    async def test_open_file_success(self, client, monkeypatch, tmp_path):
        (tmp_path / "doc.txt").write_text("hi")
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )

        monkeypatch.setattr(
            "app.api.routes.files.subprocess",
            SimpleNamespace(run=lambda *a, **kw: None),
        )
        monkeypatch.setattr("app.api.routes.files.sys", SimpleNamespace(platform="linux"))
        resp = await client.post(
            "/files/open?project_id=1", json={"path": "doc.txt"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


# ---------------------------------------------------------------------------
# create_file
# ---------------------------------------------------------------------------


class TestCreateFile:
    async def test_create_file(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        monkeypatch.setattr(
            "app.core.file.write_file",
            lambda path, content: None,
        )
        resp = await client.post(
            "/files/?project_id=1",
            json={"path": "new.py", "content": "x = 1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "new.py"
        assert body["type"] == "file"

    async def test_create_file_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path", _project_path(None)
        )
        resp = await client.post(
            "/files/?project_id=999",
            json={"path": "x.py", "content": ""},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# upload_file (chat upload)
# ---------------------------------------------------------------------------


class TestUploadFile:
    async def test_upload_file(self, client, monkeypatch, tmp_path):
        upload_dir = str(tmp_path / "uploads")
        monkeypatch.setattr(
            "app.api.routes.files.settings",
            SimpleNamespace(CHAT_UPLOAD_DIR=upload_dir),
        )
        resp = await client.post(
            "/files/upload?project_id=1",
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "test.txt"
        assert body["path"].startswith("uploads/")


# ---------------------------------------------------------------------------
# workspace_upload
# ---------------------------------------------------------------------------


class TestWorkspaceUpload:
    async def test_workspace_upload(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.post(
            "/files/workspace_upload?project_id=1",
            files={"file": ("data.bin", b"\x00\x01", "application/octet-stream")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "data.bin"
        assert body["type"] == "file"

    async def test_workspace_upload_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path", _project_path(None)
        )
        resp = await client.post(
            "/files/workspace_upload?project_id=999",
            files={"file": ("x.bin", b"\x00", "application/octet-stream")},
        )
        assert resp.status_code == 404

    async def test_workspace_upload_already_exists(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        (tmp_path / "dup.txt").write_text("old")
        resp = await client.post(
            "/files/workspace_upload?project_id=1",
            files={"file": ("dup.txt", b"new", "text/plain")},
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# search_files
# ---------------------------------------------------------------------------


class TestSearchFiles:
    async def test_search_files(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path("/tmp/proj"),
        )
        monkeypatch.setattr(
            "app.api.routes.files.FileSearcher",
            SimpleNamespace(search_content=_search_content),
        )
        resp = await client.get(
            "/files/search?q=test&project_id=1"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["content"] == "match"

    async def test_search_files_short_query(self, client, monkeypatch):
        resp = await client.get("/files/search?q=a&project_id=1")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# search_files_by_name
# ---------------------------------------------------------------------------


class TestSearchByName:
    async def test_search_name(self, client, monkeypatch, tmp_path):
        (tmp_path / "README.md").write_text("hi")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "code.py").write_text("x")
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.get(
            "/files/search_name?q=README&project_id=1"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert any(r["name"] == "README.md" for r in body)

    async def test_search_name_empty_query(self, client, monkeypatch):
        resp = await client.get("/files/search_name?q=&project_id=1")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# create_directory
# ---------------------------------------------------------------------------


class TestMkdir:
    async def test_mkdir(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.post(
            "/files/mkdir?project_id=1",
            json={"path": "new_dir"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "new_dir"
        assert body["type"] == "directory"
        assert (tmp_path / "new_dir").is_dir()

    async def test_mkdir_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path", _project_path(None)
        )
        resp = await client.post(
            "/files/mkdir?project_id=999", json={"path": "x"}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# move_file
# ---------------------------------------------------------------------------


class TestMoveFile:
    async def test_move_file(self, client, monkeypatch, tmp_path):
        (tmp_path / "old.txt").write_text("data")
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.post(
            "/files/move?project_id=1",
            json={"source_path": "old.txt", "target_path": "new.txt"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "new.txt"
        assert body["type"] == "file"

    async def test_move_source_not_found(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.post(
            "/files/move?project_id=1",
            json={"source_path": "nope.txt", "target_path": "dest.txt"},
        )
        assert resp.status_code == 404

    async def test_move_target_exists(self, client, monkeypatch, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.post(
            "/files/move?project_id=1",
            json={"source_path": "a.txt", "target_path": "b.txt"},
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------


class TestDeleteFile:
    async def test_delete_file(self, client, monkeypatch, tmp_path):
        (tmp_path / "del.txt").write_text("bye")
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.delete(
            "/files/?project_id=1&path=del.txt"
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_delete_already_gone(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path",
            _project_path(str(tmp_path)),
        )
        resp = await client.delete(
            "/files/?project_id=1&path=ghost.txt"
        )
        assert resp.status_code == 200
        assert "already deleted" in resp.json()["message"].lower()

    async def test_delete_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.get_project_path", _project_path(None)
        )
        resp = await client.delete("/files/?project_id=999&path=x.txt")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# read_any_file
# ---------------------------------------------------------------------------


class TestReadAnyFile:
    async def test_read_any_file(self, client, monkeypatch, tmp_path):
        target = tmp_path / "readme.md"
        target.write_text("# Hi")
        monkeypatch.setattr(
            "app.api.routes.files.resolve_path",
            lambda p, base_path=None: str(target),
        )
        monkeypatch.setattr(
            "app.api.routes.files._assert_path_allowed", lambda p: None
        )
        monkeypatch.setattr(
            "app.api.routes.files.read_file",
            lambda p: _read_result("# Hi"),
        )
        resp = await client.post(
            "/files/read", json={"path": str(target)}
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "# Hi"

    async def test_read_any_file_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.resolve_path",
            lambda p, base_path=None: "/tmp/no_such_file",
        )
        monkeypatch.setattr(
            "app.api.routes.files._assert_path_allowed", lambda p: None
        )
        resp = await client.post(
            "/files/read", json={"path": "/tmp/no_such_file"}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# download_any_file
# ---------------------------------------------------------------------------


class TestDownloadFile:
    async def test_download_file(self, client, monkeypatch, tmp_path):
        target = tmp_path / "archive.zip"
        target.write_bytes(b"PK\x03\x04")
        monkeypatch.setattr(
            "app.api.routes.files.resolve_path",
            lambda p, base_path=None: str(target),
        )
        monkeypatch.setattr(
            "app.api.routes.files._assert_path_allowed", lambda p: None
        )
        resp = await client.post(
            "/files/download", json={"path": str(target)}
        )
        assert resp.status_code == 200

    async def test_download_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.files.resolve_path",
            lambda p, base_path=None: "/tmp/nope",
        )
        monkeypatch.setattr(
            "app.api.routes.files._assert_path_allowed", lambda p: None
        )
        resp = await client.post(
            "/files/download", json={"path": "/tmp/nope"}
        )
        assert resp.status_code == 404
