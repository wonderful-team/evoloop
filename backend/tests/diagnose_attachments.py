import asyncio
import os
import sys
from sqlalchemy import select
from app.infrastructure.database.sql.database import session_scope
from app.models import Message, MessageReference, Conversation
from app.core.config import settings

async def diagnose_db_state():
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize()
    
    print("\n" + "="*50)
    print("DATABASE & FILE SYSTEM DIAGNOSTIC")
    print("="*50)
    
    try:
        async with session_scope() as session:
            # 获取最近的一个带附件的会话
            stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(5)
            result = await session.execute(stmt)
            conversations = result.scalars().all()
            
            for conv in conversations:
                print(f"\n[Thread: {conv.id}] (Updated: {conv.updated_at})")
                
                # 检查物理目录
                physical_dir = os.path.join(settings.CHAT_UPLOAD_DIR, conv.id)
                exists = os.path.exists(physical_dir)
                print(f"  Physical Dir: {physical_dir} -> {'✅ EXISTS' if exists else '❌ MISSING'}")
                if exists:
                    files = os.listdir(physical_dir)
                    print(f"  Files found: {files}")

                # 检查消息及引用
                msg_stmt = select(Message).where(Message.thread_id == conv.id).order_by(Message.sequence_number.asc())
                msg_result = await session.execute(msg_stmt)
                messages = msg_result.scalars().all()
                
                for msg in messages:
                    ref_stmt = select(MessageReference).where(MessageReference.message_id == msg.id)
                    ref_result = await session.execute(ref_stmt)
                    refs = ref_result.scalars().all()
                    
                    if refs:
                        print(f"  Msg #{msg.sequence_number} ({msg.role}):")
                        for ref in refs:
                            print(f"    - Ref ID: {ref.id}")
                            print(f"    - Ref Type: {ref.type}")
                            print(f"    - Ref Target ID (URL): {ref.target_id}")
                            print(f"    - Ref Target Name: {ref.target_name}")
                            
                            # 验证 URL 里的路径是否能对上物理文件
                            if ref.target_id and "path=" in ref.target_id:
                                logical_path = ref.target_id.split("path=")[1].split("&")[0]
                                print(f"    - Parsed Logical Path: {logical_path}")
    finally:
        await db_resource_manager.shutdown()

if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(diagnose_db_state())
