# 代码审计缺陷：生产者→消费者链路契约错配

- **发现时间**: 2026-08-07
- **类型**: 代码审计（非 E2E 自动生成）
- **范围**: app/ 全域数据链路（producer→consumer 字段契约）

## 背景

系统性审计"生产者→消费者"数据链路，发现多类字段契约错配：生产者（驱动/事件/服务）返回的 dict/对象字段名与消费者读取的字段名不一致，导致静默渲染为空/默认值。根因是**驱动/事件返回裸 dict + 消费方各写各的 `.get()`**，无类型化契约兜底。

## 缺陷清单（按严重度）

### 🔴 已修复：macOS get_current_app 缺 bundle_id/title（Atlas 学习链失效）

- **链路**: `macos_driver.get_current_app()` → `_utils.py` / `vision/engine.py` / `find_element.py` / `_element_mixin.py`
- **问题**: 驱动只返回 `{name, pid, bounds}`，消费方读 `bundle_id`/`title` → 恒为默认
- **影响**: macOS 上 Atlas 视觉→空间记忆学习整链静默失效（bundle_id 恒 "unknown" → atlas/engine.py 直接 return）
- **修复**: 驱动补 `bundle_id`（NSRunningApplication.bundleIdentifier）+ `title`（AX）；中层建 `CurrentApp` 类型化模型 + `get_current_app_context()` 访问器；4 个消费方改类型化访问
- **状态**: ✅ 已修复（2026-08-07）

### 🔴 已修复：macOS get_system_info 缺 cpu/ram_gb（HostEnvironment 空字段）

- **链路**: `macos_driver.get_system_info()` → `discovery._probe_macos_impl` → HostEnvironment
- **问题**: 驱动返回 `{model, os_version, memory(字符串), platform}`，消费方读 `cpu`/`ram_gb`
- **影响**: macOS HostEnvironment 的 cpu="Unknown"、ram_gb=0（agent 环境感知缺字段）
- **状态**: ✅ 已修复（2026-08-07）

### 🟠 已修复：BOUNDARY_LEARNED 事件键名错配

- **链路**: `boundaries.py` publish → `environment/event/subscribers.py:226`
- **问题**: 生产 `{tool_name, category, description}`，订阅方读 `data.get("platform")` / `data.get("boundary_type")`，恒 None
- **修复**: 订阅方改读 `tool_name`/`category`/`description`
- **状态**: ✅ 已修复（2026-08-07）

### 🟠 已修复：AWAKENING_COMPLETE 事件键名错配

- **链路**: `lifecycle.py` publish → `environment/event/subscribers.py:203`
- **问题**: 生产 `{platforms, project_id}`，订阅方读 `data.get("project")`，恒 None
- **修复**: 订阅方改读 `project_id`
- **状态**: ✅ 已修复（2026-08-07）

### 🟡 已修复：MacroEngine fallback_context 键名错配

- **链路**: `macro/engine/__init__.py` → `SkillResponse.error` → `skill_error_details.j2`
- **问题**: 生产 `{step_number, event_type}`，消费方读 `fallback_context.get("failed_step")`，错误详情行恒空
- **修复**: engine 的 4 处 fallback_context 统一补 `failed_step`（完整 step dict）
- **状态**: ✅ 已修复（2026-08-07）

### 🟡 已修复：AgentRunCompletedEvent 失败路径缺 outcome/summary

- **链路**: `monitoring/activity.py:_publish_run_completed` → `web_channel.py`
- **问题**: 失败路径 payload 只含 `{run_id, task_type}`，无 `outcome`/`summary`
- **修复**: 补 `outcome=result.status`
- **状态**: ✅ 已修复（2026-08-07）

### 🟡 已修复：plan step status 'done' vs 'completed'

- **链路**: `models/planning.py` 枚举 `{pending, in_progress, completed, failed}` → `supervisor_context_ticket.j2` / `finish_audit_ticket.j2` 判 `s.status == 'done'`
- **修复**: 两个模板改为判 `'completed'`
- **状态**: ✅ 已修复（2026-08-07）

### 🟡 已修复：telemetry.active_window 从未填充

- **链路**: `TelemetrySnapshot.active_window` → `worker_mission_ticket.j2`
- **问题**: 字段恒 None；且填充后 `.title` 与 `get_active_window().window_title` 不一致
- **修复**: `get_telemetry_snapshot` 填充 active_window（macOS）；模板改读 `window_title`
- **状态**: ✅ 已修复（2026-08-07）

### ⚪ 死订阅：SKILL_EXECUTED/PROMOTED/DEPRECATED

- **链路**: 原 `environment/event/subscribers.py` 有订阅，全 app 无任何发布方
- **处理**: 已从 environment 模块**迁回学习域**（`app/core/learning/event/`，`SkillEventType` + `SkillEventSubscriber`），消除放置异味；事件类型从 environment `EventType` 移除
- **状态**: ⏳ 仍需学习/技能域业务确认是否补发布方（`skill.executed/promoted/deprecated` 目前无生产者）

## 清理记录

### ✅ 已清理：`app/core/fingerprint.py`（兼容 shim）

- **删除时间**: 2026-08-07
- **删除前验证**：设备注册链（`websocket_link` → `device.get_hardware_fingerprint` → `register_device`）从 `app.core.device` 导入，不依赖 fingerprint.py；指纹确定性 + 32 字符 + machine_id 同源验证通过
- **删除后**：全库零残留引用，46 integration 测试通过

### ⏸️ 保留：`adb.get_package_info()`（手机域）

- 按业务决定，adb/手机域逻辑不动

### ✅ 已清理：应用层直接调驱动（context_probe / macro _executors）

- `routing/context_probe.py:17`、`macro/engine/_executors.py:181` 改走中层 `get_current_app_context()` 出口（分层一致性）

### ⏸️ 暂未处理：`adb.get_package_info()` 死方法

- 手机域逻辑，按业务决定保留

## 复现/验证

- 各链路验证脚本见 `tests/integration/test_device_environment_chains.py`

## 运行时缺陷（2026-08-07 日志抓取）

### 🔴 已修复：persist_file_operation_task 同名冲突自递归

- **现象**: huey 任务 `engine_persist_file_operation` 执行失败 `TypeError: object Result can't be used in 'await' expression`
- **根因**: `app/core/engine/tasks.py` 中核心实现（原 line 54）与 `@shared_task` 包装器（原 line 109）**同名** `persist_file_operation_task`。包装器内部 `await persist_file_operation_task(...)` 因 Python 名字解析指向自身（最后的定义），调用返回 huey `Result` 对象而非可 await 的协程
- **修复**: 核心实现改名 `_persist_file_operation`（私有），包装器改调 `_persist_file_operation`；全库扫描确认无其他任务包装器自递归
- **状态**: ✅ 已修复（2026-08-07）

## 新能力（2026-08-07）

### ✨ LAN 设备发现（mDNS/DNS-SD）

- **能力**: 探测局域网内广播 Bonjour/mDNS 服务的设备，并分类设备类型（tv/speaker/computer/printer/smart_home/unknown）
- **实现**:
  - `app/core/environment/lan_discovery.py` — `probe_lan_devices()`（zeroconf AsyncServiceBrowser 两阶段：枚举服务类型 → 解析实例）+ `classify_device_type()`（服务类型映射表）+ TXT 元数据提取（model/manufacturer）
  - `schemas/models.py` 新增 `LanDevice(ip, name, device_type, manufacturer, model, services, port)`
  - `AwakenedState.lan_devices` 字段 + `lifecycle.awaken()` 并行 gather
  - `build_environment_summaries()` 暴露 `lan_devices` → `awareness.j2` 新增 "LAN Devices" 片段
- **依赖**: `zeroconf>=0.136.0` 从可选提为正式依赖（pyproject）
- **验证**: 真实网络探测到 4 台设备并分类；53 integration 测试全过
- **增强**: ① 优先级分类（computer > tv > printer > smart_home > speaker，多服务设备确定性定类）② MAC OUI 厂商（`manuf` IEEE 库 ~3 万条 + 常用品牌名兜底）③ 浏览期间增量解析（`create_task` 立即解析，最大化窗口内服务捕获 → 多服务设备定类稳定不再抖动）④ **蓝牙探索**（`system_profiler SPBluetoothDataType`，非特权）：拿到手机名称/Vendor ID→品牌/Minor Type→类型，按"Mobile Phone↔mobile"与 LAN 设备合并丰富
- **验证**: 真实网络稳定识别 LAN 9 台（3 手机 mobile + 4 电脑 + 1 路由器[HuaweiDe] + 1 未知）+ 蓝牙 8 台（手机[黄小强的Mate 30 5G/Huawei]、键盘、鼠标、耳机）；LAN mobile 192.168.3.3 被蓝牙丰富为"黄小强的Mate 30 5G/Huawei"；61 integration 测试全过
- **已知限制**: 蓝牙只列已配对设备（非主动扫描，主动需 IOBluetoothDeviceInquiry）；蓝牙 MAC≠WiFi MAC 无法按地址精确匹配，按名称/类型启发式合并；随机 MAC 手机无厂商；ARP 表只含近期活跃设备
