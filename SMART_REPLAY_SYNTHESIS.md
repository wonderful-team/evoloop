# Smart Replay Synthesis - 实现总结

## 概述

Smart Replay Synthesis 是一个智能技能合成系统，允许用户通过录制视频标注 + 任务目标描述，让 AI 自动生成可执行的自动化技能。

## 核心功能

### 三阶段流程

1. **录制阶段 (Recording)**
   - 用户正常操作目标网站/App
   - 系统自动记录 DOM 事件、全局事件、屏幕视频

2. **回放标注阶段 (Annotation)**
   - 用户观看录制的视频回放
   - 在视频上框选感兴趣的数据区域
   - 可添加简短备注描述该区域

3. **智能合成阶段 (Synthesis)**
   - 用户描述任务目标
   - LLM 分析视频关键帧、标注区域、事件序列
   - 自动生成技能（标题、描述、心法、宏脚本）

## 技术架构

### 后端组件

```
backend/
├── app/models/learning.py
│   ├── RecordingAnnotation    # 标注数据模型
│   └── SynthesisJob           # 合成任务模型
│
├── app/core/learning/smart_synthesizer.py
│   ├── SmartSynthesizer       # 核心合成引擎
│   │   ├── _extract_keyframes()           # 关键帧提取
│   │   ├── _analyze_frames_with_annotations()  # Vision LLM 分析
│   │   ├── _understand_task_phases()      # 任务阶段理解
│   │   ├── _generate_optimized_macro()    # 宏脚本生成
│   │   └── _generate_skill_metadata()     # 技能元信息生成
│
└── app/api/routes/learning.py
    ├── POST /recordings/annotations              # 创建标注
    ├── GET /recordings/{id}/annotations          # 获取标注列表
    ├── DELETE /recordings/annotations/{id}       # 删除标注
    ├── POST /recordings/{id}/smart-synthesis     # 启动合成
    └── GET /synthesis-jobs/{id}                  # 查询合成状态
```

### 前端组件

```
frontend/
└── src/components/Learning/SmartReplay/
    ├── SmartReplayEditor.tsx      # 主编辑器组件
    ├── AnnotationList.tsx         # 标注列表管理
    ├── Timeline.tsx               # 视频时间轴
    ├── SynthesisProgress.tsx      # 合成进度显示
    └── SkillReviewPanel.tsx       # 结果审查面板
```

## API 端点

### 标注管理

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/recordings/annotations` | 创建标注 |
| GET | `/recordings/{session_id}/annotations` | 获取标注列表 |
| DELETE | `/recordings/annotations/{annotation_id}` | 删除标注 |

### 智能合成

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/recordings/{session_id}/smart-synthesis` | 启动合成任务 |
| GET | `/synthesis-jobs/{job_id}` | 获取任务状态 |

### 请求/响应示例

**创建标注**
```json
POST /recordings/annotations
{
  "session_id": "session-123",
  "thread_id": "thread-456",
  "annotation_type": "extract_region",
  "video_timestamp_ms": 12500,
  "region_x": 1200,
  "region_y": 500,
  "region_width": 200,
  "region_height": 50,
  "user_note": "这是价格区域"
}
```

**启动合成**
```json
POST /recordings/session-123/smart-synthesis
{
  "session_id": "session-123",
  "thread_id": "thread-456",
  "task_goal": "我想采集这个网站上所有商品的价格和库存信息，保存到Excel",
  "annotation_ids": [1, 2, 3]
}

Response:
{
  "job_id": 123,
  "status": "pending",
  "message": "Synthesis job started with 3 annotations"
}
```

**查询合成状态**
```json
GET /synthesis-jobs/123

Response:
{
  "id": 123,
  "status": "completed",
  "progress_percent": 100,
  "current_phase": "generating_metadata",
  "task_goal": "...",
  "result": {
    "skill": {
      "name": "batch_extract_product_data",
      "description": "自动采集网站商品价格和库存信息",
      "namespace": "web/ecommerce/data-extraction",
      "trigger_patterns": ["采集商品数据", "提取价格信息"],
      "instructions": "## 1. Mental Model...",
      "execution_mode": "deterministic",
      "macro_script": [...]
    }
  }
}
```

## 数据库迁移

运行迁移命令：

```bash
cd backend
alembic upgrade head
```

新创建的表：
- `recording_annotations` - 存储用户标注
- `synthesis_jobs` - 存储合成任务状态和结果

## 使用流程

1. **开始录制**
   - 用户在 EvoLoop 中点击录制按钮
   - 系统开始录制屏幕视频和操作事件

2. **停止录制**
   - 用户停止录制
   - 自动打开 SmartReplayEditor

3. **标注阶段**
   - 观看录制的视频
   - 点击 "Draw Region" 按钮
   - 在视频上拖拽框选数据区域
   - 可以添加简短备注（如"价格"、"标题"）
   - 重复标记所有感兴趣的区域

4. **描述目标**
   - 点击 "Next: Describe Goal"
   - 输入任务目标描述：
     "我想采集闲鱼上iPhone商品的价格和卖家信息，整理成表格保存"

5. **AI 分析**
   - 点击 "Start AI Analysis"
   - 系统执行：
     1. 提取视频关键帧
     2. Vision LLM 分析每一帧
     3. 理解任务阶段和流程
     4. 生成优化的宏脚本
     5. 生成技能元信息（标题、描述、心法）

6. **审查结果**
   - 查看生成的技能概览
   - 查看详细的操作说明（心法）
   - 查看宏脚本步骤
   - 确认保存或返回编辑

## 宏脚本动作映射

| 动作类型 | 来源 | 执行工具 |
|---------|------|---------|
| `navigate` | dom | browser_control |
| `click` | dom | browser_control |
| `input` | dom | browser_control |
| `scroll` | dom | browser_control |
| `wait` | dom | asyncio.sleep |
| `extract` | dom | browser_control (get_text) |
| `tap` | mobile | mobile_control |
| `swipe` | mobile | mobile_control |
| `dump_ui` | mobile | mobile_control |
| `applescript` | desktop | desktop_control |

## 下一步优化

1. **Vision LLM 集成**
   - 集成 GPT-4V / Claude 3 进行真正的视觉分析
   - 当前使用文本描述作为 fallback

2. **实时预览**
   - 宏脚本步骤的高亮预览
   - 提取数据的可视化验证

3. **编辑增强**
   - 宏脚本步骤的拖拽重排
   - 步骤级别的编辑和删除

4. **批量测试**
   - 生成技能的自动验证
   - 测试用例生成

## 文件变更列表

### 后端
- `app/models/learning.py` - 添加 RecordingAnnotation, SynthesisJob 模型
- `app/core/learning/smart_synthesizer.py` - 新增智能合成引擎
- `app/api/routes/learning.py` - 添加新 API 端点
- `app/alembic/versions/a8f9c2d4e5b6_add_smart_replay_synthesis_tables.py` - 数据库迁移

### 前端
- `src/components/Learning/SmartReplay/SmartReplayEditor.tsx` - 主编辑器
- `src/components/Learning/SmartReplay/AnnotationList.tsx` - 标注列表
- `src/components/Learning/SmartReplay/Timeline.tsx` - 时间轴
- `src/components/Learning/SmartReplay/SynthesisProgress.tsx` - 进度显示
- `src/components/Learning/SmartReplay/SkillReviewPanel.tsx` - 结果审查
- `src/components/Learning/SmartReplay/index.ts` - 导出
- `src/hooks/useSmartSynthesis.ts` - 合成逻辑 Hook
- `src/hooks/index.ts` - 导出更新
- `src/routes/_layout/learning.tsx` - 集成 SmartReplayEditor
