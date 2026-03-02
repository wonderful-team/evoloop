#!/usr/bin/env python3
"""
深度验证 i18n 键使用情况
- 遍历所有代码文件提取使用的键
- 支持多种使用模式：t("key"), i18nKey="key", t(`key`), etc.
- 支持动态键模式匹配
"""

import json
import re
from pathlib import Path
from typing import Set, Dict, List


def get_all_keys_from_json(obj: dict, prefix: str = "") -> Set[str]:
    """递归获取 JSON 中的所有键"""
    keys = set()
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys.update(get_all_keys_from_json(value, full_key))
        else:
            keys.add(full_key)
    return keys


def extract_used_keys_from_file(file_path: Path) -> Set[str]:
    """从代码文件中提取使用的 i18n 键"""
    used_keys = set()

    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"  无法读取文件 {file_path}: {e}")
        return used_keys

    # 模式 1: t("key") 或 t('key')
    pattern1 = r't\(["\']([\w.]+)["\']'
    matches1 = re.findall(pattern1, content)
    used_keys.update(matches1)

    # 模式 2: i18nKey="key" 或 i18nKey='key'
    pattern2 = r'i18nKey=["\']([\w.]+)["\']'
    matches2 = re.findall(pattern2, content)
    used_keys.update(matches2)

    # 模式 3: t(`key`) - 模板字符串
    pattern3 = r't\(`([\w.]+)`\)'
    matches3 = re.findall(pattern3, content)
    used_keys.update(matches3)

    # 模式 4: 动态键模式如 t(`learning.statusBadge.${status}`)
    # 提取前缀部分
    pattern4 = r't\([`"\']?([\w]+\.[\w]+)\.'
    matches4 = re.findall(pattern4, content)
    for prefix in matches4:
        used_keys.add(f"{prefix}.*")  # 标记为动态使用

    return used_keys


def find_all_used_keys(src_dir: Path) -> Set[str]:
    """遍历源代码目录，找出所有使用的 i18n 键"""
    used_keys = set()

    for ext in ['*.tsx', '*.ts']:
        for file_path in src_dir.rglob(ext):
            if 'node_modules' in str(file_path):
                continue
            keys = extract_used_keys_from_file(file_path)
            used_keys.update(keys)

    return used_keys


def check_key_usage(key: str, used_keys: Set[str]) -> bool:
    """检查一个键是否被使用"""
    # 直接匹配
    if key in used_keys:
        return True

    # 检查是否是动态使用的一部分
    for used_key in used_keys:
        if used_key.endswith('.*'):
            prefix = used_key[:-2]
            if key.startswith(prefix):
                return True

    return False


def main():
    frontend_dir = Path("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/frontend")

    # 读取语言文件
    locales = {}
    all_defined_keys = {}

    for pkg in ['desktop', 'mobile', 'shared']:
        pkg_path = frontend_dir / "packages" / pkg
        locales_dir = pkg_path / "src" / "locales"

        if not locales_dir.exists():
            continue

        for lang in ['zh', 'en']:
            lang_file = locales_dir / f"{lang}.json"
            if lang_file.exists():
                try:
                    data = json.loads(lang_file.read_text(encoding='utf-8'))
                    keys = get_all_keys_from_json(data)
                    all_defined_keys[f"{pkg}.{lang}"] = keys
                    print(f"{pkg}/{lang}.json: {len(keys)} 个键")
                except Exception as e:
                    print(f"  错误: 无法解析 {lang_file}: {e}")

    print("\n" + "="*60)

    # 收集所有代码中使用的键（包括 cross-package）
    all_used_keys_by_pkg = {}

    for pkg in ['desktop', 'mobile', 'shared']:
        pkg_path = frontend_dir / "packages" / pkg
        src_dir = pkg_path / "src"

        if not src_dir.exists():
            continue

        used_keys = find_all_used_keys(src_dir)
        all_used_keys_by_pkg[pkg] = used_keys

    # 检查每个 package
    for pkg in ['desktop', 'mobile', 'shared']:
        print(f"\n检查 package: {pkg}")
        print("-" * 40)

        # shared package 的键可能在 desktop 和 mobile 中使用
        if pkg == 'shared':
            all_used_keys = all_used_keys_by_pkg['shared'] | all_used_keys_by_pkg['desktop'] | all_used_keys_by_pkg['mobile']
            print(f"  shared代码: {len(all_used_keys_by_pkg['shared'])} 个")
            print(f"  desktop代码: {len(all_used_keys_by_pkg['desktop'])} 个")
            print(f"  mobile代码: {len(all_used_keys_by_pkg['mobile'])} 个")
            print(f"  合并检查: {len(all_used_keys)} 个键")
        else:
            all_used_keys = all_used_keys_by_pkg[pkg]
            print(f"  代码中找到 {len(all_used_keys)} 个使用的键")

        # 检查未使用的键
        for lang in ['zh', 'en']:
            key_prefix = f"{pkg}.{lang}"
            if key_prefix not in all_defined_keys:
                continue

            defined_keys = all_defined_keys[key_prefix]

            # 过滤出可能未使用的键
            unused = []
            for key in defined_keys:
                if not check_key_usage(key, all_used_keys):
                    unused.append(key)

            if unused:
                print(f"\n  {lang}.json 可能未使用的键 ({len(unused)} 个):")
                for key in sorted(unused)[:50]:  # 显示前50个
                    print(f"    - {key}")
                if len(unused) > 50:
                    print(f"    ... 还有 {len(unused) - 50} 个")
            else:
                print(f"  {lang}.json: 所有键都被使用 ✓")

            # 检查缺失的键（代码中使用但语言文件中没有）
            # 对于 shared package，检查 shared 自己的键
            # 对于 desktop/mobile，检查自己 + shared 的键
            if pkg == 'shared':
                available_keys = defined_keys
            else:
                # 合并自己和 shared 的键
                shared_keys = all_defined_keys.get(f"shared.{lang}", set())
                available_keys = defined_keys | shared_keys

            missing = []
            for key in all_used_keys:
                if key.endswith('.*') or key == '.':
                    continue  # 跳过动态键和空键
                if key not in available_keys:
                    missing.append(key)

            if missing:
                print(f"\n  {lang}.json 缺失的键 ({len(missing)} 个):")
                for key in sorted(missing)[:30]:
                    print(f"    - {key}")
                if len(missing) > 30:
                    print(f"    ... 还有 {len(missing) - 30} 个")


if __name__ == "__main__":
    main()
