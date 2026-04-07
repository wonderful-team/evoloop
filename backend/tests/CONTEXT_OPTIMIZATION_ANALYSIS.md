# EvoLoop 上下文优化深度分析报告

## 📊 当前状况

### 测试数据对比
| 配置 | 本地 Gateway | 生产 Gateway | 差距 |
|------|-------------|-------------|------|
| 190KB + 6轮 | ~10s | ~4min | **24x** |
| 130KB + 6轮 | ~6s | ~2min | **20x** |
| 30KB + 2轮 | ~7s | ~30s | **4x** |

**结论**: 生产环境仍有优化空间，上下文大小与延迟不成正比。

---

## 🔍 上下文架构分析

### 1. System Prompt 组成 (当前 ~130KB)

```
worker.prompt.j2 (425行)
├── 角色定义 + 指令 (~2KB)
├── 执行协议 (~1KB)
├── 内存使用指南 (~1KB)
├── 角色工具优先级 (~5KB)
│   ├── Desktop/Mobile/Web 协议
│   └── 文件编辑协议 (60行)
├── 环境感知块 environment_block (~20-50KB) ⭐
│   ├── macOS 信息 + 15个常用应用
│   ├── Android 设备 + 10个包名
│   └── 网络状态
├── 系统信息 (~0.5KB)
├── 浏览器自动化协议 (~3KB)
├── 桌面自动化协议 (~25KB) ⭐⭐ 最大块
│   ├── 速度优先规则
│   ├── 批量模式说明
│   ├── 键盘/坐标选择
│   ├── 150+ 行详细示例
│   └── 正确/错误模式对比
├── 移动自动化协议 (~5KB)
├── 约束和防护 (~1KB)
├── 数据可视化指南 (~2KB)
├── 历史上下文 (~10-30KB)
└── 最终报告指南 (~1KB)
```

### 2. 关键常量设置

```python
# app/constants.py
DEFAULT_WINDOW_SIZE = 5              # 保留消息对数
MAX_CONTEXT_CHARS = 50000            # 最大字符数 (~40k tokens)
CONTEXT_PRUNE_THRESHOLD = 10000      # 裁剪阈值
MAX_OUTPUT_LENGTH = 60000            # 工具输出截断
```

### 3. 历史消息窗口管理

```python
# 当前逻辑 (app/core/engine/message_utils.py)
def apply_message_window(
    messages: list[BaseMessage],
    window_size: int = DEFAULT_WINDOW_SIZE,  # = 5
    max_total_chars: int = MAX_CONTEXT_CHARS,  # = 50000
) -> list[BaseMessage]:
    # 1. 保留最近 N 对消息 (Human + AI)
    # 2. 对旧消息进行裁剪 (CONTEXT_PRUNE_THRESHOLD=10000)
    # 3. 如果还超长，截断到 max_total_chars
```

---

## ⚠️ 发现的问题

### 问题 1: System Prompt 包含大量不必要的协议

**观察**: `worker.prompt.j2` 425行，包含：
- Desktop 自动化协议：150+ 行
- Mobile 自动化协议：50+ 行
- 浏览器协议：30+ 行

**影响**: 
- Documenter 角色不需要 Desktop/Mobile 协议
- 每轮请求都携带这些无用内容
- 130KB 中约 40KB 是特定场景协议

### 问题 2: Window Size 设置过于保守

```python
DEFAULT_WINDOW_SIZE = 5  # 只保留5对消息

# 对于长对话，早期上下文丢失严重
# 用户需要重复信息
```

### 问题 3: 环境信息块过大

```python
# app/core/environment/prompt.py
macos_info["top_apps"] = [s.app_name for s in state.macos.app_usage_stats[:15]]
# 15个应用，每个约 50-100字节 = 1-1.5KB

android_packages[:10]  # 10个包名
# 每个包名约 30-50字节 = 0.3-0.5KB
```

### 问题 4: 消息裁剪策略不够智能

```python
# 当前策略：简单截断
if len(str(m.content)) > CONTEXT_PRUNE_THRESHOLD:
    content=str(m.content)[:10000] + "\n... [截断]"

# 问题：可能截断关键信息
# 没有语义分析，不知道哪些内容更重要
```

### 问题 5: 没有 Prompt Caching

```python
# 每次请求都重新构建完整的 System Prompt
# 130KB 的模板渲染 + 变量替换
# 没有复用机制
```

---

## 🎯 优化建议

### 优化 1: 角色特定 Prompt (预计节省 30-40KB)

**实现方式**:
```python
# worker.prompt.j2 修改
{% if role_name == "Documenter" %}
  {# 只包含代码相关协议 #}
  {% include 'fragments/code_protocol.j2' %}
{% elif role_name in ["Desktop", "Mac", "Windows"] %}
  {# 包含桌面自动化协议 #}
  {% include 'fragments/desktop_protocol.j2' %}
{% elif role_name in ["Mobile", "Android"] %}
  {# 包含移动自动化协议 #}
  {% include 'fragments/mobile_protocol.j2' %}
{% endif %}
```

**效果**: 
- Documenter: 130KB → 80KB (节省 40KB)
- Browser: 130KB → 90KB (节省 30KB)

### 优化 2: 动态环境信息 (预计节省 10-20KB)

**当前**:
```python
# 每次都渲染完整环境
macos_info["top_apps"] = 15个应用
android_devices = 完整设备信息
```

**优化后**:
```python
# 只渲染必要的设备信息
def render_minimal_environment(role_name):
    if "Desktop" in role_name:
        return render_desktop_env(minimal=True)  # 只包含 top 5 apps
    elif "Mobile" in role_name:
        return render_mobile_env(minimal=True)   # 只包含基础信息
    else:
        return ""  # Documenter 不需要环境信息
```

### 优化 3: 增大 Window Size (平衡内存和上下文)

```python
# constants.py
# 当前
DEFAULT_WINDOW_SIZE = 5
MAX_CONTEXT_CHARS = 50000

# 优化后 (针对 Kimi 200K 上下文)
DEFAULT_WINDOW_SIZE = 10              # 2倍历史
MAX_CONTEXT_CHARS = 100000            # 2倍字符数 (~80k tokens)
CONTEXT_PRUNE_THRESHOLD = 5000        # 更早裁剪，保留更多消息
```

### 优化 4: 智能消息摘要 (替代简单截断)

```python
# 新策略：对旧消息进行摘要，而非截断
async def smart_message_compression(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    1. 保留最近 3 轮完整对话
    2. 对 3-10 轮进行轻量摘要 (保留关键动作和结果)
    3. 对 10 轮之前的进行重度摘要 (只保留结论)
    """
    # 使用 LLM 或规则进行摘要
    pass
```

### 优化 5: Prompt Caching (减少重复渲染)

```python
# 缓存静态部分
_system_prompt_cache = {}

def get_cached_system_prompt(role_name, environment_hash):
    cache_key = f"{role_name}:{environment_hash}"
    
    if cache_key not in _system_prompt_cache:
        # 渲染并缓存
        _system_prompt_cache[cache_key] = render_template(...)
    
    return _system_prompt_cache[cache_key]
```

### 优化 6: 流式 Prompt 构建

```python
# 当前：一次性构建完整 prompt
system_prompt = render_template("worker.prompt.j2", **all_vars)  # 130KB

# 优化：增量构建
base_prompt = get_cached_base_prompt(role_name)  # 60KB (缓存)
environment = get_minimal_environment(role)       # 10KB (动态)
history = get_compressed_history(window=10)       # 30KB (裁剪)
# 总计: 100KB，构建速度提升 50%
```

---

## 📋 实施优先级

| 优化项 | 难度 | 效果 | 优先级 |
|--------|------|------|--------|
| 角色特定 Prompt | 中 | 高 (-40KB) | ⭐⭐⭐ |
| 动态环境信息 | 低 | 中 (-15KB) | ⭐⭐ |
| Prompt Caching | 低 | 中 (提速) | ⭐⭐ |
| 增大 Window Size | 低 | 中 (质量↑) | ⭐⭐ |
| 智能消息摘要 | 高 | 高 (质量↑↑) | ⭐ |
| 流式构建 | 中 | 中 (提速) | ⭐ |

---

## 🔧 快速实施指南

### 第一步：修改常量 (5分钟)

```python
# app/constants.py
DEFAULT_WINDOW_SIZE = 10              # 从 5 改为 10
MAX_CONTEXT_CHARS = 80000             # 从 50000 改为 80000
CONTEXT_PRUNE_THRESHOLD = 5000        # 从 10000 改为 5000
```

### 第二步：环境信息精简 (15分钟)

```python
# app/core/environment/prompt.py
def render_environment_block(tips: bool = True, skip_hydrate: bool = False) -> str:
    # ... 现有代码 ...
    
    # 精简 top_apps
    if state.macos and state.macos.installed_apps:
        macos_info["top_apps"] = [s.app_name for s in state.macos.app_usage_stats[:5]]  # 15 -> 5
    
    # 精简 Android 包名
    if dev.installed_packages:
        dev_data["top_pkgs"] = dev.installed_packages[:3]  # 10 -> 3
```

### 第三步：角色特定模板 (30分钟)

```jinja2
{# worker.prompt.j2 #}
{# 将 Desktop/Mobile 协议移到条件块 #}

{% if "Desktop" in role_name or "Mac" in role_name or "Windows" in role_name %}
## 🖥 Desktop Automation Protocol
... (150行协议)
{% endif %}

{% if "Mobile" in role_name or "Android" in role_name %}
## 📱 Mobile Automation Protocol
... (50行协议)
{% endif %}
```

---

## 📊 预期效果

### 优化后对比

| 指标 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| System Prompt | 130KB | 80KB | -38% |
| Window Size | 5轮 | 10轮 | +100% |
| 构建时间 | ~50ms | ~20ms | -60% |
| 生产 190KB 延迟 | ~4min | ~1.5min | -62% |

---

## 🎯 总结

1. **短期优化** (立即实施): 修改常量 + 精简环境信息 = 节省 20-30KB
2. **中期优化** (本周): 角色特定模板 = 节省 30-40KB
3. **长期优化** (下月): 智能摘要 + Prompt Caching = 提升质量 + 速度

**建议立即实施第一步和第二步**，可以在不改变架构的情况下获得显著改善。
