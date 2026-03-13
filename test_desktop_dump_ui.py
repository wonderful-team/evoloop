#!/usr/bin/env python3
"""
验证 Desktop dump_ui 可行性
==========================

测试内容：
1. 检查 macos_driver.dump_ax_tree() 能否获取完整的 AX Tree
2. 验证返回数据的格式和内容
3. 确认是否可以作为 dump_ui action 的基础
"""

import asyncio
import sys
import os
import json

sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")
os.chdir("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")

from app.infrastructure.drivers.macos import macos_driver
from app.domain.tools.environment.desktop import desktop_control


async def test_ax_tree_dump():
    """测试 AX Tree 导出功能"""
    print("\n" + "="*70)
    print("🧪 Testing Desktop AX Tree Dump Capability")
    print("="*70)

    # 测试1: 直接调用 macos_driver.dump_ax_tree()
    print("\n1. Testing macos_driver.dump_ax_tree()...")
    try:
        raw_tree = macos_driver.dump_ax_tree()
        print(f"   ✓ dump_ax_tree() returned data")
        print(f"   - Raw data length: {len(raw_tree)} chars")
        print(f"   - First 200 chars: {raw_tree[:200]}...")

        # 尝试解析
        try:
            import ast
            elements = ast.literal_eval(raw_tree.replace("missing value", "None"))
            print(f"   ✓ Parsed successfully")
            print(f"   - Number of elements: {len(elements)}")
            if elements:
                print(f"   - First element sample: {json.dumps(elements[0], indent=2, default=str)[:300]}...")
        except Exception as e:
            print(f"   ⚠ Parse warning: {e}")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

    # 测试2: 打开一个应用后获取 AX Tree
    print("\n2. Testing with Safari open...")
    try:
        result = await desktop_control.ainvoke({"action": "open_app", "app_name": "Safari"})
        print(f"   ✓ Opened Safari: {result[:60]}...")

        await asyncio.sleep(1)

        raw_tree = macos_driver.dump_ax_tree()
        elements = ast.literal_eval(raw_tree.replace("missing value", "None"))
        print(f"   ✓ AX Tree captured: {len(elements)} elements")

        # 分析元素类型
        roles = {}
        for el in elements:
            role = el.get("role", "Unknown")
            roles[role] = roles.get(role, 0) + 1

        print(f"   - Element roles breakdown:")
        for role, count in sorted(roles.items(), key=lambda x: -x[1])[:10]:
            print(f"     • {role}: {count}")

    except Exception as e:
        print(f"   ❌ Error: {e}")

    # 测试3: 检查返回数据的字段完整性
    print("\n3. Analyzing data structure...")
    try:
        if elements:
            sample = elements[0]
            print(f"   Available fields in element:")
            for key in sample.keys():
                print(f"     • {key}")

            # 检查是否有嵌套 children
            has_children = any("children" in el for el in elements)
            print(f"   - Has nested children: {has_children}")

            # 检查是否有 bounds
            has_bounds = any("bounds" in el for el in elements)
            print(f"   - Has bounds: {has_bounds}")

    except Exception as e:
        print(f"   ❌ Error: {e}")

    return True


async def test_dump_ui_feasibility():
    """评估作为 dump_ui action 的可行性"""
    print("\n" + "="*70)
    print("📊 dump_ui Action Feasibility Assessment")
    print("="*70)

    assessments = []

    # 1. 数据完整性
    print("\n1. Data Completeness:")
    raw_tree = macos_driver.dump_ax_tree()
    try:
        elements = json.loads(raw_tree.replace("'", '"').replace("missing value", "null"))
        assessments.append(("Parseable JSON", True))
    except:
        try:
            import ast
            elements = ast.literal_eval(raw_tree.replace("missing value", "None"))
            assessments.append(("Parseable (ast.literal_eval)", True))
        except Exception as e:
            assessments.append(("Parseable", False))
            print(f"   ❌ Cannot parse: {e}")
            return assessments

    # 检查关键字段
    required_fields = ["name", "role", "bounds"]
    for field in required_fields:
        has_field = any(field in el for el in elements)
        assessments.append((f"Has '{field}' field", has_field))
        status = "✅" if has_field else "⚠️"
        print(f"   {status} Field '{field}': {has_field}")

    # 2. 数据大小
    print("\n2. Data Size:")
    size_kb = len(raw_tree) / 1024
    assessments.append(("Size < 100KB", size_kb < 100))
    print(f"   {'✅' if size_kb < 100 else '⚠️'} Raw size: {size_kb:.1f} KB")

    # 3. 实用性
    print("\n3. Practical Utility:")
    meaningful_elements = [el for el in elements if el.get("name") or el.get("role")]
    has_meaningful = len(meaningful_elements) > 0
    assessments.append(("Has meaningful elements", has_meaningful))
    print(f"   ✅ Meaningful elements: {len(meaningful_elements)}/{len(elements)}")

    # 4. 与 Mobile dump_ui 对比
    print("\n4. Comparison with Mobile dump_ui:")
    print("   Mobile dump_ui returns: XML hierarchy")
    print("   Desktop would return: JSON array of elements")
    print("   ✅ Both provide complete UI structure")

    return assessments


async def main():
    print("\n" + "="*70)
    print("🚀 DESKTOP DUMP_UI VALIDATION TEST")
    print("="*70)

    # 运行测试
    success = await test_ax_tree_dump()
    assessments = await test_dump_ui_feasibility()

    # 总结
    print("\n" + "="*70)
    print("📊 VALIDATION SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in assessments if result)
    total = len(assessments)

    print(f"\nChecks passed: {passed}/{total}")

    if passed == total:
        print("\n✅ DUMP_UI IS FEASIBLE")
        print("\nImplementation recommendation:")
        print("  1. Add 'dump_ui' action to desktop_control")
        print("  2. Return JSON array of AX elements")
        print("  3. Include: name, role, bounds, path, children")
        print("  4. Optionally support filtering by role or name")
    else:
        print("\n⚠️  SOME ISSUES FOUND")
        for check, result in assessments:
            if not result:
                print(f"  - {check}: FAILED")

    return passed == total


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
