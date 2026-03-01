"""
多模态 Skill 合成器 (MultimodalSkillSynthesizer)

核心功能：
- 从视频录制 + 事件序列合成 Expert Guide Skill
- 使用 Kimi 多模态 LLM 分析视频内容
- 生成结构化的 Expert Skill Guide (心法式指导)

流程：
1. 获取事件序列 (TraceEvent)
2. 智能选择关键帧
3. 提取并压缩帧
4. 归一化坐标
5. 构建多模态 Prompt
6. 调用 Kimi LLM
7. 解析并保存 Skill
"""

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import yaml
from sqlalchemy import select

from app.core.learning.frame_compressor import (
    CompressedFrame,
    CoordinateNormalizer,
    FrameCompressor,
    KeyframeCandidate,
    KeyframeSelector,
    NormalizedEvent,
)
from app.core.learning.trace_parser import TraceSequence
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.llm.factory import LLMFactory
from app.infrastructure.llm.vision import VisionLLMFactory
from app.infrastructure.config.service import SystemConfigService
from app.models import TraceEvent

logger = logging.getLogger(__name__)


@dataclass
class RecordingSession:
    """录制会话数据"""
    video_path: str
    session_id: str
    task_description: str
    thread_id: Optional[str] = None


@dataclass
class VideoInfo:
    """视频元信息"""
    duration: float
    width: int
    height: int
    fps: float


class MultimodalSkillSynthesizer:
    """
    多模态 Skill 合成器

    同步处理流程，直接返回合成结果。
    """

    # 配置
    MAX_FRAMES = 15              # 最大关键帧数
    MAX_PROCESSING_TIME = 60     # 60秒超时
    DEFAULT_VIDEO_FPS = 15       # 默认帧率

    def __init__(self):
        self.compressor = FrameCompressor()
        self.keyframe_selector = KeyframeSelector()
        # 使用系统配置的 Vision LLM
        self.vision_llm = VisionLLMFactory.create_vision_llm(temperature=0.3)
        self.model_name = SystemConfigService.get_value("VISION_MODEL") or SystemConfigService.get_value("LLM_MODEL")

    async def synthesize(self, recording: RecordingSession) -> dict:
        """
        同步合成主流程

        Args:
            recording: 录制会话数据

        Returns:
            dict: 包含 skill 数据和元信息
        """
        start_time = time.time()
        logger.info(f"Starting multimodal synthesis for session {recording.session_id}")

        # Step 1: 获取视频信息
        video_info = await self._get_video_info(recording.video_path)
        logger.info(f"Video: {video_info.width}x{video_info.height}, {video_info.duration:.1f}s")

        # Step 2: 获取事件序列
        events = await self._fetch_events(recording.session_id)
        if not events:
            raise ValueError(f"No events found for session {recording.session_id}")
        logger.info(f"Fetched {len(events)} events")

        # Step 3: 智能选择关键帧
        keyframes = self.keyframe_selector.select_keyframes(
            events=events,
            video_duration=video_info.duration,
            video_resolution=(video_info.width, video_info.height)
        )
        logger.info(f"Selected {len(keyframes)} keyframes")

        if not keyframes:
            raise ValueError("No keyframes could be selected from the recording")

        # Step 4: 提取并压缩帧
        compressed_frames = await self._extract_and_compress_frames(
            video_path=recording.video_path,
            keyframes=keyframes,
            original_resolution=(video_info.width, video_info.height)
        )
        logger.info(f"Compressed {len(compressed_frames)} frames")

        # Step 5: 构建事件上下文（含归一化坐标）
        event_context = self._build_event_context(
            events=events,
            original_resolution=(video_info.width, video_info.height)
        )

        # Step 6: 关联事件到帧
        frames_with_events = self._associate_events_to_frames(
            frames=compressed_frames,
            keyframes=keyframes,
            normalizer=CoordinateNormalizer(video_info.width, video_info.height)
        )

        # Step 7: 调用多模态 LLM (使用系统配置的 Vision LLM)
        logger.info(f"Calling Vision LLM ({self.model_name})...")
        try:
            llm_response = await self._call_vision_llm(
                task_description=recording.task_description,
                frames=frames_with_events,
                event_context=event_context
            )
        except Exception as e:
            logger.error(f"Vision LLM call failed: {e}")
            raise RuntimeError(f"LLM analysis failed: {e}")

        # Step 8: 解析 LLM 输出
        skill_data = self._parse_llm_response(llm_response, recording)

        processing_time = time.time() - start_time
        logger.info(f"Synthesis completed in {processing_time:.1f}s")

        return {
            "skill": skill_data,
            "metadata": {
                "processing_time_seconds": processing_time,
                "frames_analyzed": len(compressed_frames),
                "events_processed": len(events),
                "video_duration": video_info.duration,
                "model": self.model_name or "unknown",
            }
        }

    async def _get_video_info(self, video_path: str) -> VideoInfo:
        """
        使用 ffprobe 获取视频元信息
        """
        try:
            # 获取时长
            duration_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            duration_result = subprocess.run(
                duration_cmd, capture_output=True, text=True, timeout=10
            )
            duration = float(duration_result.stdout.strip())

            # 获取分辨率
            resolution_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "json",
                video_path
            ]
            resolution_result = subprocess.run(
                resolution_cmd, capture_output=True, text=True, timeout=10
            )
            stream_info = json.loads(resolution_result.stdout)["streams"][0]

            width = int(stream_info["width"])
            height = int(stream_info["height"])

            # 解析帧率 (可能是 "15/1" 格式)
            fps_str = stream_info.get("r_frame_rate", "15/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den)
            else:
                fps = float(fps_str)

            return VideoInfo(
                duration=duration,
                width=width,
                height=height,
                fps=fps
            )

        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            # 返回默认值
            return VideoInfo(
                duration=30.0,
                width=1920,
                height=1080,
                fps=self.DEFAULT_VIDEO_FPS
            )

    async def _fetch_events(self, session_id: str) -> List[TraceEvent]:
        """
        从数据库获取事件序列
        """
        async with session_scope() as session:
            stmt = (
                select(TraceEvent)
                .where(TraceEvent.recording_session_id == session_id)
                .order_by(TraceEvent.timestamp)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def _extract_and_compress_frames(
        self,
        video_path: str,
        keyframes: List[KeyframeCandidate],
        original_resolution: Tuple[int, int]
    ) -> List[CompressedFrame]:
        """
        从视频提取关键帧并压缩
        """
        frames = []

        for i, keyframe in enumerate(keyframes):
            try:
                # 提取单帧
                frame_path = await self._extract_single_frame(
                    video_path, keyframe.timestamp
                )

                # 压缩
                compressed = self.compressor.compress(frame_path)

                # 如果太大，自适应压缩
                if len(compressed.data) > 150 * 1024:  # 150KB
                    compressed = self.compressor.compress_with_target_size(
                        frame_path, target_kb=100
                    )

                frames.append(compressed)
                logger.debug(f"Frame {i+1}/{len(keyframes)}: {compressed.width}x{compressed.height}, "
                           f"{len(compressed.data)/1024:.1f}KB")

            except Exception as e:
                logger.warning(f"Failed to extract/compress frame at {keyframe.timestamp}s: {e}")
                continue

        return frames

    async def _extract_single_frame(self, video_path: str, timestamp: float) -> str:
        """
        从视频提取单帧

        Returns:
            临时帧文件路径
        """
        import tempfile

        temp_dir = tempfile.gettempdir()
        output_path = Path(temp_dir) / f"evoloop_frame_{timestamp:.3f}.jpg"

        cmd = [
            "ffmpeg",
            "-y",                           # 覆盖
            "-ss", str(timestamp),          # 时间点
            "-i", video_path,               # 输入
            "-frames:v", "1",               # 一帧
            "-q:v", "2",                    # 高质量
            str(output_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()}")

        if not output_path.exists():
            raise RuntimeError(f"Frame extraction failed: no output file")

        return str(output_path)

    def _build_event_context(
        self,
        events: List[TraceEvent],
        original_resolution: Tuple[int, int]
    ) -> str:
        """
        构建格式化的事件上下文（含归一化坐标）
        """
        normalizer = CoordinateNormalizer(
            original_resolution[0],
            original_resolution[1]
        )

        lines = []
        lines.append(f"Total Events: {len(events)}")
        lines.append(f"Screen Resolution: {original_resolution[0]}x{original_resolution[1]}")
        lines.append("")

        for i, event in enumerate(events, 1):
            # 跳过鼠标移动（太多噪声）
            if event.action_type in ("mouse_move", "cursor_move"):
                continue

            # 归一化坐标
            norm_pos = normalizer.normalize(
                getattr(event, 'mouse_x', None),
                getattr(event, 'mouse_y', None)
            )

            # 构建描述
            ts = getattr(event, 'timestamp', 0)
            line = f"{i}. [{ts:.2f}s] {event.action_type}"

            if norm_pos:
                desc = CoordinateNormalizer.describe_position(norm_pos[0], norm_pos[1])
                line += f" at ({norm_pos[0]:.3f}, {norm_pos[1]:.3f}) [{desc}]"

            # 目标信息
            target = getattr(event, 'target_text', None)
            if target:
                line += f' on "{target}"'

            # 窗口信息
            window = getattr(event, 'window_title', None)
            app = getattr(event, 'app_name', None)
            if window and app:
                line += f" in [{app} - {window}]"
            elif app:
                line += f" in [{app}]"

            # 按键信息
            key = getattr(event, 'key_name', None)
            if key:
                line += f" key='{key}'"

            lines.append(line)

        return "\n".join(lines)

    def _associate_events_to_frames(
        self,
        frames: List[CompressedFrame],
        keyframes: List[KeyframeCandidate],
        normalizer: CoordinateNormalizer
    ) -> List[CompressedFrame]:
        """
        将事件关联到对应的关键帧
        """
        result = []

        for frame, keyframe in zip(frames, keyframes):
            # 收集关联事件的归一化信息
            related_event = keyframe.related_event
            if related_event:
                norm_pos = normalizer.normalize(
                    getattr(related_event, 'mouse_x', None),
                    getattr(related_event, 'mouse_y', None)
                )

                frame.norm_events = [{
                    'action': related_event.action_type,
                    'position': norm_pos,
                    'target_text': getattr(related_event, 'target_text', None),
                    'timestamp': getattr(related_event, 'timestamp', 0),
                }]

            result.append(frame)

        return result

    async def _call_vision_llm(
        self,
        task_description: str,
        frames: List[CompressedFrame],
        event_context: str
    ) -> str:
        """
        使用 VisionLLMFactory 调用多模态 LLM

        支持 GPT-4V, Claude 3, Kimi 等系统配置的模型
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        # 构建系统提示
        system_prompt = self._get_system_prompt()

        # 构建多模态消息内容
        content = self._build_multimodal_content(
            task_description=task_description,
            frames=frames,
            event_context=event_context
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=content)
        ]

        # 调用 LLM
        response = await self.vision_llm.ainvoke(messages)
        return response.content

    def _build_multimodal_content(
        self,
        task_description: str,
        frames: List[CompressedFrame],
        event_context: str
    ) -> List[dict]:
        """
        构建多模态消息内容（文本+图片）
        """
        import base64

        content = []

        # 1. 任务描述
        content.append({
            "type": "text",
            "text": f"## Task Description\n{task_description}\n\n"
        })

        # 2. 坐标系说明
        content.append({
            "type": "text",
            "text": (
                "## Coordinate System\n"
                "All coordinates are normalized to 0.0-1.0 range:\n"
                "- (0.0, 0.0) = top-left corner of screen\n"
                "- (1.0, 1.0) = bottom-right corner of screen\n"
                "- (0.5, 0.5) = center of screen\n\n"
            )
        })

        # 3. 事件上下文
        content.append({
            "type": "text",
            "text": f"## User Actions (Chronological)\n{event_context}\n\n"
        })

        # 4. 关键帧（多模态核心）
        content.append({
            "type": "text",
            "text": "## Screen Recording Keyframes\n"
        })

        for i, frame in enumerate(frames, 1):
            # 帧描述
            frame_desc = f"\n### Frame {i} [{frame.timestamp:.2f}s]\n"
            frame_desc += f"**Context**: {frame.description}\n"
            frame_desc += f"**Resolution**: {frame.width}x{frame.height}\n"

            # 如果有归一化事件，显示坐标
            if frame.norm_events:
                frame_desc += "**Actions in this frame**:\n"
                for evt in frame.norm_events:
                    pos = evt.get('position')
                    if pos:
                        desc = self._describe_position(pos[0], pos[1])
                        frame_desc += f"  - {evt['action']} at ({pos[0]:.3f}, {pos[1]:.3f}) [{desc}]\n"
                    if evt.get('target_text'):
                        frame_desc += f"    Target: \"{evt['target_text']}\"\n"

            content.append({"type": "text", "text": frame_desc})

            # Base64 图片
            base64_image = base64.b64encode(frame.data).decode('utf-8')
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })

        # 5. 输出要求
        content.append({
            "type": "text",
            "text": self._get_output_requirement_prompt()
        })

        return content

    def _get_system_prompt(self) -> str:
        """
        获取系统提示
        """
        return """You are EvoLoop's Skill Architect, an expert at analyzing screen recordings and creating reusable automation skills.

Your task is to:
1. Observe the sequence of screenshots to understand the UI flow
2. Combine visual information with the action log to understand user intent
3. Generate a high-quality Expert Skill Guide (not rigid steps, but strategic guidance)

Key principles:
- FOCUS ON PATTERNS: Identify repeatable strategies, not just specific coordinates
- VISUAL REASONING: Use UI layout, colors, icons, and text positions
- SPATIAL AWARENESS: Describe positions relatively ("top-left", "near the header")
- TIMING INSIGHTS: Note loading delays, animations, and transition states
- ERROR RECOVERY: Anticipate what could go wrong and how to recover

Anti-patterns to avoid:
- ❌ "Click at (0.234, 0.567)" → Too rigid, will break on different resolutions
- ❌ "Click the button" → Too vague, which button?
- ✅ "Click the blue 'Search' button in the top-right corner of the window"

The output must be a valid YAML frontmatter + Markdown body in the exact format specified.
"""

    def _get_output_requirement_prompt(self) -> str:
        """
        获取输出格式要求
        """
        return """

## Required Output Format

Generate a skill in YAML + Markdown format:

```yaml
name: [short_descriptive_name]
namespace: [logical_category like "cross_app", "os/macos/wechat", "web/browser"]
description: |
  [Clear description of what this skill does]
trigger_patterns:
  - "[natural language pattern with {{parameter}}]"
  - "[alternative phrasing]"
parameters:
  - name: [param_name]
    type: string
    required: true/false
    description: "[what this parameter represents]"
```

# 🧠 Expert Skill Guide

## 1. Mental Model
[The high-level strategy and business logic. Why are we doing this? What's the core insight?]

Example: "This skill bridges information between apps using clipboard as a universal transfer medium and OCR for element location. The key insight is that custom UI apps like WeChat don't expose native accessibility APIs, so we must use visual reasoning."

## 2. Visual Anchors & Context
[Key visual indicators that confirm we're in the right state:]
- **Window Title**: Look for "..."
- **UI Elements**: Search for "..." label/icon
- **Color/Layout**: The ... should be visible in the ...

## 3. Execution Workflow

### Phase 1: [Name]
1. **Activate**: Focus the target application
2. **Visual Scan**: Look for [specific element] in [location]
3. **Action**: [What to do with details]
4. **Verify**: Confirm [expected state change]

### Phase 2: [Name]
...

## 4. Common Pitfalls & Gotchas
- **Timing**: [e.g., "Wait 1s for the dropdown to animate"]
- **False Positives**: [e.g., "Don't confuse 'Search' with 'Search Settings'"]
- **Hidden States**: [e.g., "If element not found, check if sidebar is collapsed"]

## 5. Error Recovery Strategies
- If [failure condition] → [recovery action]
- If [alternative failure] → [alternative recovery]

---
IMPORTANT:
1. STAY GROUNDED: Only describe elements visible in the screenshots
2. BE SPECIFIC: Name exact UI labels, colors, positions
3. THINK STRATEGIC: Focus on "how to think about this task" not just "what buttons to click"
4. ANTICIPATE: Include timing notes and recovery strategies based on observed behavior
"""

    def _describe_position(self, norm_x: float, norm_y: float) -> str:
        """将归一化坐标转换为人类可读描述"""
        if norm_x < 0.2:
            h = "left"
        elif norm_x < 0.4:
            h = "left-center"
        elif norm_x < 0.6:
            h = "center"
        elif norm_x < 0.8:
            h = "right-center"
        else:
            h = "right"

        if norm_y < 0.2:
            v = "top"
        elif norm_y < 0.4:
            v = "upper"
        elif norm_y < 0.6:
            v = "middle"
        elif norm_y < 0.8:
            v = "lower"
        else:
            v = "bottom"

        return f"{v}-{h}"

    def _parse_llm_response(self, response: str, recording: RecordingSession) -> dict:
        """
        解析 LLM 输出，提取 YAML 和 Markdown
        """
        # 提取 YAML 部分
        yaml_content = self._extract_yaml(response)

        # 提取 Markdown 部分（instructions）
        instructions = self._extract_instructions(response)

        # 解析 YAML
        try:
            metadata = yaml.safe_load(yaml_content) if yaml_content else {}
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML: {e}")
            metadata = {}

        return {
            "name": metadata.get("name", "unnamed_skill"),
            "namespace": metadata.get("namespace", "misc"),
            "description": metadata.get("description", ""),
            "trigger_patterns": metadata.get("trigger_patterns", []),
            "parameters": metadata.get("parameters", []),
            "instructions": instructions or response,  # 如果解析失败，保留全文
            "source_session_id": recording.session_id,
            "source_thread_id": recording.thread_id,
            "skill_source": "multimodal_record",
            "status": "draft",
        }

    def _extract_yaml(self, text: str) -> Optional[str]:
        """
        从文本提取 YAML 部分（```yaml 和 ``` 之间）
        """
        if "```yaml" in text:
            parts = text.split("```yaml", 1)
            if len(parts) > 1:
                yaml_part = parts[1].split("```", 1)[0]
                return yaml_part.strip()

        # 尝试找第一个代码块
        if "```" in text:
            parts = text.split("```", 2)
            if len(parts) >= 3:
                return parts[1].strip()

        # 没有代码块标记，尝试找 YAML frontmatter
        lines = text.split("\n")
        yaml_lines = []
        in_yaml = False

        for line in lines:
            if line.strip() == "---" and not in_yaml:
                in_yaml = True
                # Don't include the opening --- in output
            elif line.strip() == "---" and in_yaml:
                # End of frontmatter, stop here (don't include closing ---)
                break
            elif in_yaml:
                yaml_lines.append(line)

        if yaml_lines:
            return "\n".join(yaml_lines)

        return None

    def _extract_instructions(self, text: str) -> Optional[str]:
        """
        提取 instructions 部分（通常是 # Expert Skill Guide 之后）
        """
        # 找 Expert Skill Guide 标题
        markers = [
            "# 🧠 Expert Skill Guide",
            "# Expert Skill Guide",
            "## 1. Mental Model",
            "## 🧠 Mental Model",
        ]

        for marker in markers:
            if marker in text:
                idx = text.find(marker)
                return text[idx:].strip()

        # 如果找不到，返回 YAML 之后的内容
        yaml_end = text.find("---", text.find("---") + 3) if "---" in text else -1
        if yaml_end > 0:
            return text[yaml_end + 3:].strip()

        return text
