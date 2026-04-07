---
id: mem_user_001
type: user
privacy: private
title: 用户编码偏好
created_at: '2026-04-01T15:30:00Z'
updated_at: '2026-04-01T15:30:00Z'
version: 1
tags:
- preferences
- coding-style
- python
source: extracted
confidence: 0.95
user_id: user_123
---

## Python 编码风格偏好

用户偏好以下 Python 代码风格：

1. **引号使用**：优先使用双引号 `"` 而非单引号 `'`
2. **类型注解**：所有函数参数和返回值都应添加类型注解
3. **文档字符串**：使用 Google 风格的文档字符串
4. **行长度**：每行不超过 100 个字符
5. **导入排序**：按标准库、第三方库、本地库分组

### 示例代码

```python
def process_data(input_data: list[dict]) -> list[dict]:
    """处理输入数据并返回结果。
    
    Args:
        input_data: 输入数据列表，每项为字典格式
        
    Returns:
        处理后的数据列表，只保留 active 项
    """
    return [item for item in input_data if item.get("active")]
```

### 特殊偏好

- 喜欢使用 `pathlib` 而不是 `os.path`
- 偏好 `f-string` 而不是 `.format()`
- 在测试中使用 `pytest` 而不是 `unittest`
