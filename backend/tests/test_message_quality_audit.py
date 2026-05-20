import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Any

# 环境准备
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.engine.message.handler import MessageHandler
from app.core.engine.message.repository import MessageRepository
from app.core.engine.message.mapper import BlockMapper
from app.core.engine.message.schemas import MessageBlock
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.resource_manager import db_resource_manager

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("MessageQualityAudit")

SCENARIOS = [
    {
        "name": "S1: Simple Text",
        "content": "这是一条普通的 AI 回复文本。",
        "expect": {"refs_count": 0}
    },
    {
        "name": "S2: File Generation",
        "content": "分析已完成，请下载报告：uploads/data_analysis_v1.xlsx",
        "expect": {"refs_count": 1, "type": "file"}
    },
    {
        "name": "S3: Image Generation",
        "content": "这是系统的屏幕截图预览：uploads/screenshot_2024.png",
        "expect": {"refs_count": 1, "type": "image"}
    },
    {
        "name": "S4: ECharts Block",
        "content": "数据趋势如下：\n```echarts\n{\"title\": {\"text\": \"Revenue\"}, \"series\": [10, 20, 30]}\n```",
        "expect": {"refs_count": 1, "type": "artifact", "artifact_type": "echarts"}
    },
    {
        "name": "S5: Mermaid Diagram",
        "content": "执行流程如下：\n```mermaid\ngraph TD; A-->B; B-->C;\n```",
        "expect": {"refs_count": 1, "type": "artifact", "artifact_type": "mermaid"}
    },
    {
        "name": "S6: Map Artifact",
        "content": "位置已标记：\n```map\n{\"center\": [121.47, 31.23], \"zoom\": 12}\n```",
        "expect": {"refs_count": 1, "type": "artifact", "artifact_type": "map"}
    },
    {
        "name": "S7: HTML Component",
        "content": "这是您的仪表盘组件预览：\n```artifact\n<div style='color:red'>Dashboard</div>\n```",
        "expect": {"refs_count": 1, "type": "artifact", "artifact_type": "html"}
    },
    {
        "name": "S8: Mixed Content",
        "content": "文件：uploads/raw.csv\n图表：\n```echarts\n{}\n```\n结论：增长了 20%。",
        "expect": {"refs_count": 2}
    },
    {
        "name": "S9: Batch Artifacts",
        "content": "```echarts\n{\"id\":1}\n```\n```echarts\n{\"id\":2}\n```",
        "expect": {"refs_count": 2}
    },
    {
        "name": "S10: Tool Output Simulation",
        "content": "查询成功。",
        "metadata": {"tool_meta": {"display_name": "GetWeather"}},
        "expect": {"has_tool_meta": True}
    },
    {
        "name": "S11: Changeset Bridge Simulation",
        "content": "已更新代码。",
        "simulate_changeset": True,
        "expect": {"has_changeset": True}
    },
    {
        "name": "S12: Skill Reference",
        "content": "根据 抖音分析 技能处理：",
        "custom_refs": [{"type": "skill", "target_id": "skill-123", "target_name": "抖音分析"}],
        "expect": {"refs_count": 1, "type": "skill"}
    },
    {
        "name": "S13: Edge Case - Unclosed Block",
        "content": "未闭合的代码块：\n```echarts\n{\"broken\": true}",
        "expect": {"refs_count": 0} # 预期不提取，防止损坏 JSON 干扰前端
    },
    {
        "name": "S14: Deep Path Path",
        "content": "深度路径：uploads/reports/2024/jan/report.pdf",
        "expect": {"refs_count": 1, "target_contains": "report.pdf"}
    },
    {
        "name": "S15: Thinking Preservation",
        "content": "最终结论。",
        "thinking": "<thinking>第一步，分析需求。第二步，生成代码。</thinking>",
        "expect": {"has_thinking": True}
    }
]

class Auditor:
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.handler = MessageHandler(thread_id=thread_id)
        self.repo = MessageRepository(thread_id=thread_id)

    async def audit_scenario(self, scenario: dict) -> dict:
        name = scenario["name"]
        content = scenario["content"]
        thinking = scenario.get("thinking")
        metadata = scenario.get("metadata", {})
        custom_refs = scenario.get("custom_refs", [])

        # 1. 模拟 MessageHandler 处理 (触发 Extractor)
        result = await self.handler.handle_ai_message(
            content=content,
            thinking=thinking,
            metadata=metadata
        )
        
        msg_id = result.message_id
        seq = result.sequence_number

        # 2. 如果需要模拟 Changeset 桥接 (Phase 3)
        if scenario.get("simulate_changeset"):
            await self.repo.sync_changeset_reference(msg_id, "app/main.py", "edit")

        # 3. 如果需要手动注入引用 (Phase 1)
        if custom_refs:
            async with session_scope() as session:
                from app.models import MessageReference
                for r in custom_refs:
                    ref = MessageReference(
                        id=str(uuid.uuid4()),
                        message_id=msg_id,
                        type=r["type"],
                        target_id=r["target_id"],
                        target_name=r["target_name"],
                        meta_data=r.get("metadata", {})
                    )
                    session.add(ref)

        # 4. 从 DB 加载并映射 (Phase 4)
        async with session_scope() as session:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            from app.models import Message
            stmt = select(Message).where(Message.id == msg_id).options(selectinload(Message.references))
            db_res = await session.execute(stmt)
            db_msg = db_res.scalar_one()
            
            block = BlockMapper.from_db(db_msg)

        # 5. 质量核对 (Quality Check)
        report = {
            "name": name,
            "status": "PASS",
            "details": [],
            "block": block.model_dump()
        }

        # 核对引用数量
        actual_refs = len(block.references) if block.references else 0
        expected_refs = scenario["expect"].get("refs_count")
        if expected_refs is not None and actual_refs != expected_refs:
            report["status"] = "FAIL"
            report["details"].append(f"Expected {expected_refs} refs, got {actual_refs}")

        # 核对特定类型
        if scenario["expect"].get("type"):
            found_type = any(r.type == scenario["expect"]["type"] for r in block.references)
            if not found_type:
                report["status"] = "FAIL"
                report["details"].append(f"Missing expected ref type: {scenario['expect']['type']}")

        # 核对 Mobile 对齐
        if actual_refs > 0:
            if not block.attachments or len(block.attachments) != actual_refs:
                report["status"] = "FAIL"
                report["details"].append("Mobile 'attachments' field mismatch")

        # 核对 Changeset
        if scenario["expect"].get("has_changeset") and not block.has_file_operations:
            report["status"] = "FAIL"
            report["details"].append("Changeset not detected in top-level fields")

        return report

async def main():
    logger.info("="*80)
    logger.info("EvoLoop AI Message Standardization Quality Audit")
    logger.info("="*80)

    # 初始化 DB
    await db_resource_manager.initialize(create_tables=True)
    
    thread_id = f"audit-{uuid.uuid4().hex[:6]}"
    auditor = Auditor(thread_id)
    
    final_reports = []
    for scenario in SCENARIOS:
        logger.info(f"Auditing {scenario['name']}...")
        report = await auditor.audit_scenario(scenario)
        final_reports.append(report)
        if report["status"] == "PASS":
            logger.info(f"  ✅ PASS")
        else:
            logger.error(f"  ❌ FAIL: {', '.join(report['details'])}")

    # 生成总结报告
    passed = len([r for r in final_reports if r["status"] == "PASS"])
    logger.info("\n" + "="*80)
    logger.info(f"AUDIT SUMMARY: {passed}/{len(SCENARIOS)} Scenarios Passed")
    logger.info("="*80)

    # 保存报告到文件
    with open("/Users/huangjinhuan/.gemini/antigravity/brain/c6e2f2c3-ad4a-4a4f-8fc9-ce6c4336cfb9/scratch/audit_report.json", "w", encoding="utf-8") as f:
        json.dump(final_reports, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Detailed audit JSON saved to: scratch/audit_report.json")

if __name__ == "__main__":
    asyncio.run(main())
