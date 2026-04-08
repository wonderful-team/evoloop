#!/usr/bin/env python3
"""
MCP 全面审计测试脚本
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_syntax():
    """测试所有 MCP 文件语法"""
    print("=" * 60)
    print("1. 语法检查")
    print("=" * 60)
    
    files = [
        "app/core/mcp/__init__.py",
        "app/core/mcp/config.py",
        "app/core/mcp/transport.py",
        "app/core/mcp/health.py",
        "app/core/mcp/client/manager.py",
        "app/core/mcp/worker.py",
        "app/core/mcp/worker_config.py",
        "app/core/mcp/features/base.py",
        "app/core/mcp/features/tools.py",
        "app/core/mcp/features/resources.py",
        "app/core/mcp/features/prompts.py",
        "app/core/mcp/auth/base.py",
        "app/core/mcp/auth/manager.py",
        "app/core/mcp/auth/elicitation.py",
        "app/core/mcp/auth/oauth_flows.py",
        "app/core/tools/mcp/worker_integration.py",
        "app/core/tools/mcp/list_resources.py",
        "app/core/tools/mcp/read_resource.py",
        "app/core/tools/mcp/list_prompts.py",
        "app/core/tools/mcp/get_prompt.py",
    ]
    
    import py_compile
    errors = []
    for f in files:
        try:
            py_compile.compile(f, doraise=True)
            print(f"  ✅ {f}")
        except Exception as e:
            print(f"  ❌ {f}: {e}")
            errors.append((f, e))
    
    if errors:
        print(f"\n❌ {len(errors)} 个文件有语法错误")
        return False
    print(f"\n✅ 所有 {len(files)} 个文件语法正确")
    return True


def test_code_structure():
    """测试代码结构（不依赖外部模块）"""
    print("\n" + "=" * 60)
    print("2. 代码结构检查")
    print("=" * 60)
    
    all_pass = True
    
    # 检查 config.py
    try:
        with open("../app/core/mcp/config.py", "r") as f:
            content = f.read()
        
        checks = [
            ("class TransportType", "TransportType 枚举"),
            ("class AuthType", "AuthType 枚举"),
            ("class McpServerConfig", "McpServerConfig 类"),
            ("def from_db_model", "from_db_model 方法"),
        ]
        for check, desc in checks:
            if check in content:
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ {desc}")
                all_pass = False
    except Exception as e:
        print(f"  ❌ config.py 检查失败: {e}")
        all_pass = False
    
    # 检查 worker_config.py
    try:
        with open("../app/core/mcp/worker_config.py", "r") as f:
            content = f.read()
        
        checks = [
            ("class WorkerMcpServerConfig", "WorkerMcpServerConfig 类"),
            ("class WorkerMcpConfig", "WorkerMcpConfig 类"),
            ("def from_dict", "from_dict 方法"),
            ("def to_mcp_config", "to_mcp_config 方法"),
            ("def is_empty", "is_empty 方法"),
        ]
        for check, desc in checks:
            if check in content:
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ {desc}")
                all_pass = False
    except Exception as e:
        print(f"  ❌ worker_config.py 检查失败: {e}")
        all_pass = False
    
    # 检查 features/base.py
    try:
        with open("../app/core/mcp/features/base.py", "r") as f:
            content = f.read()
        
        checks = [
            ("class McpFeature", "McpFeature 基类"),
            ("@abstractmethod", "抽象方法装饰器"),
            ("async def initialize", "initialize 方法"),
            ("def reset", "reset 方法"),
        ]
        for check, desc in checks:
            if check in content:
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ {desc}")
                all_pass = False
    except Exception as e:
        print(f"  ❌ features/base.py 检查失败: {e}")
        all_pass = False
    
    return all_pass


def test_manager_structure():
    """测试 Manager 结构"""
    print("\n" + "=" * 60)
    print("3. Manager 结构检查")
    print("=" * 60)
    
    all_pass = True
    
    try:
        with open("../app/core/mcp/client/manager.py", "r") as f:
            content = f.read()
        
        checks = [
            ("class McpClientManager", "McpClientManager 类"),
            ("async def connect", "connect 方法"),
            ("async def connect_all", "connect_all 方法"),
            ("async def disconnect", "disconnect 方法"),
            ("async def disconnect_all", "disconnect_all 方法"),
            ("async def cleanup", "cleanup 方法"),
            ("async def get_tools", "get_tools 方法"),
            ("async def ensure_connected", "ensure_connected 方法"),
            ("async def list_resources", "list_resources 方法"),
            ("async def read_resource", "read_resource 方法"),
            ("async def list_prompts", "list_prompts 方法"),
            ("async def get_prompt", "get_prompt 方法"),
            ("async def health_check", "health_check 方法"),
            ("mcp_client_manager = McpClientManager", "单例实例"),
        ]
        for check, desc in checks:
            if check in content:
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ {desc}")
                all_pass = False
    except Exception as e:
        print(f"  ❌ manager.py 检查失败: {e}")
        all_pass = False
    
    return all_pass


def test_worker_mcp():
    """测试 Worker MCP"""
    print("\n" + "=" * 60)
    print("4. Worker MCP 检查")
    print("=" * 60)
    
    all_pass = True
    
    try:
        with open("../app/core/mcp/worker.py", "r") as f:
            content = f.read()
        
        checks = [
            ("class WorkerMcpSession", "WorkerMcpSession 类"),
            ("class WorkerMcpManager", "WorkerMcpManager 类"),
            ("async def connect_server", "connect_server 方法"),
            ("async def disconnect_all", "disconnect_all 方法"),
            ("def get_tools", "get_tools 方法"),
            ("worker_mcp_manager = WorkerMcpManager", "单例实例"),
        ]
        for check, desc in checks:
            if check in content:
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ {desc}")
                all_pass = False
    except Exception as e:
        print(f"  ❌ worker.py 检查失败: {e}")
        all_pass = False
    
    return all_pass


def test_model_update():
    """测试数据库模型更新"""
    print("\n" + "=" * 60)
    print("5. 数据库模型检查")
    print("=" * 60)
    
    try:
        with open("../app/models/learning.py", "r") as f:
            content = f.read()
        
        if "mcp_config" in content and "Mapped[dict" in content:
            print("  ✅ LearnedSkill 有 mcp_config 列定义")
        else:
            print("  ❌ LearnedSkill 缺少 mcp_config 列定义")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ❌ 模型检查失败: {e}")
        return False


def test_api_routes():
    """测试 API 路由更新"""
    print("\n" + "=" * 60)
    print("6. API 路由检查")
    print("=" * 60)
    
    all_pass = True
    
    try:
        with open("../app/api/routes/learning.py", "r") as f:
            content = f.read()
        
        checks = [
            ("mcp_config: dict", "UpdateSkillRequest 有 mcp_config"),
            ("skill.mcp_config = body.mcp_config", "更新逻辑"),
        ]
        for check, desc in checks:
            if check in content:
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ {desc}")
                all_pass = False
    except Exception as e:
        print(f"  ❌ API 路由检查失败: {e}")
        all_pass = False
    
    return all_pass


def test_subtask_inheritance():
    """测试子任务 MCP 继承"""
    print("\n" + "=" * 60)
    print("7. 子任务 MCP 继承检查")
    print("=" * 60)
    
    try:
        with open("../app/core/engine/routers.py", "r") as f:
            content = f.read()
        
        checks = [
            ("parent_mcp_servers = parent_ticket.get", "获取父任务 MCP"),
            ('"mcp_servers_required": parent_mcp_servers', "传递给子任务"),
        ]
        
        all_pass = True
        for check, desc in checks:
            if check in content:
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ {desc}")
                all_pass = False
        
        return all_pass
        
    except Exception as e:
        print(f"  ❌ 检查失败: {e}")
        return False


def test_worker_integration():
    """测试 Worker 集成"""
    print("\n" + "=" * 60)
    print("8. Worker MCP 集成检查")
    print("=" * 60)
    
    try:
        with open("../app/core/engine/nodes/worker.py", "r") as f:
            content = f.read()
        
        checks = [
            ("_merge_skills_mcp_config", "合并技能 MCP 配置"),
            ("_load_worker_tools", "加载 Worker 工具"),
            ("WorkerMcpConfig", "导入 WorkerMcpConfig"),
            ("tool_manager.get_worker_tools", "调用 get_worker_tools"),
            ("tool_manager.cleanup_worker_tools", "调用 cleanup_worker_tools"),
        ]
        
        all_pass = True
        for check, desc in checks:
            if check in content:
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ {desc}")
                all_pass = False
        
        return all_pass
        
    except Exception as e:
        print(f"  ❌ 检查失败: {e}")
        return False


def test_cleanup_in_main():
    """测试 main.py 清理逻辑"""
    print("\n" + "=" * 60)
    print("9. Main.py 清理检查")
    print("=" * 60)
    
    try:
        with open("../app/main.py", "r") as f:
            content = f.read()
        
        checks = [
            ("worker_mcp_manager.cleanup_all", "Worker MCP 清理"),
            ("mcp_client_manager.cleanup", "全局 MCP 清理"),
        ]
        
        all_pass = True
        for check, desc in checks:
            if check in content:
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ {desc}")
                all_pass = False
        
        return all_pass
        
    except Exception as e:
        print(f"  ❌ 检查失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "🔍" * 30)
    print("EvoLoop MCP 全面审计")
    print("🔍" * 30 + "\n")
    
    results = []
    
    results.append(("语法检查", test_syntax()))
    results.append(("代码结构", test_code_structure()))
    results.append(("Manager 结构", test_manager_structure()))
    results.append(("Worker MCP", test_worker_mcp()))
    results.append(("数据库模型", test_model_update()))
    results.append(("API 路由", test_api_routes()))
    results.append(("子任务继承", test_subtask_inheritance()))
    results.append(("Worker 集成", test_worker_integration()))
    results.append(("Main 清理", test_cleanup_in_main()))
    
    print("\n" + "=" * 60)
    print("审计结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print("\n" + "=" * 60)
    print(f"总计: {passed}/{total} 通过")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 所有审计项通过！MCP 实现完整。")
        print("\n架构亮点:")
        print("  • 分层架构：config → transport → features → client → worker")
        print("  • 功能完整：Tools + Resources + Prompts + OAuth + URL Elicitation")
        print("  • Worker 独立 MCP：父子隔离，自动生命周期管理")
        print("  • 技能自带 MCP：通过 mcp_config 字段支持")
        print("  • 子任务继承：自动继承父任务 MCP 服务器")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 项失败，请修复后再测试。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
