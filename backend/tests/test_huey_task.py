import os
import inspect

def test_signature_via_exec():
    """
    通过 exec() 加载函数定义，既能检查运行时签名，又能避开所有 import 依赖。
    """
    print("\n=== Huey Task Runtime Signature Audit (via exec) ===")
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TASK_FILE = os.path.join(BASE_DIR, "app/core/evocloud/bridge/sync_tasks.py")
    
    if not os.path.exists(TASK_FILE):
        print(f"❌ Error: Task file not found at {TASK_FILE}")
        return

    with open(TASK_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # 准备一个 Mock 的装饰器，防止 exec 时报错
    class MockSharedTask:
        def __call__(self, *args, **kwargs):
            return lambda f: f

    namespace = {
        "shared_task": MockSharedTask(),
        "SyncMessage": object, # Mock
        "get_db_session": object, # Mock
        "ConversationModel": object, # Mock
        "MessageModel": object, # Mock
        "update": object, # Mock
        "select": object, # Mock
        "timezone": object, # Mock
        "datetime": object, # Mock
        "logger": object, # Mock
        "api": object, # Mock
        "EvoCloudHTTPClient": object # Mock
    }
    
    # 我们只执行函数定义相关的部分，为了简单，我们用 exec() 跑整个文件，但屏蔽掉真正的 import
    # 或者，我们只截取函数定义部分
    
    # 查找函数头 (直到冒号)
    import re
    match = re.search(r"async def incremental_sync_task\(.*?\):", content, re.DOTALL)
    if not match:
        print("❌ Error: Could not find incremental_sync_task header")
        return
        
    header = match.group(0)
    header += "\n    pass" # 补全函数体
    
    print(f"Executing: {header}")
    
    try:
        exec(header, namespace)
        func = namespace["incremental_sync_task"]
        sig = inspect.signature(func)
        
        print(f"\nResulting Signature: {sig}")
        params = list(sig.parameters.keys())
        
        if "conversation_ids" in params:
            print("❌ FAIL: 'conversation_ids' is STILL there!")
        else:
            print("✅ SUCCESS: 'conversation_ids' is GONE.")
            
        if "thread_ids" in params:
            print("✅ SUCCESS: 'thread_ids' exists.")
        else:
            print("❌ FAIL: 'thread_ids' is MISSING!")
            
    except Exception as e:
        print(f"Error during exec: {e}")

if __name__ == "__main__":
    test_signature_via_exec()
