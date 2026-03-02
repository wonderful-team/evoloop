#!/usr/bin/env python3
import os
import re
import json
import sys
from collections import defaultdict

# 配置
PACKAGES_DIR = os.path.join(os.path.dirname(__file__), 'packages')
EXCLUDE_DIRS = {'node_modules', 'dist', '.git', '.next', 'build', 'out', 'gen'}
EXTENSIONS = {'.tsx', '.ts', '.jsx', '.js'}

# 模式匹配
CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')

# i18n 使用提取 (支持单引号、双引号、多参数)
USED_KEY_PATTERNS = [
    re.compile(r'\bt\(\s*["\']([^"\']+)["\']'),
    re.compile(r'<Trans\s+[^>]*i18nKey=["\']([^"\']+)["\']'),
]

# 常用属性中的硬编码字符串 (例如 placeholder="请输入")
ATTR_PATTERNS = [
    re.compile(r'\b(placeholder|title|label|description|alt|message)\s*=\s*["\']([^"\']+)["\']'),
]

# JSX 子元素中的硬编码字符串 (限制在单行内，且不包含明显代码特征)
JSX_TEXT_SINGLE_LINE = re.compile(r'>\s*([^<>{}\s][^<>{}]*[^<>{}\s])\s*<')

# 技术性字符串排除 (简化的启发式)
TECHNICAL_EXCLUSIONS = [
    re.compile(r'^https?://'),
    re.compile(r'^sk-[a-zA-Z0-9]{20,}'), # API Key 模式
    re.compile(r'^[A-Z_0-9]+$'), # 全大写常量
    re.compile(r'\.css$'),
    re.compile(r'^[a-z0-9-]+$'), # 可能是 ID 或 类名
    re.compile(r'.*([=]{2,3}|&&|\|\||=>|\?|:).*'), # 逻辑/三元运算符特征
]

def is_technical(s):
    s = s.strip()
    if not s: return True
    if len(s) < 2: return True
    for p in TECHNICAL_EXCLUSIONS:
        if p.match(s):
            return True
    return False

def get_locale_files(root_dir):
    locales = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith('.json') and ('locales' in root or 'i18n' in root):
                locales.append(os.path.join(root, file))
    return locales

def flatten_dict(d, parent_key='', sep='.'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def scan_file(file_path):
    issues = []
    keys_found = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        content = "".join(lines)
        
        # 1. 提取使用的 i18n keys
        for p in USED_KEY_PATTERNS:
            keys_found.update(p.findall(content))
        
        # 2. 逐行检测
        in_multiline_comment = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 注释处理
            if '/*' in stripped: in_multiline_comment = True
            if '*/' in stripped: 
                in_multiline_comment = False
                continue
            if in_multiline_comment or stripped.startswith('//') or stripped.startswith('import ') or stripped.startswith('*'):
                continue

            # 排除 console 和 throw
            if 'console.' in stripped or 'throw new Error' in stripped:
                continue

            # 检测硬编码中文 (排除已在 t() 中的)
            if CHINESE_PATTERN.search(line):
                # 简单检查是否在 t("...") 中
                if not re.search(r't\(["\'].*?'+re.escape(CHINESE_PATTERN.search(line).group())+'.*?["\']', line):
                    issues.append({
                        'type': 'Hardcoded Chinese',
                        'line': i + 1,
                        'content': stripped
                    })
            
            # 检测单行 JSX 文本
            for match in JSX_TEXT_SINGLE_LINE.finditer(line):
                text = match.group(1).strip()
                if CHINESE_PATTERN.search(text): continue # 中文已处理
                if any(c.isalpha() for c in text) and not is_technical(text):
                    # 避免匹配到 TS 泛型，检查前一个非空字符
                    pre_content = line[:match.start()].strip()
                    if pre_content.endswith('=') or pre_content.endswith('('): # 可能是赋值或调用，不是 JSX Text
                        continue
                    issues.append({
                        'type': 'Hardcoded JSX Text',
                        'line': i+1,
                        'content': text
                    })

        # 3. 检测硬编码 UI 属性 (在全文中匹配以便处理跨行)
        for pattern in ATTR_PATTERNS:
            for match in pattern.finditer(content):
                attr_name, attr_val = match.groups()
                if not attr_val.strip().startswith('{') and not CHINESE_PATTERN.search(attr_val):
                    if not is_technical(attr_val):
                        line_no = content.count('\n', 0, match.start()) + 1
                        issues.append({
                            'type': f'Hardcoded Attr ({attr_name})',
                            'line': line_no,
                            'content': attr_val
                        })
                    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        
    return issues, keys_found

def main():
    print("开始扫描 I18n 状态 (已优化优化逻辑)...")
    
    all_issues = defaultdict(list)
    all_used_keys = set()
    all_defined_keys = {}
    
    locale_files = get_locale_files(PACKAGES_DIR)
    for lf in locale_files:
        try:
            with open(lf, 'r', encoding='utf-8') as f:
                data = json.load(f)
                flattened = flatten_dict(data)
                all_defined_keys[lf] = set(flattened.keys())
        except Exception as e:
            print(f"无法解析多语言文件 {lf}: {e}")

    for root, dirs, files in os.walk(PACKAGES_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if any(file.endswith(ext) for ext in EXTENSIONS):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, PACKAGES_DIR)
                
                issues, k = scan_file(file_path)
                if issues:
                    all_issues[rel_path].extend(issues)
                all_used_keys.update(k)

    print("\n" + "="*50)
    print("报告: 硬编码字符串 (过滤了组件/技术参数/注释)")
    print("="*50)
    
    for file, issues in sorted(all_issues.items()):
        print(f"\n[文件] {file}")
        for issue in sorted(issues, key=lambda x: x['line']):
            print(f"  L{issue['line']}: [{issue['type']}] -> {issue['content']}")

    print("\n" + "="*50)
    print("报告: 未使用的 I18n Keys (支持多参数匹配)")
    print("="*50)
    
    unused_found = False
    for lf, defined_keys in all_defined_keys.items():
        rel_lf = os.path.relpath(lf, PACKAGES_DIR)
        unused = defined_keys - all_used_keys
        if unused:
            unused_found = True
            print(f"\n[语言文件] {rel_lf}")
            for k in sorted(unused):
                print(f"  - {k}")
    
    if not unused_found:
        print("未发现未使用的 key。")

    print("\n" + "="*50)
    print("扫描完成。")

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
