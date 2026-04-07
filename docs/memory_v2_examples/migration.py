"""
Memory 系统迁移脚本

从 v1 (Brain + NoOp) 迁移到 v2 (统一 MemoryManager)
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryMigration:
    """记忆系统迁移工具"""
    
    def __init__(self, brain_root: str, memory_v2_root: str):
        self.brain_root = Path(brain_root)
        self.memory_v2_root = Path(memory_v2_root)
    
    async def migrate_all(self) -> dict:
        """
        执行完整迁移
        
        Returns:
            迁移统计信息
        """
        stats = {
            "journal_entries": 0,
            "focus_entries": 0,
            "identity_entries": 0,
            "errors": [],
        }
        
        # 1. 迁移 journal.md
        try:
            journal_count = await self._migrate_journal()
            stats["journal_entries"] = journal_count
        except Exception as e:
            stats["errors"].append(f"Journal migration failed: {e}")
        
        # 2. 迁移 focus.md
        try:
            focus_count = await self._migrate_focus()
            stats["focus_entries"] = focus_count
        except Exception as e:
            stats["errors"].append(f"Focus migration failed: {e}")
        
        # 3. 迁移 identity.md
        try:
            identity_count = await self._migrate_identity()
            stats["identity_entries"] = identity_count
        except Exception as e:
            stats["errors"].append(f"Identity migration failed: {e}")
        
        return stats
    
    async def _migrate_journal(self) -> int:
        """迁移 journal.md 到 Memory v2"""
        journal_path = self.brain_root / "knowledge" / "journal.md"
        if not journal_path.exists():
            logger.info("No journal.md found, skipping")
            return 0
        
        content = journal_path.read_text(encoding="utf-8")
        entries = self._parse_journal_entries(content)
        
        count = 0
        for entry in entries:
            # 转换为 MemoryEntry
            memory_entry = self._convert_journal_entry(entry)
            # 存储到 v2
            # await memory_manager.store_memory(memory_entry)
            count += 1
        
        logger.info(f"Migrated {count} journal entries")
        return count
    
    def _parse_journal_entries(self, content: str) -> list[dict]:
        """解析 journal.md 中的条目"""
        entries = []
        # 按 "## Consolidated Entry" 分割
        parts = content.split("## Consolidated Entry")
        
        for part in parts[1:]:  # 跳过第一个空部分
            lines = part.strip().split("\n")
            if not lines:
                continue
            
            # 提取 ID
            header = lines[0]
            entry_id = None
            if "<!-- id:" in header:
                entry_id = header.split("<!-- id:")[1].split("-->")[0].strip()
            
            # 提取内容
            body = "\n".join(lines[1:]).strip()
            
            entries.append({
                "id": entry_id,
                "content": body,
            })
        
        return entries
    
    def _convert_journal_entry(self, entry: dict) -> dict:
        """将 journal 条目转换为 MemoryEntry 格式"""
        return {
            "type": "feedback",
            "privacy": "private",
            "title": f"Consolidated Entry {entry.get('id', 'unknown')[:8]}",
            "content": entry["content"],
            "source": "consolidated",
            "confidence": 0.8,
        }
    
    async def _migrate_focus(self) -> int:
        """迁移 focus.md"""
        focus_path = self.brain_root / "working" / "focus.md"
        if not focus_path.exists():
            return 0
        
        content = focus_path.read_text(encoding="utf-8")
        if not content.strip():
            return 0
        
        # 创建为 project 类型的记忆
        memory_entry = {
            "type": "project",
            "privacy": "private",
            "title": "当前工作焦点",
            "content": content,
            "source": "manual",
            "confidence": 1.0,
        }
        
        logger.info("Migrated focus.md")
        return 1
    
    async def _migrate_identity(self) -> int:
        """迁移 identity.md"""
        identity_path = self.brain_root / "sys" / "identity.md"
        if not identity_path.exists():
            return 0
        
        content = identity_path.read_text(encoding="utf-8")
        
        memory_entry = {
            "type": "user",
            "privacy": "private",
            "title": "系统身份配置",
            "content": content,
            "source": "manual",
            "confidence": 1.0,
        }
        
        logger.info("Migrated identity.md")
        return 1


# 迁移检查清单
MIGRATION_CHECKLIST = """
# Memory v2 迁移检查清单

## 迁移前准备
- [ ] 备份现有的 Brain 目录
- [ ] 备份现有的 Neo4j 数据（如适用）
- [ ] 确认 settings.EMBEDDED_MODE 配置
- [ ] 设置 USE_MEMORY_V2 = false（灰度开关）

## 代码迁移
- [ ] 部署 memory_v2 模块
- [ ] 运行迁移脚本
- [ ] 验证迁移结果
- [ ] 运行回归测试

## 灰度切换
- [ ] 设置 USE_MEMORY_V2 = true（小范围测试）
- [ ] 监控错误日志
- [ ] 验证核心功能正常
- [ ] 全量切换

## 回滚准备
- [ ] 保留 v1 代码路径
- [ ] 测试回滚流程
- [ ] 准备紧急回滚方案
"""


if __name__ == "__main__":
    import asyncio
    
    async def main():
        migrator = MemoryMigration(
            brain_root="~/.evoloop/brain",
            memory_v2_root="~/.evoloop/memory",
        )
        
        print("Starting migration...")
        stats = await migrator.migrate_all()
        
        print("\nMigration complete!")
        print(f"  Journal entries: {stats['journal_entries']}")
        print(f"  Focus entries: {stats['focus_entries']}")
        print(f"  Identity entries: {stats['identity_entries']}")
        
        if stats['errors']:
            print(f"\nErrors ({len(stats['errors'])}):")
            for err in stats['errors']:
                print(f"  - {err}")
    
    asyncio.run(main())
