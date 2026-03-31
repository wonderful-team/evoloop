"""
Pre-Supervisor 优化静态代码验证

不依赖运行时导入，直接检查源代码实现
"""

import ast
import sys
from pathlib import Path


def check_file_exists(filepath, desc):
    """检查文件是否存在"""
    print(f"\n{'='*60}")
    print(f"检查: {desc}")
    print(f"{'='*60}")
    
    if filepath.exists():
        print(f"✓ 文件存在: {filepath}")
        return True
    else:
        print(f"❌ 文件不存在: {filepath}")
        return False


def parse_python_file(filepath):
    """解析 Python 文件"""
    try:
        with open(filepath, 'r') as f:
            return ast.parse(f.read())
    except SyntaxError as e:
        print(f"❌ 语法错误: {e}")
        return None


def check_evocloud_manager():
    """检查 EvoCloud Manager 缓存实现"""
    filepath = Path("app/core/evocloud/manager.py")
    
    if not check_file_exists(filepath, "EvoCloud Manager 缓存"):
        return False
    
    tree = parse_python_file(filepath)
    if not tree:
        return False
    
    # 检查关键属性
    checks = {
        "_projects_cache 属性": False,
        "_projects_cache_time 属性": False,
        "_projects_cache_ttl 属性": False,
        "invalidate_projects_cache 方法": False,
        "_fetch_projects_from_api 方法": False,
        "缓存过期检查逻辑": False,
        "返回副本逻辑": False,
    }
    
    source = filepath.read_text()
    
    # 文本级检查
    checks["_projects_cache 属性"] = "_projects_cache: list[dict] | None" in source
    checks["_projects_cache_time 属性"] = "_projects_cache_time: float" in source
    checks["_projects_cache_ttl 属性"] = "_projects_cache_ttl: int = 60" in source
    checks["invalidate_projects_cache 方法"] = "def invalidate_projects_cache" in source
    checks["_fetch_projects_from_api 方法"] = "async def _fetch_projects_from_api" in source
    checks["缓存过期检查逻辑"] = "(now - self._projects_cache_time) < self._projects_cache_ttl" in source
    checks["返回副本逻辑"] = ".copy()" in source and "return self._projects_cache.copy()" in source
    
    for name, found in checks.items():
        status = "✓" if found else "❌"
        print(f"  {status} {name}")
    
    return all(checks.values())


def check_main_py_warmup():
    """检查 main.py 启动预热代码"""
    filepath = Path("app/main.py")
    
    if not check_file_exists(filepath, "main.py 启动预热"):
        return False
    
    source = filepath.read_text()
    
    checks = {
        "_warm_evocloud_cache 函数": "async def _warm_evocloud_cache():" in source,
        "Skills 预热": "skill_discovery.get_active_skills_list()" in source,
        "语言偏好预热": "get_language_preference()" in source,
        "EvoCloud 后台预热": "asyncio.create_task(_warm_evocloud_cache())" in source,
        "预热计时": "start_warm = time.time()" in source,
        "预热完成日志": "Cache warming completed" in source,
        "time 导入": "import time" in source,
    }
    
    for name, found in checks.items():
        status = "✓" if found else "❌"
        print(f"  {status} {name}")
    
    return all(checks.values())


def check_skill_discovery_cache():
    """检查 Skill Discovery 缓存属性"""
    filepath = Path("app/core/learning/discovery.py")
    
    if not check_file_exists(filepath, "Skill Discovery 缓存"):
        return False
    
    source = filepath.read_text()
    
    checks = {
        "_skills_cache 属性": "_skills_cache: list[LearnedSkill] | None" in source,
        "_skills_list_cache 属性": "_skills_list_cache: list[dict[str, Any]] | None" in source,
        "_id_map 属性": "_id_map: dict[int, LearnedSkill]" in source,
        "_name_map 属性": "_name_map: dict[str, LearnedSkill]" in source,
        "force_reload 参数": "force_reload: bool" in source,
        "缓存检查逻辑": "if not force_reload and self._skills_cache is not None:" in source,
    }
    
    for name, found in checks.items():
        status = "✓" if found else "❌"
        print(f"  {status} {name}")
    
    return all(checks.values())


def check_system_config_cache():
    """检查 System Config 缓存"""
    filepath = Path("app/infrastructure/config/service.py")
    
    if not check_file_exists(filepath, "System Config 缓存"):
        return False
    
    source = filepath.read_text()
    
    checks = {
        "_cache 字典": "_cache: dict[str, str] = {}" in source,
        "缓存读取": "if key in _cache:" in source,
        "缓存写入": "_cache[key] = val" in source,
        "get_value 方法": "def get_value(" in source,
        "get_language_preference 方法": "def get_language_preference(" in source,
    }
    
    for name, found in checks.items():
        status = "✓" if found else "❌"
        print(f"  {status} {name}")
    
    return all(checks.values())


def check_renderer_dedup():
    """检查 renderer.py 重复定义修复"""
    filepath = Path("app/utils/renderer.py")
    
    if not check_file_exists(filepath, "renderer.py 去重"):
        return False
    
    source = filepath.read_text()
    
    checks = {
        "DEPRECATED 标记": "DEPRECATED" in source,
        "重新导出": "from app.utils.template import render_template" in source,
        "无独立 Environment": source.count("Environment(") == 0,
        "无文件加载器": source.count("FileSystemLoader") == 0,
    }
    
    for name, found in checks.items():
        status = "✓" if found else "❌"
        print(f"  {status} {name}")
    
    return all(checks.values())


def check_template_globals():
    """检查 template.py 全局单例"""
    filepath = Path("app/utils/template.py")
    
    if not check_file_exists(filepath, "template.py 全局单例"):
        return False
    
    source = filepath.read_text()
    
    checks = {
        "_config_env 全局变量": "_config_env: Environment | None = None" in source,
        "懒加载模式": "if _config_env is None:" in source,
        "单例返回": "return _config_env" in source,
        "TemplateRenderer 复用": "class TemplateRenderer" in source,
    }
    
    for name, found in checks.items():
        status = "✓" if found else "❌"
        print(f"  {status} {name}")
    
    return all(checks.values())


def main():
    """运行所有静态检查"""
    print("\n" + "="*70)
    print(" Pre-Supervisor 优化静态代码验证")
    print("="*70)
    
    # 切换到 backend 目录
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)
    
    tests = [
        ("EvoCloud Manager 缓存", check_evocloud_manager),
        ("main.py 启动预热", check_main_py_warmup),
        ("Skill Discovery 缓存", check_skill_discovery_cache),
        ("System Config 缓存", check_system_config_cache),
        ("renderer.py 去重", check_renderer_dedup),
        ("template.py 全局单例", check_template_globals),
    ]
    
    passed = 0
    failed = 0
    
    for name, check_func in tests:
        try:
            if check_func():
                passed += 1
            else:
                failed += 1
                print(f"\n⚠️  {name} 检查未完全通过")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name} 检查失败: {e}")
    
    print("\n" + "="*70)
    print(f" 验证结果: {passed} 通过, {failed} 失败")
    print("="*70)
    
    if failed == 0:
        print("\n🎉 所有静态代码验证通过!")
        print("\n实施的优化:")
        print("  1. EvoCloud scan_projects() 60s TTL 缓存")
        print("  2. Skill Discovery 启动预热")
        print("  3. User Prefs 启动预热")
        print("  4. Jinja2 Environment 单例化")
        print("  5. renderer.py 重复定义修复")
        return 0
    else:
        print(f"\n⚠️  {failed} 个检查失败，请查看详情")
        return 1


if __name__ == "__main__":
    import os
    exit(main())
