#!/usr/bin/env python3
"""
Wiki Tools — Filesystem-Backend Integration Test

Validates the new title-addressed, filesystem-backed wiki tools:
  - write_wiki_page (create + update + TOC slug)
  - read_wiki_page (by title)
  - edit_wiki_page (incremental edit)
  - list_wiki_pages (filesystem → DB sync)
"""

import asyncio
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

TEST_PROJECT_ID = 999999  # Isolated test project
TEST_WIKI_DIR = None  # Set during setup


async def _setup():
    """Initialize DB and create a temp project directory."""
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    # Create a temp directory as the "project path"
    global TEST_WIKI_DIR
    TEST_WIKI_DIR = tempfile.mkdtemp(prefix="wiki_tools_test_")

    # Clean any existing wiki pages for this test project
    from sqlmodel import delete, Session
    from app.models.wiki import WikiPage

    with Session(db_resource_manager.sync_engine) as session:
        session.exec(delete(WikiPage).where(WikiPage.project_id == TEST_PROJECT_ID))
        session.commit()

    print(f"[Setup] Temp project path: {TEST_WIKI_DIR}")
    return TEST_WIKI_DIR


def _teardown():
    """Remove temp directory."""
    if TEST_WIKI_DIR and os.path.exists(TEST_WIKI_DIR):
        shutil.rmtree(TEST_WIKI_DIR)
        print(f"[Teardown] Removed {TEST_WIKI_DIR}")


async def _mock_context(project_path: str):
    """Set up thread context so get_working_directory() returns our temp path."""
    import contextvars
    from app.core.context import thread_context_store
    from app.core.context.manager import ContextManager, EvoContext, _context_var

    thread_id = f"wiki-tool-test-{int(time.time())}"
    thread_context_store.set_working_directory(thread_id, project_path)

    # Set project_id in context so _resolve_wiki_project_id works
    ctx = EvoContext(
        request_id=thread_id,
        project_id=TEST_PROJECT_ID,
        thread_id=thread_id,
        working_directory=project_path,
    )
    token = ContextManager.set(ctx)

    return thread_id, token


async def test_write_and_read():
    """Test basic write + read cycle."""
    print("\n--- Test: write + read ---")
    from app.domain.tools.wiki_tools import write_wiki_page, read_wiki_page

    title = "项目概述"
    content = "# 项目概述\n\n这是一个测试项目。\n"

    # Write (StructuredTool needs ainvoke with dict)
    result = await write_wiki_page.ainvoke({"title": title, "content": content})
    print(f"  write result: {result}")
    assert "created" in result.lower() or "updated" in result.lower(), f"Unexpected result: {result}"

    # Read back
    result = await read_wiki_page.ainvoke({"title": title})
    print(f"  read result snippet: {result[:100]}...")
    assert "项目概述" in result, "Read did not return expected content"
    assert "这是一个测试项目" in result, "Content mismatch"

    # Verify file exists
    expected_file = os.path.join(TEST_WIKI_DIR, "docs/wiki", "项目概述.md")
    assert os.path.exists(expected_file), f"File not found: {expected_file}"
    print(f"  ✓ File exists: {expected_file}")

    # Verify DB record
    from sqlmodel import Session, select
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.models.wiki import WikiPage

    with Session(db_resource_manager.sync_engine) as session:
        page = session.exec(
            select(WikiPage).where(
                WikiPage.project_id == TEST_PROJECT_ID,
                WikiPage.title == title,
            )
        ).first()
        assert page is not None, "DB record not found"
        assert page.slug == "项目概述", f"Unexpected slug: {page.slug}"
        assert page.content == content, "DB content mismatch"
        print(f"  ✓ DB record synced: slug={page.slug}")

    print("  ✅ write + read passed")


async def test_update_existing():
    """Test updating an existing page reuses slug."""
    print("\n--- Test: update existing page ---")
    from app.domain.tools.wiki_tools import write_wiki_page

    title = "项目概述"
    new_content = "# 项目概述\n\n这是一个测试项目。\n\n已更新。\n"

    result = await write_wiki_page.ainvoke({"title": title, "content": new_content})
    print(f"  write result: {result}")
    assert "updated" in result.lower(), f"Expected 'updated', got: {result}"

    # Verify only one file exists (no duplicate)
    wiki_dir = os.path.join(TEST_WIKI_DIR, "docs/wiki")
    files = [f for f in os.listdir(wiki_dir) if f.endswith(".md")]
    project_files = [f for f in files if "项目" in f or "概述" in f]
    print(f"  wiki files: {files}")
    assert len(project_files) == 1, f"Expected 1 file, got {len(project_files)}: {project_files}"

    # Verify DB: only one record for this title
    from sqlmodel import Session, select
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.models.wiki import WikiPage

    with Session(db_resource_manager.sync_engine) as session:
        pages = session.exec(
            select(WikiPage).where(
                WikiPage.project_id == TEST_PROJECT_ID,
                WikiPage.title == title,
            )
        ).all()
        assert len(pages) == 1, f"Expected 1 DB record, got {len(pages)}"
        print(f"  ✓ No duplicate records")

    print("  ✅ update existing passed")


async def test_edit_wiki_page():
    """Test incremental edit."""
    print("\n--- Test: edit_wiki_page ---")
    from app.domain.tools.wiki_tools import write_wiki_page, edit_wiki_page, read_wiki_page

    title = "API 文档"
    content = "# API 文档\n\n系统使用 REST API。\n\n## 认证\n使用 OAuth2。\n"
    await write_wiki_page.ainvoke({"title": title, "content": content})

    # Incremental edit
    result = await edit_wiki_page.ainvoke({
        "title": title,
        "old_string": "使用 OAuth2。",
        "new_string": "使用 OAuth2 + JWT。",
    })
    print(f"  edit result: {result}")
    assert "success" in result.lower() or "updated" in result.lower(), f"Edit failed: {result}"

    # Read back
    result = await read_wiki_page.ainvoke({"title": title})
    assert "OAuth2 + JWT" in result, "Edit not applied"
    assert "REST API" in result, "Unrelated content lost"
    print(f"  ✓ Incremental edit applied correctly")

    print("  ✅ edit_wiki_page passed")


async def test_edit_not_found():
    """Test edit on non-existent page."""
    print("\n--- Test: edit non-existent page ---")
    from app.domain.tools.wiki_tools import edit_wiki_page

    result = await edit_wiki_page.ainvoke({
        "title": "不存在的页面",
        "old_string": "foo",
        "new_string": "bar",
    })
    print(f"  edit result: {result}")
    assert "not found" in result.lower() or "找不到" in result, f"Expected not-found error: {result}"
    print("  ✅ edit not-found passed")


async def test_toc_slug():
    """Test TOC page gets slug='toc' automatically."""
    print("\n--- Test: TOC slug auto-mapping ---")
    from app.domain.tools.wiki_tools import write_wiki_page
    from sqlmodel import Session, select
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.models.wiki import WikiPage

    title = "目录"
    content = "# 目录\n\n- 项目概述\n- API 文档\n"
    result = await write_wiki_page.ainvoke({"title": title, "content": content})
    print(f"  write result: {result}")

    # Verify DB: slug should be 'toc'
    with Session(db_resource_manager.sync_engine) as session:
        page = session.exec(
            select(WikiPage).where(
                WikiPage.project_id == TEST_PROJECT_ID,
                WikiPage.title == title,
            )
        ).first()
        assert page is not None, "DB record not found"
        assert page.slug == "toc", f"Expected slug='toc', got '{page.slug}'"
        print(f"  ✓ TOC slug auto-mapped to 'toc'")

    # Verify file
    expected_file = os.path.join(TEST_WIKI_DIR, "docs/wiki", "toc.md")
    assert os.path.exists(expected_file), f"TOC file not found: {expected_file}"
    print(f"  ✓ TOC file exists: {expected_file}")

    print("  ✅ TOC slug passed")


async def test_list_sync():
    """Test list_wiki_pages syncs filesystem to DB."""
    print("\n--- Test: list_wiki_pages filesystem sync ---")
    from app.domain.tools.wiki_tools import list_wiki_pages
    from sqlmodel import delete, Session
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.models.wiki import WikiPage

    # Create a file directly on filesystem (orphan file)
    wiki_dir = os.path.join(TEST_WIKI_DIR, "docs/wiki")
    os.makedirs(wiki_dir, exist_ok=True)
    orphan_file = os.path.join(wiki_dir, "orphan-page.md")
    with open(orphan_file, "w", encoding="utf-8") as f:
        f.write("# Orphan Page\n\nThis page was created outside the tool.\n")

    # Delete its DB record (simulate out-of-sync)
    with Session(db_resource_manager.sync_engine) as session:
        session.exec(
            delete(WikiPage).where(
                WikiPage.project_id == TEST_PROJECT_ID,
                WikiPage.slug == "orphan-page",
            )
        )
        session.commit()

    # List should sync it back
    result = await list_wiki_pages.ainvoke({})
    print(f"  list result snippet: {result[:200]}...")
    assert "Orphan Page" in result or "orphan-page" in result, f"Orphan page not synced: {result}"

    # Verify DB now has it
    from sqlmodel import select as sqlselect
    with Session(db_resource_manager.sync_engine) as session:
        page = session.exec(
            sqlselect(WikiPage).where(
                WikiPage.project_id == TEST_PROJECT_ID,
                WikiPage.slug == "orphan-page",
            )
        ).first()
        assert page is not None, "Orphan page not synced to DB"
        assert "created outside the tool" in page.content, "Content mismatch after sync"
        print(f"  ✓ Orphan file synced to DB: title={page.title}")

    print("  ✅ list sync passed")


async def test_parent_title():
    """Test parent_title hierarchy."""
    print("\n--- Test: parent_title hierarchy ---")
    from app.domain.tools.wiki_tools import write_wiki_page
    from sqlmodel import Session, select
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.models.wiki import WikiPage

    parent_title = "后端架构"
    child_title = "数据库设计"

    await write_wiki_page.ainvoke({"title": parent_title, "content": "# 后端架构\n"})
    await write_wiki_page.ainvoke({"title": child_title, "content": "# 数据库设计\n", "parent_title": parent_title})

    with Session(db_resource_manager.sync_engine) as session:
        parent = session.exec(
            select(WikiPage).where(
                WikiPage.project_id == TEST_PROJECT_ID,
                WikiPage.title == parent_title,
            )
        ).first()
        child = session.exec(
            select(WikiPage).where(
                WikiPage.project_id == TEST_PROJECT_ID,
                WikiPage.title == child_title,
            )
        ).first()

        assert parent is not None, "Parent not found"
        assert child is not None, "Child not found"
        assert child.parent_id == parent.id, f"Hierarchy broken: child.parent_id={child.parent_id}, parent.id={parent.id}"
        print(f"  ✓ Hierarchy correct: '{child_title}' → parent '{parent_title}'")

    print("  ✅ parent_title passed")


async def main():
    project_path = await _setup()
    thread_id, ctx_token = await _mock_context(project_path)

    try:
        await test_write_and_read()
        await test_update_existing()
        await test_edit_wiki_page()
        await test_edit_not_found()
        await test_toc_slug()
        await test_list_sync()
        await test_parent_title()

        print("\n" + "=" * 50)
        print("🎉 ALL TOOL TESTS PASSED")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    finally:
        _teardown()
        # Restore context
        from app.core.context.manager import _context_var
        _context_var.reset(ctx_token)


if __name__ == "__main__":
    asyncio.run(main())
