"""Vulture 白名单：框架反射 / 接口兼容导致的静态分析误报。

原则：只收「确属误报」的名字并注明原因；真死代码一律删除，禁止进白名单。
运行：`make deadcode`（配置见 pyproject.toml [tool.vulture]）。
vulture 按名字全局匹配，这里的属性引用即视为「已使用」。
"""


class _:
    """白名单载体（不被执行，仅供 vulture 名字匹配）。"""


# pydantic 事件 schema 字段：序列化/验证经反射读取（app/**/event/schemas.py 等）
_.__context  # noqa: B018

# VoiceInputChannel.bind 接口兼容参数：签名与其它 InputChannel 对齐，实现仅用 agent_run_registry
_.state_machine  # noqa: B018
_.state_enum  # noqa: B018

# SQLAlchemy PoolEvents.checkout 派发签名要求（见 pool_leak_probe._on_checkout 的 noqa 注释）
_.connection_proxy  # noqa: B018

# ResourceManager.initialize 已废弃参数：保留签名兼容存量调用方（docstring 标注 Deprecated）
_.seed_data  # noqa: B018

# huey Celery 兼容 API：apply_async(args, kwargs, **opts) 接受并忽略调度选项
_.opts  # noqa: B018

# Windows 兜底 pwd.getpwuid 假实现：必须与 stdlib 签名一致
_.uid  # noqa: B018
