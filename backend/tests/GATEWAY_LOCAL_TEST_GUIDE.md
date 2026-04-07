# Gateway 本地测试指南

## 快速开始

### 1. 启动本地 Gateway

```bash
# 终端 1: 启动本地 Gateway
cd member-center/gateway
chmod +x start_local.sh
./start_local.sh
```

或者手动启动：

```bash
cd member-center/gateway
go run . -config config.local.json
```

你将看到类似输出：
```
🚀 Starting EvoLoop Gateway (Local Mode)...
📋 Config: config.local.json
...
2024/xx/xx xx:xx:xx [LLMProxy] Config manager started
2024/xx/xx xx:xx:xx Gateway started on :9001
```

### 2. 运行测试（使用本地 Gateway）

```bash
# 终端 2: 运行测试
cd evoloop/backend
python tests/test_kimi_context_optimization.py --local --quick
```

## 日志分析

### 日志格式

本地 Gateway 会输出带 `[TIMING]` 前缀的性能日志：

```
[TIMING] ChatCompletion START: request_id=xxx, model=kimi-k2-thinking-turbo, body_size=133120 bytes
[TIMING] SelectProvider: elapsed_ms=2, provider: kimi, type: openai
[TIMING] forwardOpenAI UPSTREAM: url=https://api.kimi.com/..., body_size=133120 bytes
[TIMING] JSON_Marshal: elapsed_ms=15, body_size: 133120
[TIMING] Upstream_Request: elapsed_ms=45000, provider: kimi
[TIMING] forwardOpenAI UPSTREAM_RESPONSE: status=200
[TIMING] JSON_Decode: elapsed_ms=5
[TIMING] forwardOpenAI TOTAL: elapsed_ms=45020, tokens=30000+500=30500
```

### 关键指标

| 阶段 | 正常耗时 | 说明 |
|------|---------|------|
| SelectProvider | 1-5ms | 选择供应商配置 |
| JSON_Marshal | 10-50ms | 序列化请求体 |
| Upstream_Request | 30-60s (130KB) | **发送到 Kimi API 并等待响应** |
| JSON_Decode | 5-20ms | 解析响应 |
| **TOTAL** | **30-60s** | 总耗时 |

### 性能瓶颈识别

**如果 `Upstream_Request` 耗时异常（> 2分钟）：**
- 说明问题在 Gateway → Kimi API 的网络传输
- 可能是 HTTP/1.1 连接问题

**如果其他阶段耗时异常：**
- JSON_Marshal > 100ms：序列化效率低
- SelectProvider > 50ms：配置查询有锁竞争

## 对比测试

### 三种模式对比

```bash
# 1. 远程 Gateway（生产环境）
python tests/test_kimi_context_optimization.py --quick

# 2. 本地 Gateway（调试模式，带详细日志）
python tests/test_kimi_context_optimization.py --local --quick

# 3. 直连 Kimi API（绕过 Gateway）
python tests/test_kimi_context_optimization.py --direct --quick
```

### 预期结果

| 模式 | 130KB Prompt | 说明 |
|------|-------------|------|
| 远程 Gateway | 6+ min | 当前生产环境，有问题 |
| 本地 Gateway | 30-60s | 本地测试，用于定位问题 |
| 直连 Kimi | 30-60s | 官方 API 正常速度 |

## 故障排查

### 问题 1: 本地 Gateway 启动失败

```bash
# 检查端口占用
lsof -i :9001

# 检查 Redis（可选，非必需）
redis-cli ping
```

### 问题 2: 测试脚本连接失败

```bash
# 检查本地 Gateway 是否运行
curl http://localhost:9001/health

# 预期输出
{"status":"ok","users":0,"quota":{"cached_users":0}}
```

### 问题 3: 认证失败

本地 Gateway 使用与远程相同的 JWT Secret，token 可以通用。
如果认证失败，检查：
1. 是否正确登录获取 token
2. config.local.json 中的 jwt.secret 是否与远程一致

## 进阶：修改 Gateway 代码测试

### 1. 修改后重新编译

```bash
cd member-center/gateway
go build -o gateway_test .
./gateway_test -config config.local.json
```

### 2. 热重载（开发模式）

```bash
# 安装 air（Go 热重载工具）
go install github.com/cosmtrek/air@latest

# 启动热重载
cd member-center/gateway
air -c .air.toml
```

## 常用调试命令

```bash
# 查看 Gateway 实时日志
tail -f /tmp/gateway.log

# 测试 Gateway 连通性
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:9001/v1/models

# 测试 Chat Completion（小请求）
curl -X POST http://localhost:9001/v1/chat/completions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"kimi-k2-thinking-turbo","messages":[{"role":"user","content":"hello"}]}'
```

## 下一步优化

根据本地测试日志，可以确定具体优化方向：

1. **如果 Upstream_Request 慢**：优化 HTTP Client 配置（启用 HTTP/2）
2. **如果 JSON_Marshal 慢**：优化序列化方式（使用流式编码）
3. **如果 SelectProvider 慢**：优化配置缓存（无锁读取）

详细的优化建议请参考 `GATEWAY_PERFORMANCE_ANALYSIS.md`
