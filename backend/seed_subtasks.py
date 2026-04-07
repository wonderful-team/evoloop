#!/usr/bin/env python3
"""
Seed script to create demo subtask data for testing.

Usage:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    python seed_subtasks.py
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, '.')

os.environ['TASK_QUEUE_BACKEND'] = 'huey'

from app.infrastructure.database.sql.database import session_scope
from app.domain.project.requirements.models import (
    ProjectRequirementDocument,
    ProjectRequirementAnalysis,
    ProjectRequirementTask
)


def utcnow():
    return datetime.now(timezone.utc)


async def seed_demo_data():
    """Create demo project with hierarchical tasks."""
    
    async with session_scope() as session:
        # 1. Find or create a requirement document
        print("Finding existing requirement document...")
        
        # Get first available document
        from sqlalchemy import select
        result = await session.execute(
            select(ProjectRequirementDocument).limit(1)
        )
        doc = result.scalar_one_or_none()
        
        if not doc:
            print("No requirement document found. Creating one...")
            doc = ProjectRequirementDocument(
                id=str(uuid.uuid4()),
                project_id=1,
                file_name="demo-requirements.md",
                file_path="/tmp/demo-requirements.md",
                file_type="text/markdown",
                file_size=1024,
                status="confirmed",
                created_at=utcnow(),
                updated_at=utcnow()
            )
            session.add(doc)
            await session.flush()
            print(f"Created document: {doc.id}")
        else:
            print(f"Using existing document: {doc.id} (project_id: {doc.project_id})")
        
        project_id = doc.project_id
        
        # 2. Create an analysis
        print("\nCreating analysis...")
        analysis = ProjectRequirementAnalysis(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            project_id=project_id,
            status="confirmed",
            version=1,
            analysis_data={
                "title": "Demo Analysis",
                "summary": "Demo analysis for testing subtasks"
            },
            confirmed_at=utcnow(),
            created_at=utcnow()
        )
        session.add(analysis)
        await session.flush()
        print(f"Created analysis: {analysis.id}")
        
        # 3. Create root task (parent)
        print("\nCreating root task...")
        root_task = ProjectRequirementTask(
            id=str(uuid.uuid4()),
            analysis_id=analysis.id,
            project_id=project_id,
            parent_id=None,
            status="in_progress",
            progress=30,
            task_data={
                "title": "实现用户认证系统",
                "description": "完整的用户登录、注册、权限管理功能",
                "priority": "high",
                "estimated_hours": 40,
                "category": "backend",
                "tags": ["auth", "security", "api"],
                "requirement_refs": ["FR-001", "FR-002"],
                "acceptance_criteria": [
                    "用户可以使用邮箱和密码注册",
                    "用户可以使用邮箱和密码登录",
                    "支持 JWT Token 认证"
                ]
            },
            sync_status="synced",
            synced_at=utcnow(),
            created_at=utcnow(),
            updated_at=utcnow()
        )
        session.add(root_task)
        await session.flush()
        print(f"Created root task: {root_task.id}")
        
        # 4. Create subtasks
        print("\nCreating subtasks...")
        
        subtasks_data = [
            {
                "title": "设计数据库用户表",
                "description": "创建用户表结构，包含基本信息、密码哈希、状态字段",
                "priority": "high",
                "estimated_hours": 4,
                "category": "database",
                "progress": 100,
                "status": "completed"
            },
            {
                "title": "实现用户注册 API",
                "description": "POST /api/auth/register 接口，包含参数校验、密码加密",
                "priority": "high",
                "estimated_hours": 6,
                "category": "backend",
                "progress": 80,
                "status": "in_progress"
            },
            {
                "title": "实现用户登录 API",
                "description": "POST /api/auth/login 接口，返回 JWT Token",
                "priority": "high",
                "estimated_hours": 4,
                "category": "backend",
                "progress": 50,
                "status": "in_progress"
            },
            {
                "title": "实现 JWT 中间件",
                "description": "验证 JWT Token，保护需要认证的接口",
                "priority": "medium",
                "estimated_hours": 4,
                "category": "backend",
                "progress": 0,
                "status": "pending"
            },
            {
                "title": "前端登录页面",
                "description": "React 登录表单，包含邮箱、密码输入和验证",
                "priority": "medium",
                "estimated_hours": 8,
                "category": "frontend",
                "progress": 0,
                "status": "pending"
            }
        ]
        
        created_subtasks = []
        for data in subtasks_data:
            subtask = ProjectRequirementTask(
                id=str(uuid.uuid4()),
                analysis_id=analysis.id,
                project_id=project_id,
                parent_id=root_task.id,
                status=data["status"],
                progress=data["progress"],
                task_data={
                    "title": data["title"],
                    "description": data["description"],
                    "priority": data["priority"],
                    "estimated_hours": data["estimated_hours"],
                    "category": data["category"],
                    "tags": [],
                    "requirement_refs": [],
                    "acceptance_criteria": []
                },
                sync_status="synced",
                synced_at=utcnow(),
                created_at=utcnow(),
                updated_at=utcnow()
            )
            session.add(subtask)
            created_subtasks.append(subtask)
        
        await session.flush()
        print(f"Created {len(created_subtasks)} subtasks")
        
        # 5. Create nested subtask (child of child)
        print("\nCreating nested subtask...")
        first_subtask = created_subtasks[0]  # Under "设计数据库用户表"
        
        nested_subtask = ProjectRequirementTask(
            id=str(uuid.uuid4()),
            analysis_id=analysis.id,
            project_id=project_id,
            parent_id=first_subtask.id,
            status="completed",
            progress=100,
            task_data={
                "title": "编写数据库迁移脚本",
                "description": "使用 Alembic 创建用户表迁移脚本",
                "priority": "high",
                "estimated_hours": 2,
                "category": "database",
                "tags": ["migration"],
                "requirement_refs": [],
                "acceptance_criteria": [
                    "迁移脚本可以正常执行",
                    "支持回滚操作"
                ]
            },
            sync_status="synced",
            synced_at=utcnow(),
            created_at=utcnow(),
            updated_at=utcnow()
        )
        session.add(nested_subtask)
        await session.flush()
        print(f"Created nested subtask: {nested_subtask.id}")
        
        # Print summary
        print("\n" + "="*60)
        print("SEED DATA CREATED SUCCESSFULLY")
        print("="*60)
        print(f"Project ID: {project_id}")
        print(f"Document ID: {doc.id}")
        print(f"Analysis ID: {analysis.id}")
        print(f"Root Task ID: {root_task.id}")
        print(f"\nSubtasks created: {len(created_subtasks)}")
        for i, st in enumerate(created_subtasks, 1):
            print(f"  {i}. {st.task_data['title']} ({st.progress}%)")
        print(f"\nNested subtask: {nested_subtask.task_data['title']} ({nested_subtask.progress}%)")
        print("\nYou can now test the frontend with:")
        print(f"  - Project ID: {project_id}")
        print(f"  - Root Task ID (for getTaskTree): {root_task.id}")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
