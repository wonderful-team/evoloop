# 多模态 Skill 合成测试套件

本测试套件针对多模态 Skill 合成功能，包括帧压缩、坐标归一化、关键帧选择和 LLM 合成。

## 测试文件结构

```
tests/
├── unit/core/
│   ├── test_frame_compressor.py      # 帧压缩和坐标归一化单元测试
│   └── test_multimodal_synthesizer.py # 合成器核心逻辑测试
├── integration/
│   └── test_multimodal_synthesis.py   # API 集成测试
├── mocks/
│   └── vision_llm.py                  # Vision LLM Mock
├── data/
│   └── sample_multimodal_recording.py # 测试数据生成器
└── conftest.py                        # 共享 fixtures（已更新）
```

## 运行测试

### 运行所有单元测试
```bash
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
pytest tests/unit/core/test_frame_compressor.py -v
pytest tests/unit/core/test_multimodal_synthesizer.py -v
```

### 运行集成测试（需要数据库）
```bash
pytest tests/integration/test_multimodal_synthesis.py -v
```

### 运行特定标记的测试
```bash
# 只运行单元测试
pytest -m unit

# 只运行需要 LLM 的测试
pytest -m llm

# 跳过需要数据库的测试
pytest -m "not db"
```

## 测试数据生成

生成合成测试数据：
```bash
python tests/data/sample_multimodal_recording.py
```

这将创建：
- `/tmp/evoloop_test_data/wechat/` - WeChat 消息场景
- `/tmp/evoloop_test_data/browser/` - 浏览器搜索场景

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `VISION_MODEL` | 多模态模型名称 | `gpt-4o` |
| `LLM_PROVIDER` | LLM 提供商 | `openai` |
| `LLM_BASE_URL` | API 地址 | `https://api.openai.com/v1` |
| `LLM_API_KEY` | API 密钥 | `sk-...` |
| `TEST_VIDEO_PATH` | 集成测试用的视频文件 | `/path/to/test.mp4` |

## 关键 Fixtures

### Mock Fixtures
- `mock_vision_llm` - 模拟 Vision LLM
- `mock_compressed_frames` - 模拟压缩帧
- `sample_recording_session` - 示例录制会话
- `sample_trace_events` - 示例事件序列

### 组件 Fixtures
- `frame_compressor` - FrameCompressor 实例
- `keyframe_selector` - KeyframeSelector 实例
- `coordinate_normalizer` - CoordinateNormalizer 实例

## 测试覆盖

### 单元测试覆盖
- ✅ 坐标归一化（原始像素 -> 0-1）
- ✅ 坐标反归一化（0-1 -> 压缩图像）
- ✅ 位置描述生成（左上、中心等）
- ✅ 帧压缩（不同策略）
- ✅ 图像格式转换
- ✅ 关键帧选择
- ✅ 时间去重
- ✅ 优先级排序
- ✅ LLM 响应解析
- ✅ YAML 提取

### 集成测试覆盖
- ✅ API 端点 `/skills/synthesize-from-recording`
- ✅ API 端点预览功能
- ✅ 视频不存在错误处理
- ✅ 合成失败处理

## 注意事项

1. **LLM 成本**：标记为 `@pytest.mark.llm` 的测试可能产生 API 费用，请谨慎运行
2. **数据库依赖**：集成测试需要 PostgreSQL 数据库连接
3. **FFmpeg**：帧提取测试需要系统中安装 FFmpeg
