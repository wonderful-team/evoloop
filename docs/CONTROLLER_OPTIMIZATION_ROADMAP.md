# Controller 性能优化路线图

## 分析时间: 2026-03-28
## 当前状态: Desktop 异步化 ✅ 完成

---

## 🔴 高优先级（强烈建议改进）

### 1. Desktop Controller - `ast.literal_eval` 阻塞
**位置**: `desktop_controller.py` 行 63, 105, 551, 629, 670

**问题**: AX Tree 解析在主线程执行，大页面时可能阻塞数百毫秒

```python
# 当前代码 (阻塞)
elements = ast.literal_eval(raw_tree.replace("missing value", "None"))

# 建议方案
import functools
elements = await asyncio.to_thread(
    functools.partial(ast.literal_eval, raw_tree.replace("missing value", "None"))
)
```

**影响**: 高 | **复杂度**: 低 | **建议**: ✅ **立即改进**

---

### 2. Desktop Controller - 三重引擎串行解析
**位置**: `desktop_controller.py` 行 96-201 `_resolve_element()`

**问题**: AX Tree → Atlas → OCR 顺序执行，每个失败才进下一步

```python
# 当前代码 (串行)
result = await cls._try_ax_tree(...)  # 1-2s
if not result:
    result = await cls._try_atlas(...)  # 0.5s
if not result:
    result = await cls._try_ocr(...)  # 2-3s

# 建议方案 (并行+超时)
results = await asyncio.gather(
    asyncio.wait_for(cls._try_ax_tree(...), timeout=3),
    asyncio.wait_for(cls._try_atlas(...), timeout=1),
    asyncio.wait_for(cls._try_ocr(...), timeout=5),
    return_exceptions=True
)
# 取最快成功的结果
```

**影响**: 高 | **复杂度**: 中 | **建议**: ✅ **建议改进**

---

### 3. Mobile Controller - `resolve_element` 轮询延迟
**位置**: `mobile_controller.py` 行 375-511

**问题**: 500ms 轮询间隔 + 8s 超时 = 最多 16 次循环

```python
# 当前代码
while time.time() - start < timeout:
    await asyncio.sleep(0.5)  # 固定间隔
    # ... 检查元素

# 建议方案 (指数退避)
interval = 0.1  # 从100ms开始
while time.time() - start < timeout:
    # ... 检查元素
    if found:
        break
    await asyncio.sleep(min(interval, 1.0))
    interval *= 1.5  # 指数退避
```

**影响**: 高 | **复杂度**: 低 | **建议**: ✅ **立即改进**

---

### 4. Mobile Controller - `scroll_to_bottom` 频繁 UI dump
**位置**: `mobile_controller.py` 行 703-750

**问题**: 每轮滚动都执行 `dump_ui()` 检查稳定性，ADB 通信开销大

```python
# 当前代码 (每轮dump)
while not stable:
    curr_ui = await dump_ui()  # 昂贵!
    if hash(curr_ui) == prev_hash:
        stable = True

# 建议方案 (截图哈希)
while not stable:
    screenshot = await screenshot()  # 比dump_ui快
    if image_hash(screenshot) == prev_hash:
        stable = True
```

**影响**: 高 | **复杂度**: 中 | **建议**: ✅ **建议改进**

---

### 5. Browser Controller - `get_elements` 串行 DOM 查询
**位置**: `browser_controller.py` 行 424-441

**问题**: 最多 20 个元素，每个串行执行 `bounding_box()` + `inner_text()`

```python
# 当前代码 (串行)
for el in elements[:20]:
    box = await el.bounding_box()  # 往返通信
    text = await el.inner_text()   # 往返通信

# 建议方案 (批量JS)
js = """
elements => elements.map(el => ({
    box: el.getBoundingClientRect(),
    text: el.innerText
}))
"""
results = await page.evaluate(js, await locator.element_handles())
```

**影响**: 高 | **复杂度**: 中 | **建议**: ✅ **建议改进**

---

### 6. Browser Controller - `batch` 操作串行执行
**位置**: `browser_controller.py` 行 703-716

**问题**: 批量操作顺序执行，无法利用 Playwright 的并发能力

```python
# 当前代码 (串行)
for action in actions:
    result = await executor.execute(action)  # 一个一个来

# 建议方案 (并行)
semaphore = asyncio.Semaphore(3)  # 控制并发数
async def bounded_execute(action):
    async with semaphore:
        return await executor.execute(action)
results = await asyncio.gather(*[bounded_execute(a) for a in actions])
```

**影响**: 高 | **复杂度**: 中 | **建议**: ✅ **建议改进**

---

## 🟡 中优先级（可考虑改进）

### 7. Desktop Controller - AX Tree 重复 dump
**位置**: 单次操作内多次调用

**问题**: click → verify 流程中可能重复 dump AX Tree

**方案**: 添加 100-200ms 方法级缓存

**影响**: 中 | **复杂度**: 低 | **建议**: 💡 **可考虑**

---

### 8. Mobile Controller - A11y 结果缓存
**位置**: `mobile_controller.py` 行 395-396

**问题**: 每 500ms 轮询都重新解析 A11y 数据

**方案**: 200ms TTL 缓存

**影响**: 中 | **复杂度**: 低 | **建议**: 💡 **可考虑**

---

### 9. Browser Controller - `wait_for_stability` 频率
**位置**: `browser_controller.py` 行 565-588

**问题**: 每 500ms 执行一次 JS evaluation

**方案**: 增加到 1s 或使用智能退避

**影响**: 中 | **复杂度**: 低 | **建议**: 💡 **可考虑**

---

## 🟢 低优先级（当前可接受）

| 问题 | 位置 | 原因 |
|------|------|------|
| 文件操作异步化 | 多处 | 本地 SSD 文件操作通常 <1ms，收益小 |
| 模板渲染优化 | OCR 结果 | 影响小，仅在 OCR 成功时执行 |
| 截图缓存 TTL | mobile_controller.py | 当前 1s 设置合理 |

---

## 📊 改进收益预估

| 改进项 | 预估性能提升 | 实施建议 |
|--------|-------------|----------|
| ast.literal_eval 异步化 | 避免 100-500ms 卡顿 | 立即做 |
| 三重引擎并行 | 元素解析 2-3x 加速 | 建议做 |
| 轮询退避策略 | 平均查找时间 -30% | 立即做 |
| scroll_to_bottom 优化 | ADB 通信 -50% | 建议做 |
| DOM 查询批量 | 元素获取 5-10x 加速 | 建议做 |
| batch 并行 | 批量任务 3-5x 加速 | 建议做 |

---

## 🎯 推荐实施顺序

### 第1阶段 (立即 - 低风险)
1. Desktop `ast.literal_eval` 异步化
2. Mobile 轮询退避策略

### 第2阶段 (本周 - 中风险)
3. Browser `get_elements` 批量优化
4. Browser `batch` 并行化

### 第3阶段 (可选 - 复杂度较高)
5. Desktop 三重引擎并行
6. Mobile `scroll_to_bottom` 截图优化

---

## ⚠️ 注意事项

1. **不要过度优化**: Mobile 的 `dump_ui` 已经用了 `asyncio.to_thread()`，已经是异步的
2. **测试覆盖**: 每次改动后需要测试对应控制器的核心功能
3. **监控先行**: 建议在优化前添加性能指标采集，用于验证改进效果
