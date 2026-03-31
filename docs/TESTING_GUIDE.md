# macOS 优化测试指南

## 🎯 测试策略概览

```
┌─────────────────────────────────────────────────────────────┐
│                    三层测试体系                              │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: 单元测试 (本地，立即执行)                          │
│    - 快捷键映射正确性                                       │
│    - Batch 规划逻辑                                         │
│    - 性能基准                                               │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: 集成测试 (需要后端环境)                            │
│    - 快捷键自动转换                                         │
│    - Batch 执行流程                                         │
│    - 提示词注入效果                                         │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: 真实环境 A/B 测试 (需要 macOS + 后端)              │
│    - 微信发送消息耗时对比                                    │
│    - Chrome 搜索耗时对比                                     │
│    - 持续性能监控                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 1️⃣ 单元测试（立即执行）

### 运行方式

```bash
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
python -m pytest tests/monitoring/test_macos_optimization.py -v
```

### 预期输出

```
✅ WeChat shortcuts test passed
✅ Chrome shortcuts test passed  
✅ Generic shortcuts test passed
✅ Unknown element returns None
✅ Same focus steps batched correctly
✅ Cross-focus steps separated correctly
✅ Shortcut lookup: 1000 calls in 3.45ms
✅ Batch planning: 100 steps in 12.34ms
```

### 测试内容

| 测试 | 目的 | 通过标准 |
|------|------|---------|
| 快捷键映射 | 验证 shortcuts.py 正确性 | 36 个快捷键全部匹配 |
| Batch 规划 | 验证规划逻辑正确性 | 同焦点合并，跨焦点分离 |
| 性能基准 | 验证查询速度 | 1000 次查询 < 10ms |

---

## 2️⃣ 集成测试（需要后端环境）

### 准备环境

```bash
# 1. 确保后端依赖安装
cd backend
pip install -e .

# 2. 设置环境变量
export ENABLE_PARTIAL_SCREENSHOT=true

# 3. 启动后端（如果测试需要）
# uvicorn app.main:app --reload
```

### 测试快捷键转换

```python
# test_integration.py
import asyncio
from app.core.environment.controllers.desktop_controller import DesktopController

async def test_shortcut_conversion():
    """测试：click('发送') 自动转换为 key_press('cmd+return')"""
    
    # Mock 当前应用为微信
    with mock.patch('app.infrastructure.drivers.macos.macos_driver.get_current_app',
                   return_value={'bundle_id': 'com.tencent.xinWeChat'}):
        
        with mock.patch('app.infrastructure.drivers.macos.macos_driver.key_press') as mock_key:
            
            result = await DesktopController.execute(
                action="click",
                element_name="发送"
            )
            
            # 验证：应该调用 key_press，而不是 click
            mock_key.assert_called_once_with("cmd+return")
            print("✅ 快捷键自动转换生效！")

asyncio.run(test_shortcut_conversion())
```

### 测试 Batch 提速

```python
async def test_batch_speed():
    """对比：批量 vs 单步"""
    
    import time
    
    # 单步执行（模拟）
    start = time.time()
    for _ in range(3):
        await DesktopController.execute(action="key_press", key="a")
        await asyncio.sleep(0.5)  # 模拟验证延迟
    single_time = time.time() - start
    
    # Batch 执行
    start = time.time()
    await DesktopController.execute(
        action="batch",
        actions=[
            {"action": "key_press", "key": "a"},
            {"action": "key_press", "key": "a"},
            {"action": "key_press", "key": "a"},
        ],
        delay_ms=100
    )
    batch_time = time.time() - start
    
    print(f"单步: {single_time:.2f}s")
    print(f"Batch: {batch_time:.2f}s")
    print(f"提速: {(single_time/batch_time - 1)*100:.0f}%")
```

---

## 3️⃣ 真实环境 A/B 测试（推荐）

### 创建性能基线

```bash
# 在优化前（或对比时）创建基线
cd backend/tests/monitoring
python test_real_world_ab.py baseline

# 这会创建 /tmp/evoloop_baseline.json
```

### 运行 A/B 测试

```bash
# 运行对比测试
python test_real_world_ab.py ab

# 输出示例：
🧪 测试场景: wechat_send_message
模式: baseline
  运行 1/5... 8.45s
  运行 2/5... 8.12s
  ...

模式: optimized
  运行 1/5... 3.21s
  运行 2/5... 3.15s
  ...

📊 A/B 测试报告
wechat_send_message:
  优化前: 8.32s
  优化后: 3.18s
  提升: 61.8% (2.6x faster)
```

### 持续监控

```bash
# 持续监控 10 分钟
python test_real_world_ab.py monitor 10

# 输出：
✅ desktop_operation: 245ms
✅ desktop_operation: 198ms
✅ desktop_operation: 312ms

最近 60 秒统计:
  desktop_operation: 252ms avg, 12 ops
```

---

## 4️⃣ 生产环境验证（最重要）

### 方案 A：影子测试（推荐）

```python
# 在生产环境中同时运行新旧逻辑，对比但不影响结果

class ShadowTester:
    """影子测试：同时执行，对比结果"""
    
    async def execute_with_shadow(self, action, **kwargs):
        # 主逻辑：使用优化后的代码
        result = await self.optimized_execute(action, **kwargs)
        
        # 影子逻辑：在后台运行旧代码，记录差异
        asyncio.create_task(self.run_shadow(action, **kwargs))
        
        return result
    
    async def run_shadow(self, action, **kwargs):
        start = time.time()
        old_result = await self.baseline_execute(action, **kwargs)
        old_time = time.time() - start
        
        # 记录对比数据
        logger.info(f"Shadow test: old={old_time:.2f}s, diff={old_time/new_time:.2f}x")
```

### 方案 B：特征标志（Feature Flag）

```python
# 使用配置开关控制是否启用优化

if settings.ENABLE_SPEED_OPTIMIZATION:
    # 使用优化路径
    result = await optimized_path()
else:
    # 使用原路径
    result = await baseline_path()

# 通过环境变量控制
ENABLE_SPEED_OPTIMIZATION=true uvicorn app.main:app
```

### 方案 C：金丝雀发布

```python
# 只对部分用户/请求启用优化

import random

async def desktop_control(action, **kwargs):
    # 10% 流量使用优化版本
    if random.random() < 0.1:
        return await optimized_execute(action, **kwargs)
    else:
        return await baseline_execute(action, **kwargs)
```

---

## 5️⃣ 观察指标

### 关键指标

| 指标 | 优化前 | 优化后目标 | 测量方式 |
|------|--------|-----------|---------|
| 微信发消息耗时 | ~8s | <4s | A/B 测试 |
| API 调用次数 | 6-8 次 | 2-3 次 | 日志统计 |
| Token 消耗 | ~4000 | ~1500 | LLM 调用记录 |
| 成功率 | ~70% | >85% | 错误日志 |

### 监控仪表板

```python
# 简单的监控打印
from app.core.monitoring import perf_monitor

@perf_monitor.track("desktop_operation")
async def desktop_control(action, **kwargs):
    result = await execute(action, **kwargs)
    return result

# 自动打印：
# ✅ desktop_operation: 245ms | shortcut_used=True | batch_size=3
```

---

## 6️⃣ 快速验证清单

### 立即验证（1 分钟）

```bash
# 1. 单元测试
python backend/tests/monitoring/test_macos_optimization.py

# 2. 检查快捷键配置
python -c "from app.core.shortcuts import SHORTCUTS; print(f'Configured: {len(SHORTCUTS)} apps')"

# 3. 检查提示词
grep -A 5 "SPEED FIRST" backend/app/domain/tools/environment/desktop.py
```

### 完整验证（10 分钟）

```bash
# 1. 启动后端
cd backend && uvicorn app.main:app &

# 2. 运行集成测试
pytest tests/monitoring/test_macos_optimization.py::TestIntegration -v

# 3. 创建基线
python tests/monitoring/test_real_world_ab.py baseline

# 4. 运行 A/B 测试
python tests/monitoring/test_real_world_ab.py ab
```

---

## 7️⃣ 故障排查

### 问题：快捷键未生效

```bash
# 检查 1：确认导入
python -c "from app.core.shortcuts import get_shortcut; print(get_shortcut('com.tencent.xinWeChat', '发送'))"
# 应输出: cmd+return

# 检查 2：确认集成
python -c "from app.core.environment.controllers.desktop_controller import DesktopController; print('Shortcut import' in open('app/core/environment/controllers/desktop_controller.py').read())"
# 应输出: True
```

### 问题：Batch 未生效

```bash
# 检查提示词是否包含 batch 示例
grep -A 20 "EXAMPLE 1" backend/app/domain/tools/environment/desktop.py
```

### 问题：性能未提升

```bash
# 开启详细日志
LOG_LEVEL=DEBUG python -m pytest tests/monitoring/test_macos_optimization.py -v

# 检查是否有转换发生
# 日志中应包含："🚀 Converting click to shortcut"
```

---

## 总结

| 测试层级 | 执行时间 | 置信度 | 推荐频率 |
|---------|---------|--------|---------|
| 单元测试 | 10s | 30% | 每次提交 |
| 集成测试 | 5min | 60% | 每次发布 |
| A/B 测试 | 30min | 90% | 每周 |
| 生产监控 | 持续 | 95% | 实时 |

**推荐流程**:
1. 开发时：单元测试确保逻辑正确
2. 发布前：集成测试验证集成效果
3. 发布后：A/B 测试 + 持续监控验证真实效果
