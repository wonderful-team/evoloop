#!/usr/bin/env python3
"""
验证后端代码简化
"""
import sys
from pathlib import Path

def main():
    app_dir = Path(__file__).parent.parent / "app"
    
    print("=" * 60)
    print("Phase 2 后端服务简化验证")
    print("=" * 60)
    
    # 检查关键变更
    checks = []
    
    # 1. 检查 Repository 模型
    codebase_file = app_dir / "models/codebase.py"
    with open(codebase_file) as f:
        content = f.read()
    has_is_cloud_linked = "is_cloud_linked: Mapped[bool]" in content
    has_cloud_project_id = "cloud_project_id: Mapped[int | None]" in content
    checks.append(("Repository 模型 - is_cloud_linked 字段", has_is_cloud_linked))
    checks.append(("Repository 模型 - cloud_project_id 字段", has_cloud_project_id))
    
    # 2. 检查 sync_service.py
    sync_service_file = app_dir / "domain/project/sync_service.py"
    with open(sync_service_file) as f:
        content = f.read()
    has_simplified_doc = "Simplified project sync service" in content
    has_create_repository = "async def create_repository" in content
    checks.append(("ProjectSyncService - 简化文档", has_simplified_doc))
    checks.append(("ProjectSyncService - create_repository 方法", has_create_repository))
    
    # 3. 检查 projects API
    projects_file = app_dir / "api/routes/projects.py"
    with open(projects_file) as f:
        content = f.read()
    has_import_endpoint = "async def import_project" in content
    has_link_endpoint = "async def link_to_cloud" in content
    checks.append(("Projects API - import_project 端点", has_import_endpoint))
    checks.append(("Projects API - link_to_cloud 端点", has_link_endpoint))
    
    # 4. 检查 indexing service
    indexing_file = app_dir / "domain/codebase/indexing/service.py"
    with open(indexing_file) as f:
        content = f.read()
    has_simplified_get_or_create = "Simplified - no auto cloud lookup" in content or "is_cloud_linked=is_cloud_linked" in content
    checks.append(("IndexingService - 简化逻辑", has_simplified_get_or_create))
    
    print("\n✅ 已完成:")
    all_pass = True
    for name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if not passed:
            all_pass = False
    
    print("\n📋 变更摘要:")
    print("  - Repository 表: sync_status 5状态 → is_cloud_linked 布尔值")
    print("  - ProjectSyncService: 移除自动检测，简化导入流程")
    print("  - Projects API: 新增 /import, /link, /unlink 端点")
    print("  - 移除: get_detected_projects, import_detected, ignore 等端点")
    
    print("\n" + "=" * 60)
    if all_pass:
        print("✅ Phase 2 后端服务简化完成！")
        print("=" * 60)
        return 0
    else:
        print("❌ 部分检查未通过")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
