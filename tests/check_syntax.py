#!/usr/bin/env python3
"""
批量语法和导入检查脚本

用法:
    python check_syntax.py                          # 检查所有修改过的文件
    python check_syntax.py --file path/to/file.py   # 检查单个文件
    python check_syntax.py --all                    # 检查整个 backend 目录
"""

import ast
import os
import sys
import argparse
from pathlib import Path


# 内置名称和常见无需导入的名称
BUILTINS = {
    'len', 'range', 'print', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple',
    'open', 'isinstance', 'hasattr', 'getattr', 'setattr', 'type', 'super', 'object',
    'Exception', 'BaseException', 'True', 'False', 'None', 'NotImplemented',
    'os', 'sys', 'json', 'logging', 're', 'time', 'datetime', 'uuid', 'hashlib',
    'Optional', 'List', 'Dict', 'Any', 'Union', 'Callable', 'Tuple', 'Set',
    'Generator', 'Iterator', 'Iterable', 'Type', ' cast',
    # 常见异常
    'ValueError', 'TypeError', 'KeyError', 'IndexError', 'AttributeError',
    'ImportError', 'ModuleNotFoundError', 'RuntimeError', 'NotImplementedError',
    'FileNotFoundError', 'PermissionError', 'ConnectionError',
    # 上下文管理器
    'self', 'cls',
}


def check_file(filepath):
    """检查单个文件的语法和导入问题"""
    results = {
        'syntax_ok': True,
        'syntax_error': None,
        'undefined_names': [],
        'imports': set(),
        'line_count': 0,
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        results['line_count'] = len(source.splitlines())
    except Exception as e:
        results['syntax_ok'] = False
        results['syntax_error'] = f"Cannot read file: {e}"
        return results
    
    # 语法检查
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        results['syntax_ok'] = False
        results['syntax_error'] = f"Line {e.lineno}: {e.msg}"
        return results
    
    # 收集导入
    imported_names = set()
    imported_modules = set()
    defined_names = set()  # 函数、类定义
    used_names = {}  # name -> line number
    
    for node in ast.walk(tree):
        # Import
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name.split('.')[0]
                imported_names.add(name)
        
        # From Import
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                imported_names.add(name)
        
        # 函数定义
        elif isinstance(node, ast.FunctionDef):
            defined_names.add(node.name)
            for arg in node.args.args:
                if arg.arg != 'self':
                    defined_names.add(arg.arg)
            for default in node.args.defaults:
                if isinstance(default, ast.Name):
                    used_names[default.id] = getattr(default, 'lineno', 0)
        
        # 类定义
        elif isinstance(node, ast.ClassDef):
            defined_names.add(node.name)
        
        # 赋值（全局变量）
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)
        
        # 名称使用
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in BUILTINS and not node.id.startswith('_'):
                used_names[node.id] = node.lineno
        
        # 函数调用
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in BUILTINS and not node.func.id.startswith('_'):
                    used_names[node.func.id] = node.func.lineno
    
    # 检查未定义的名称
    for name, line in used_names.items():
        if name not in imported_names and name not in defined_names and name not in BUILTINS:
            results['undefined_names'].append((name, line))
    
    results['imports'] = imported_names
    return results


def get_files_to_check():
    """获取需要检查的文件列表"""
    # 修改过的文件列表
    modified_files = [
        'backend/app/domain/tools/scheduler.py',
        'backend/app/domain/tools/document_reader.py',
        'backend/app/domain/tools/wiki_tools.py',
        'backend/app/domain/tools/manage_todo.py',
        'backend/app/domain/tools/memory_search.py',
        'backend/app/domain/tools/research.py',
        'backend/app/domain/tools/checkpoint_tools.py',
        'backend/app/domain/tools/facades.py',
        'backend/app/domain/tools/memory.py',
        'backend/app/domain/tools/environment/ranking.py',
        'backend/app/core/environment/controllers/mobile_controller.py',
        'backend/app/core/environment/controllers/browser_controller.py',
        'backend/app/core/environment/controllers/desktop_controller.py',
        'backend/app/core/learning/prompts/builder.py',
        'backend/app/core/engine/prompts/finish.py',
        'backend/app/core/engine/prompts/supervisor_builder.py',
        'backend/app/core/engine/nodes/finish.py',
        'backend/app/api/routes/agent.py',
        'backend/app/utils/controller_response.py',
    ]
    return modified_files


def main():
    parser = argparse.ArgumentParser(description='批量检查 Python 文件语法和导入')
    parser.add_argument('--file', help='检查单个文件')
    parser.add_argument('--all', action='store_true', help='检查整个 backend 目录')
    parser.add_argument('--strict', action='store_true', help='严格模式（检查更多潜在问题）')
    args = parser.parse_args()
    
    if args.file:
        files = [args.file]
    elif args.all:
        files = []
        for root, dirs, filenames in os.walk('backend'):
            for f in filenames:
                if f.endswith('.py'):
                    files.append(os.path.join(root, f))
    else:
        files = get_files_to_check()
    
    print(f"Checking {len(files)} files...\n")
    
    errors = []
    warnings = []
    
    for filepath in files:
        if not os.path.exists(filepath):
            print(f"❌ {filepath}: File not found")
            errors.append(filepath)
            continue
        
        results = check_file(filepath)
        
        if not results['syntax_ok']:
            print(f"❌ {filepath}")
            print(f"   Syntax Error: {results['syntax_error']}")
            errors.append(filepath)
        elif results['undefined_names']:
            print(f"⚠️  {filepath}")
            for name, line in results['undefined_names']:
                print(f"   Line {line}: '{name}' may be undefined")
            warnings.append(filepath)
        else:
            print(f"✅ {filepath} ({results['line_count']} lines)")
    
    print(f"\n{'='*60}")
    print(f"Total: {len(files)} files")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    
    if errors:
        sys.exit(1)
    elif warnings:
        print("\n⚠️  Some files have potential issues (warnings)")
        sys.exit(0)
    else:
        print("\n✅ All files look good!")
        sys.exit(0)


if __name__ == '__main__':
    main()
