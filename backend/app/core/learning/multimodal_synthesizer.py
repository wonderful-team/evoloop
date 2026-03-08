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
import base64
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
from app.core.learning.prompts.builder import LearningPromptBuilder
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.llm.vision import VisionLLMFactory
from app.infrastructure.config.service import SystemConfigService
from app.models import TraceEvent, LearnedSkill

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
        self.prompt_builder = LearningPromptBuilder()
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

        # Step 5: 构建事件上下文（用于 Prompt 文本部分）
        event_context = self._build_event_context(
            events=events,
            original_resolution=(video_info.width, video_info.height)
        )

        # Step 6: 关联事件到帧（用于多模态图片标注）
        frames_with_events = self._associate_events_to_frames(
            frames=compressed_frames,
            keyframes=keyframes,
            normalizer=CoordinateNormalizer(video_info.width, video_info.height)
        )

        # Step 7: 调用多模态 LLM
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

        # Step 9: 辅助生成确定性宏脚本 (Fallback/Verification Basis)
        compiled_macro = await self._compile_macro_from_events(events)
        
        # Step 10: 验证 Dry-run (优先验证实际要返回的宏)
        target_macro = skill_data.get("macro_script") or compiled_macro
        
        # 如果 LLM 返回的是字符串 JSON，尝试解析它
        if isinstance(target_macro, str) and (target_macro.strip().startswith("[") or target_macro.strip().startswith("{")):
            try:
                target_macro = json.loads(target_macro)
            except Exception as e:
                logger.warning(f"Failed to parse LLM macro string as JSON: {e}")

        # [Phase 15] 宏规范化 (处理 LLM 的不规范输出)
        if isinstance(target_macro, list):
            target_macro = self._cleanup_macro(target_macro)
            skill_data["macro_script"] = target_macro

        verification = await self.verify_macro(target_macro)
        skill_data["verification_report"] = verification

        # 如果没有有效的 LLM 宏，使用编译出来的作为兜底
        if not skill_data.get("macro_script") or not isinstance(skill_data.get("macro_script"), list):
            skill_data["macro_script"] = compiled_macro
            skill_data["execution_mode"] = "deterministic"
        else:
            skill_data["execution_mode"] = "deterministic"

        processing_time = time.time() - start_time
        logger.info(f"Synthesis completed in {processing_time:.1f}s. Verification: {verification['status']}")

        return {
            "skill": skill_data,
            "verification": verification,
            "metadata": {
                "processing_time_seconds": processing_time,
                "frames_analyzed": len(compressed_frames),
                "events_processed": len(events),
                "video_duration": video_info.duration,
                "model": self.model_name or "unknown",
            }
        }

    def _cleanup_macro(self, steps: List[dict]) -> List[dict]:
        """规范化 LLM 生成的宏步骤 (修复常见格式错误)"""
        clean_steps = []
        for i, step in enumerate(steps, 1):
            if not isinstance(step, dict): continue
            
            # 1. 确保有 step_number
            if "step_number" not in step:
                step["step_number"] = i
                
            # 2. 映射非标准 type
            s_type = step.get("type")
            if s_type == "wait":
                # type: wait -> type: action, event_type: wait
                step["type"] = "action"
                step["event_type"] = "wait"
                # 处理 condition/timeout -> payload
                payload = step.get("payload", {})
                if "timeout" in step and "seconds" not in payload:
                    payload["seconds"] = float(step["timeout"]) / 1000.0
                step["payload"] = payload
            elif s_type in ("while", "batch_loop", "loop"):
                # 统一为 loop
                step["type"] = "loop"

            # 3. 规范化嵌套字段名
            # then -> then_steps
            if "then" in step and "then_steps" not in step:
                step["then_steps"] = step.pop("then")
                
            # else -> else_steps
            if "else" in step and "else_steps" not in step:
                step["else_steps"] = step.pop("else")
                
            # do/do_steps -> steps
            legacy_substeps = step.pop("do", None) or step.pop("do_steps", None)
            if legacy_substeps and "steps" not in step:
                step["steps"] = legacy_substeps
            
            # 4. 递归处理嵌套步骤
            for branch in ["then_steps", "else_steps", "steps"]:
                if branch in step and isinstance(step[branch], list):
                    step[branch] = self._cleanup_macro(step[branch])
                    
            clean_steps.append(step)
        return clean_steps

    async def _compile_macro_from_events(self, events: List[TraceEvent]) -> List[dict]:
        """从 TraceEvent 序列编译确定性宏脚本 (复用 WorkflowSynthesizer)"""
        from app.core.learning.skill_synthesizer import WorkflowSynthesizer
        from app.core.learning.trace_parser import TraceParser
        
        if not events:
            return []
            
        thread_id = events[0].thread_id or "unknown"
        session_id = events[0].recording_session_id
        
        parser = TraceParser(thread_id=thread_id, session_id=session_id)
        # 转换为 TraceSequence
        sequence = parser._convert_to_sequence(events)
        
        synth = WorkflowSynthesizer(thread_id=thread_id)
        return synth._compile_macro_script(sequence)

    async def verify_macro(self, macro_script: list[dict], project_id: int = 1) -> dict:
        """Dry-run 验证宏脚本的有效性"""
        from app.core.execution.macro.service import MacroService
        from app.core.execution.macro.schema import MacroScript, MacroMetadata
        
        logger.info(f"🔍 Starting verification dry-run for synthesized macro...")
        
        script = MacroScript(
            metadata=MacroMetadata(thread_id="verifier", author="multimodal_verifier"),
            steps=macro_script
        )
        
        try:
            # MacroService.run(thread_id, script_input, params=None)
            result = await MacroService.run(
                thread_id="multimodal_dryrun",
                script_input=macro_script
            )
            success = result.get("success", False)
            extracted_data = result.get("extracted_data", {})
            
            # 检查提取点数据
            expected_keys = [s["key"] for s in macro_script if s.get("type") == "extract"]
            missing_keys = [k for k in expected_keys if k not in extracted_data]
            
            status = "success" if success and not missing_keys else "failed"
            
            return {
                "status": status,
                "success": success,
                "missing_keys": missing_keys,
                "extracted_count": len(extracted_data),
                "error": result.get("error")
            }
        except Exception as e:
            logger.error(f"Verification crashed: {e}")
            return {"status": "error", "success": False, "error": str(e)}

    async def _get_video_info(self, video_path: str) -> VideoInfo:
        """使用 ffprobe JSON 获取视频元信息（更鲁棒）"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,duration",
                "-show_entries", "format=duration",
                "-of", "json",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            data = json.loads(result.stdout)
            
            stream = data["streams"][0]
            format_data = data.get("format", {})
            
            # 优先从 format 获取 duration
            duration = float(format_data.get("duration") or stream.get("duration", 0.0))
            width = int(stream["width"])
            height = int(stream["height"])
            
            # 解析帧率
            fps_str = stream.get("r_frame_rate", "15/1")
            fps = float(fps_str.split("/")[0]) / float(fps_str.split("/")[1]) if "/" in fps_str else float(fps_str)

            return VideoInfo(duration=duration, width=width, height=height, fps=fps)
        except Exception as e:
            logger.error(f"Failed to get video info for {video_path}: {e}")
            return VideoInfo(duration=30.0, width=1920, height=1080, fps=self.DEFAULT_VIDEO_FPS)

    async def _fetch_events(self, session_id: str) -> List[TraceEvent]:
        """从数据库获取事件并进行时间轴归一化"""
        async with session_scope() as session:
            stmt = select(TraceEvent).where(TraceEvent.recording_session_id == session_id).order_by(TraceEvent.timestamp)
            result = await session.execute(stmt)
            events = list(result.scalars().all())
            
            if not events:
                return []
                
            # 绝对毫秒 -> 相对秒 (以视频开始为 0)
            base_ms = events[0].timestamp
            for event in events:
                event.timestamp = (event.timestamp - base_ms) / 1000.0 if event.timestamp else 0.0
                    
            return events

    async def _extract_and_compress_frames(
        self,
        video_path: str,
        keyframes: List[KeyframeCandidate],
        original_resolution: Tuple[int, int]
    ) -> List[CompressedFrame]:
        """批量提取并压缩帧"""
        frames = []
        for keyframe in keyframes:
            try:
                # 提取单帧
                frame_path = await self._extract_single_frame(video_path, keyframe.timestamp)
                # 执行压缩
                compressed = self.compressor.compress(frame_path)
                # 自适应控制大小 (150KB 以内)
                if len(compressed.data) > 150 * 1024:
                    compressed = self.compressor.compress_with_target_size(frame_path, target_kb=100)
                
                # 注入元数据供 Prompt 使用
                compressed.timestamp = keyframe.timestamp
                compressed.description = keyframe.description
                
                frames.append(compressed)
            except Exception as e:
                logger.warning(f"Failed to process frame at {keyframe.timestamp}s: {e}")
                continue
        return frames

    async def _extract_single_frame(self, video_path: str, timestamp: float) -> str:
        """FFmpeg 提取单帧 (兼容 Mac 格式)"""
        import tempfile
        output_path = Path(tempfile.gettempdir()) / f"evoloop_frame_{timestamp:.3f}.jpg"

        cmd = [
            "ffmpeg", "-y", 
            "-ss", str(timestamp), 
            "-i", video_path, 
            "-frames:v", "1", 
            "-q:v", "2", 
            "-pix_fmt", "yuvj420p", # Mac JPEG 兼容性
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg extraction failed: {result.stderr.decode()}")
        return str(output_path)

    def _build_event_context(self, events: List[TraceEvent], original_resolution: Tuple[int, int]) -> str:
        """构建详细的事件内容上下文 (用于 Prompt)"""
        normalizer = CoordinateNormalizer(original_resolution[0], original_resolution[1])
        lines = [
            f"Total Events: {len(events)}",
            f"Screen Resolution: {original_resolution[0]}x{original_resolution[1]}",
            ""
        ]

        for i, event in enumerate(events, 1):
            if event.action_type in ("mouse_move", "cursor_move"):
                continue

            ts = getattr(event, 'timestamp', 0.0)
            line = f"{i}. [{ts:.2f}s] {event.action_type}"
            
            # 坐标描述
            norm_pos = normalizer.normalize(getattr(event, 'mouse_x', None), getattr(event, 'mouse_y', None))
            if norm_pos:
                desc = self._describe_position(norm_pos[0], norm_pos[1])
                line += f" at ({norm_pos[0]:.3f}, {norm_pos[1]:.3f}) [{desc}]"

            # 语义上下文
            target = getattr(event, 'target_text', None)
            if target: line += f' on "{target}"'
            
            window = getattr(event, 'window_title', None)
            app = getattr(event, 'app_name', None)
            if window and app: line += f" in [{app} - {window}]"
            elif app: line += f" in [{app}]"
            
            key = getattr(event, 'key_name', None)
            if key: line += f" key='{key}'"

            lines.append(line)

        return "\n".join(lines)

    def _associate_events_to_frames(
        self,
        frames: List[CompressedFrame],
        keyframes: List[KeyframeCandidate],
        normalizer: CoordinateNormalizer
    ) -> List[CompressedFrame]:
        """将事件语义关联到关键帧对象中"""
        for frame, keyframe in zip(frames, keyframes):
            if keyframe.related_event:
                pos = normalizer.normalize(
                    getattr(keyframe.related_event, 'mouse_x', None),
                    getattr(keyframe.related_event, 'mouse_y', None)
                )
                frame.norm_events = [{
                    'action': keyframe.related_event.action_type,
                    'position': pos,
                    'target_text': getattr(keyframe.related_event, 'target_text', None),
                    'timestamp': getattr(keyframe.related_event, 'timestamp', 0),
                }]
        return frames

    async def _call_vision_llm(self, task_description: str, frames: List[CompressedFrame], event_context: str) -> str:
        """构建多模态消息并调用 LLM"""
        from langchain_core.messages import HumanMessage, SystemMessage

        # 加载新的系统模板
        system_prompt = self.prompt_builder.build_multimodal_synthesis_prompt({})

        # 构建人机交互内容 (文本说明 + 交叉排布的图片)
        content = []
        
        # 1. 任务背景与全局事件序列
        content.append({
            "type": "text", 
            "text": (
                f"## Task Description\n{task_description}\n\n"
                f"## Coordinate System\n"
                "All coordinates are normalized to 0.0-1.0 range (0.0=top/left, 1.0=bottom/right).\n\n"
                f"## User Actions (Complete Timeline)\n{event_context}\n\n"
            )
        })

        # 2. 关键帧详情 (附带图片)
        content.append({"type": "text", "text": "## Screen Recording Keyframes\n"})
        
        for i, frame in enumerate(frames, 1):
            # 帧文本描述
            frame_desc = f"\n### Frame {i} [{frame.timestamp:.2f}s]\n"
            frame_desc += f"**Visual Context**: {frame.description}\n"
            
            if frame.norm_events:
                frame_desc += "**User actions during this frame**:\n"
                for evt in frame.norm_events:
                    pos = evt.get('position')
                    if pos:
                        desc = self._describe_position(pos[0], pos[1])
                        frame_desc += f"  - {evt['action']} at ({pos[0]:.3f}, {pos[1]:.3f}) [{desc}]\n"
                    if evt.get('target_text'):
                        frame_desc += f"    Target: \"{evt['target_text']}\"\n"
            
            content.append({"type": "text", "text": frame_desc})
            
            # 插入 Base64 图片
            base64_img = base64.b64encode(frame.data).decode('utf-8')
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
            })

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=content)
        ]
        
        response = await self.vision_llm.ainvoke(messages)
        return response.content

    def _describe_position(self, norm_x: float, norm_y: float) -> str:
        """将归一化坐标转换为精细的语义描述 (5x5 风格)"""
        # 水平段
        if norm_x < 0.2: h = "left"
        elif norm_x < 0.4: h = "left-center"
        elif norm_x < 0.6: h = "center"
        elif norm_x < 0.8: h = "right-center"
        else: h = "right"

        # 垂直段
        if norm_y < 0.2: v = "top"
        elif norm_y < 0.4: v = "upper"
        elif norm_y < 0.6: v = "middle"
        elif norm_y < 0.8: v = "lower"
        else: v = "bottom"

        return f"{v}-{h}"

    def _parse_llm_response(self, response: str, recording: RecordingSession) -> dict:
        """解析 LLM 返回的混合格式"""
        yaml_content = self._extract_yaml(response)
        instructions = self._extract_instructions(response)

        try:
            metadata = yaml.safe_load(yaml_content) if yaml_content else {}
        except Exception as e:
            logger.error(f"Failed to parse LLM YAML metadata: {e}")
            metadata = {}

        return {
            "name": metadata.get("name", "unnamed_skill"),
            "namespace": metadata.get("namespace", "misc"),
            "description": metadata.get("description", ""),
            "trigger_patterns": metadata.get("trigger_patterns", []),
            "parameters": metadata.get("parameters", []),
            "instructions": instructions or response,
            "source_session_id": recording.session_id,
            "source_thread_id": recording.thread_id,
            "skill_source": "multimodal_record",
            "status": "pending_review",
            "macro_script": metadata.get("macro_script"),
            "execution_mode": "deterministic" if metadata.get("macro_script") else "agentic"
        }

    def _extract_yaml(self, text: str) -> Optional[str]:
        """提取 YAML 代码块"""
        if "```yaml" in text:
            return text.split("```yaml", 1)[1].split("```", 1)[0].strip()
        if "```" in text:
            # 尝试提取第一个代码块
            return text.split("```", 2)[1].strip()
        return None

    def _extract_instructions(self, text: str) -> Optional[str]:
        """从响应中提取 Markdown 文档部分"""
        markers = ["# 🧠 Expert Skill Guide", "# Expert Skill Guide", "## 1. Mental Model"]
        for marker in markers:
            if marker in text:
                return text[text.find(marker):].strip()
        return text
