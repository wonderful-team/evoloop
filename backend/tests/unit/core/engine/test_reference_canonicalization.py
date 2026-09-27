"""图片引用注入时公网化（canonicalization）契约测试。

锁定 reference.py 的关键行为：
- 本地图片附件（/api/ raw 链接 / uploads 相对路径）注入前并发上传 MC 换公网 URL
- image_url 块、Image Reference 文本、references 持久化三者统一使用公网 URL
- 上传失败时回退到原始 att_id（不阻断消息发送）
"""

from types import SimpleNamespace

import pytest

from app.core.engine.message.reference import reference_service

RAW_URL = "/api/v1/files/raw?project_id=0&path=uploads/ref_05_786.jpg"
PUBLIC_URL = "https://evoloop.cn/upload/chat_img/20260914/ref.png"


@pytest.fixture
def patch_upload(monkeypatch):
    """Mock evocloud 上传与 uploads 物理解析。"""
    calls = []

    async def _fake_upload(file_path, kind):  # noqa: ARG001
        calls.append(file_path)
        return PUBLIC_URL

    import app.core.evocloud as evo_pkg

    monkeypatch.setattr(
        evo_pkg,
        "evocloud_manager",
        SimpleNamespace(api=SimpleNamespace(upload_chat_media=_fake_upload)),
    )

    def _fake_resolve(normalized, member_id=0):  # noqa: ARG001
        return "/tmp/resolved.png"

    import app.api.routes.files as files_mod

    monkeypatch.setattr(files_mod, "_resolve_upload_file", _fake_resolve)
    return calls


@pytest.mark.asyncio
async def test_image_reference_canonicalized_to_public_url(patch_upload):
    ctx = await reference_service.process_references(
        message_text="请根据参考图生成木马",
        references_input=[
            {"type": "image", "target_id": RAW_URL, "target_name": "ref_05_786.jpg"}
        ],
        session=None,
        root_path=None,
    )

    # 上传发生且使用公网 URL
    assert patch_upload == ["/tmp/resolved.png"]
    # image_url 多模态块 → 公网 URL（远端 VLM 可拉取）
    image_blocks = [
        b for b in ctx.content_blocks if b.get("type") == "image_url"
    ]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"] == PUBLIC_URL
    # 文本注入 → 公网 URL（模型直接传给 image 工具即可）
    text_block = ctx.content_blocks[0]["text"]
    assert f"Image Reference: ref_05_786.jpg (Path: {PUBLIC_URL})" in text_block
    assert RAW_URL not in text_block
    # 持久化引用 → target_id 为公网 URL，source_path 保留原始链接
    assert ctx.references[0]["target_id"] == PUBLIC_URL
    assert ctx.references[0]["metadata"]["source_path"] == RAW_URL


@pytest.mark.asyncio
async def test_image_reference_upload_failure_falls_back(monkeypatch):
    async def _fail(file_path, kind):  # noqa: ARG001
        raise RuntimeError("media upload failed")

    import app.core.evocloud as evo_pkg

    monkeypatch.setattr(
        evo_pkg,
        "evocloud_manager",
        SimpleNamespace(api=SimpleNamespace(upload_chat_media=_fail)),
    )

    ctx = await reference_service.process_references(
        message_text="hi",
        references_input=[{"type": "image", "target_id": RAW_URL, "target_name": "r.jpg"}],
        session=None,
        root_path=None,
    )
    text_block = ctx.content_blocks[0]["text"]
    assert RAW_URL in text_block
    assert ctx.references[0]["target_id"] == RAW_URL


@pytest.mark.asyncio
async def test_http_image_reference_skips_upload(patch_upload):
    http_url = "https://cdn.example.com/already-public.png"
    ctx = await reference_service.process_references(
        message_text="hi",
        references_input=[{"type": "image", "target_id": http_url, "target_name": "a.png"}],
        session=None,
        root_path=None,
    )
    assert patch_upload == []  # 已是公网 URL，不重复上传
    assert ctx.references[0]["target_id"] == http_url


@pytest.mark.asyncio
async def test_dispatch_root_path_takes_priority(monkeypatch, tmp_path):
    """dispatch 转正目录（root_path）中的文件优先命中，不走 raw 端点解析。"""
    img = tmp_path / "ref.jpg"
    img.write_bytes(b"fake")

    async def _fail(file_path, kind):  # noqa: ARG001
        return PUBLIC_URL

    import app.core.evocloud as evo_pkg

    monkeypatch.setattr(
        evo_pkg,
        "evocloud_manager",
        SimpleNamespace(api=SimpleNamespace(upload_chat_media=_fail)),
    )

    canonical_map = await reference_service._canonicalize_image_urls(
        [{"type": "image", "target_id": RAW_URL, "target_name": "ref.jpg"}],
        root_path=str(tmp_path),
    )
    assert canonical_map == {RAW_URL: PUBLIC_URL}
