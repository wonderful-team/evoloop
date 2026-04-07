---
id: mem_ref_001
type: reference
privacy: team
title: Python 最佳实践
created_at: '2026-03-25T11:20:00Z'
updated_at: '2026-03-25T11:20:00Z'
version: 1
tags:
- python
- best-practices
- reference
source: imported
confidence: 1.0
---

## Python 项目最佳实践

### 项目结构

```
my_project/
├── src/
│   └── my_package/
│       ├── __init__.py
│       └── module.py
├── tests/
│   ├── __init__.py
│   └── test_module.py
├── docs/
├── pyproject.toml
├── README.md
└── .gitignore
```

### 代码规范

1. **使用 Ruff 进行代码检查和格式化**
   ```toml
   [tool.ruff]
   line-length = 100
   select = ["E", "F", "I", "N", "W"]
   ```

2. **类型注解**
   - 所有函数参数和返回值都应添加类型注解
   - 使用 `mypy` 进行类型检查

3. **测试**
   - 使用 `pytest` 作为测试框架
   - 测试覆盖率目标：> 80%

### 依赖管理

- 使用 `uv` 进行依赖管理
- 锁定文件 (`uv.lock`) 必须提交到版本控制

### 文档

- 使用 Google 风格的文档字符串
- 使用 MkDocs 构建文档站点

### 性能优化

- 使用 `asyncio` 处理 I/O 密集型任务
- 考虑使用 `uvloop` 替代默认事件循环
- 对于 CPU 密集型任务，使用 `multiprocessing`

### 安全

- 使用 `bandit` 进行安全扫描
- 敏感信息使用环境变量管理
- 定期更新依赖（使用 `dependabot`）

### 参考资料

- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [Python Patterns](https://python-patterns.guide/)
