# Browser JS 执行环境验证机制设计

## 问题本质

Agent 混淆了 **Node.js 环境** vs **Browser 环境**。

| 环境 | 特点 | 常见错误 |
|------|------|----------|
| **Node.js** | 服务端，有 require/fs/path | Agent 以为 run_js 在这里执行 |
| **Browser** | 客户端，有 fetch/document | run_js 实际在这里执行 |

**目标：** 不需要为每个不支持语法改文档，而是自动检测并给出清晰提示。

---

## 方案：三层防护机制

### 第一层：静态检查（执行前）

在 `browser_controller.py` 中添加语法检测：

```python
# 定义浏览器不支持的语法模式
BROWSER_UNSUPPORTED_PATTERNS = {
    "require": {
        "pattern": r"\brequire\s*\(",
        "message": "'require' is Node.js module syntax, not supported in browser. Use native 'fetch()' or load libraries via CDN.",
        "alternative": "fetch('/api').then(r => r.json())"
    },
    "fs_module": {
        "pattern": r"\bfs\s*\.\s*(readFile|writeFile|appendFile)",
        "message": "'fs' (file system) is Node.js only. Browser cannot access local files directly.",
        "alternative": "Use upload action or fetch to server API"
    },
    "process": {
        "pattern": r"\bprocess\s*\.\s*(env|argv|exit)",
        "message": "'process' is Node.js global, not available in browser.",
        "alternative": "Use window.location or other browser APIs"
    },
    "__dirname": {
        "pattern": r"\b__dirname\b|\b__filename\b",
        "message": "'__dirname/__filename' are Node.js globals.",
        "alternative": "Use window.location.href for current URL"
    },
    "CommonJS_export": {
        "pattern": r"\bmodule\.exports\s*=|\bexports\.",
        "message": "CommonJS exports are Node.js syntax. Browser uses ES modules or global variables.",
        "alternative": "Assign to window.myVar = ... for global access"
    }
}

async def validate_browser_script(script: str) -> tuple[bool, str]:
    """
    Validate script for browser compatibility.
    Returns (is_valid, error_message_with_alternative)
    """
    import re
    
    for check_name, check_config in BROWSER_UNSUPPORTED_PATTERNS.items():
        if re.search(check_config["pattern"], script):
            return False, (
                f"❌ Browser JavaScript Error: {check_config['message']}\n\n"
                f"💡 Try this instead:\n"
                f"   {check_config['alternative']}"
            )
    
    return True, ""
```

**使用：**
```python
elif action == "run_js":
    if not script:
        return ControllerResponse.missing_param("script")
    
    # 第一层：静态检查
    is_valid, error_msg = await validate_browser_script(script)
    if not is_valid:
        return error_msg  # 提前返回，不执行错误代码
    
    # 继续执行...
    result = await page.evaluate(script)
```

**效果：**
- 执行前就拦截错误
- 给出具体替代方案
- 不需要改文档

---

### 第二层：运行时捕获（执行时）

即使通过了静态检查，也可能有其他错误：

```python
async def safe_evaluate_script(page, script: str, selector: str | None = None):
    """
    Safely evaluate script with error translation.
    """
    try:
        if selector:
            return await page.locator(selector).first.evaluate(script)
        else:
            return await page.evaluate(script)
    
    except Exception as e:
        error_str = str(e)
        
        # 翻译常见的浏览器错误
        if "ReferenceError" in error_str and "require" in error_str:
            return (
                f"❌ ReferenceError: 'require' is not defined\n\n"
                f"This is a Node.js feature, not available in browser.\n"
                f"💡 Use native browser APIs like fetch() instead."
            )
        
        elif "ReferenceError" in error_str:
            undefined_var = extract_undefined_var(error_str)
            return (
                f"❌ ReferenceError: '{undefined_var}' is not defined\n\n"
                f"This variable or function doesn't exist in browser context.\n"
                f"💡 Available globals: window, document, fetch, console, localStorage, etc."
            )
        
        elif "SyntaxError" in error_str:
            return (
                f"❌ SyntaxError in JavaScript:\n{error_str}\n\n"
                f"💡 Check your JavaScript syntax. Note: browser uses ES6+, not Node.js syntax."
            )
        
        # 其他错误原样返回
        return f"❌ JavaScript Error: {error_str}"
```

---

### 第三层：文档提示（兜底）

简洁的环境说明，作为兜底：

```python
"""
- run_js: Execute JavaScript in browser page context.
  
  ⚠️ BROWSER ENVIRONMENT - NOT Node.js
  
  Automatic validation enabled for:
  - require() → Suggests fetch()
  - fs module → Suggests server API
  - process → Suggests window
  
  If you get "ReferenceError: X is not defined", 
  X is likely a Node.js feature not available in browser.
"""
```

---

## 架构图

```
Agent 调用 run_js
       │
       ▼
┌──────────────────────┐
│ 第一层：静态检查      │ ← 正则匹配常见错误模式
│ validate_browser_js  │
└──────────────────────┘
       │
       ├── 检测到错误 ──→ 返回友好提示 + 替代方案 ❌
       │
       └── 通过 ────────→ 继续执行
                          │
                          ▼
                   ┌──────────────────────┐
                   │ 第二层：运行时捕获    │ ← Playwright evaluate
                   │ safe_evaluate_script │
                   └──────────────────────┘
                          │
                          ├── 执行错误 ────→ 翻译错误信息 ❌
                          │
                          └── 成功 ────────→ 返回结果 ✅
```

---

## 可扩展性

**新增检测规则，只需要修改配置：**

```python
# 未来发现新的不支持语法，只需添加到这里
BROWSER_UNSUPPORTED_PATTERNS.update({
    "Buffer": {
        "pattern": r"\bBuffer\s*\.\s*(from|alloc)",
        "message": "'Buffer' is Node.js only. Browser uses Uint8Array or TextEncoder.",
        "alternative": "new TextEncoder().encode(string)"
    },
    "new_syntax": {
        "pattern": r"...",
        "message": "...",
        "alternative": "..."
    }
})
```

**不需要修改文档，不需要改业务逻辑。**

---

## 实施建议

### 立即实施（1小时）

1. **添加 `validate_browser_script` 函数**
   - 放在 `browser_controller.py` 或单独模块
   - 包含 require/fs/process/__dirname 检测

2. **在 `run_js` 调用前添加检查**
   ```python
   is_valid, error_msg = await validate_browser_script(script)
   if not is_valid:
       return error_msg
   ```

3. **添加运行时错误翻译**
   - 捕获 ReferenceError/SyntaxError
   - 给出友好的中文/英文提示

### 长期维护

- 发现新的 Agent 错误模式 → 添加到 `BROWSER_UNSUPPORTED_PATTERNS`
- 积累常见替代方案 → 完善 `alternative` 字段

---

## 示例输出

### 场景 1：Agent 使用 require

```
❌ Browser JavaScript Error: 'require' is Node.js module syntax, 
   not supported in browser. Use native 'fetch()' or load libraries via CDN.

💡 Try this instead:
   fetch('/api').then(r => r.json())
```

### 场景 2：Agent 使用 fs

```
❌ Browser JavaScript Error: 'fs' (file system) is Node.js only. 
   Browser cannot access local files directly.

💡 Try this instead:
   Use upload action or fetch to server API
```

### 场景 3：未知错误

```
❌ ReferenceError: 'myCustomModule' is not defined

This variable or function doesn't exist in browser context.
💡 Available globals: window, document, fetch, console, localStorage, etc.
```

---

## 结论

**不需要每次改文档。** 实施三层防护机制后：

1. **静态检查** 拦截 80% 的常见错误
2. **运行时捕获** 处理剩余 20% 的意外错误
3. **自动提示** 给出替代方案

**新语法不支持？只需添加一行配置。**

这样 Agent 能立即知道错在哪里，以及如何修复。
