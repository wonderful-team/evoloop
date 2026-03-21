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
from sqlalchemy import select, or_

from app.core.config import settings
from app.core.learning.frame_compressor import (
    CompressedFrame,
    CoordinateNormalizer,
    FrameCompressor,
    KeyframeCandidate,
    KeyframeSelector,
    NormalizedEvent,
)
from app.core.learning.prompts.builder import LearningPromptBuilder
from app.core.learning.synthesizer_utils import (
    cleanup_macro_steps,
    describe_normalized_position,
    export_skill_to_filesystem,
    extract_instructions_section,
    extract_yaml_block,
    normalize_timestamp_to_seconds,
    verify_macro_script,
)
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.llm.vision import VisionLLMFactory
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.drivers.adb import adb_driver
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

    # 配置（从 settings 读取，见 __init__）
    MAX_PROCESSING_TIME = 300     # 60秒超时
    DEFAULT_VIDEO_FPS = 15       # 默认帧率

    def __init__(self):
        self.compressor = FrameCompressor()
        # 从配置读取最大关键帧数
        self.keyframe_selector = KeyframeSelector(max_keyframes=settings.MAX_KEYFRAMES)
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

        # [v3 Unified] Log event source distribution
        source_counts = {}
        for e in events:
            src = getattr(e, 'source', 'unknown') or 'unknown'
            source_counts[src] = source_counts.get(src, 0) + 1
        source_summary = ", ".join([f"{k}={v}" for k, v in source_counts.items()])
        logger.info(f"[Unified] Fetched {len(events)} events ({source_summary})")

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

        # Step 6.5: 提取真实包名 (用于 open_app 指令)
        bundle_id = await self._get_bundle_id_from_events(events)
        logger.info(f"Target package detected: {bundle_id}")

        # Step 7: 调用多模态 LLM
        logger.info(f"Calling Vision LLM ({self.model_name})...")
        try:
            llm_response = await self._call_vision_llm(
                task_description=recording.task_description,
                bundle_id=bundle_id,
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
        if isinstance(target_macro, str):
            cleaned_macro = target_macro.strip()
            if cleaned_macro.startswith("```json"):
                cleaned_macro = cleaned_macro[7:].strip()
            elif cleaned_macro.startswith("```"):
                cleaned_macro = cleaned_macro[3:].strip()
            if cleaned_macro.endswith("```"):
                cleaned_macro = cleaned_macro[:-3].strip()
                
            if cleaned_macro.startswith("[") or cleaned_macro.startswith("{"):
                try:
                    target_macro = json.loads(cleaned_macro)
                except Exception as e:
                    logger.warning(f"Failed to parse LLM macro string as JSON: {e}")
                    target_macro = compiled_macro
            else:
                target_macro = compiled_macro

        # [Phase 15] 宏规范化 (处理 LLM 的不规范输出)
        if isinstance(target_macro, list):
            target_macro, _ = cleanup_macro_steps(target_macro)
            skill_data["macro_script"] = target_macro
        else:
            logger.warning("Target macro is not a list, falling back to compiled_macro.")
            target_macro = compiled_macro
            skill_data["macro_script"] = compiled_macro

        # 如果没有有效的 LLM 宏，使用编译出来的作为兜底
        if not skill_data.get("macro_script") or not isinstance(skill_data.get("macro_script"), list):
            skill_data["macro_script"] = compiled_macro
            skill_data["execution_mode"] = "deterministic"
        else:
            skill_data["execution_mode"] = "deterministic"

        processing_time = time.time() - start_time
        logger.info(f"Synthesis completed in {processing_time:.1f}s.")

        # Export to filesystem
        export_skill_to_filesystem(skill_data)

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
        return await verify_macro_script(
            macro_script=macro_script,
            thread_id="multimodal_dryrun",
            project_id=project_id,
            params={"max_scrolls": 2, "is_dry_run": True}
        )

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
            stmt = select(TraceEvent).where(
                or_(
                    TraceEvent.recording_session_id == session_id,
                    TraceEvent.session_id == session_id
                )
            ).order_by(TraceEvent.timestamp)
            result = await session.execute(stmt)
            events = list(result.scalars().all())

            session.expunge_all()

            if not events:
                return []

            for event in events:
                event.timestamp = normalize_timestamp_to_seconds(event.timestamp)

            if events:
                timestamps = [e.timestamp for e in events if e.timestamp is not None]
                if timestamps:
                    logger.info(f"[_fetch_events] Normalized timestamp range: {min(timestamps):.3f}s - {max(timestamps):.3f}s, count: {len(timestamps)}")

            return events

    async def _extract_and_compress_frames(
        self,
        video_path: str,
        keyframes: List[KeyframeCandidate],
        original_resolution: Tuple[int, int]
    ) -> List[CompressedFrame]:
        """批量提取并压缩帧"""
        frames = []
        logger.info(f"[KeyframeExtraction] Starting extraction of {len(keyframes)} keyframes from video: {video_path}")

        for i, keyframe in enumerate(keyframes, 1):
            try:
                # 提取单帧
                frame_path = await self._extract_single_frame(video_path, keyframe.timestamp)

                # 记录原始截图路径
                logger.info(
                    f"[KeyframeExtraction] Frame {i}/{len(keyframes)} | "
                    f"Timestamp: {keyframe.timestamp:.3f}s | "
                    f"Context: {keyframe.context} | "
                    f"Priority: {keyframe.priority} | "
                    f"Raw screenshot: {frame_path}"
                )

                # 执行压缩
                compressed = self.compressor.compress(frame_path)
                original_size_kb = len(compressed.data) / 1024

                # 自适应控制大小 (150KB 以内)
                if len(compressed.data) > 150 * 1024:
                    compressed = self.compressor.compress_with_target_size(frame_path, target_kb=100)
                    compressed_size_kb = len(compressed.data) / 1024
                    logger.info(
                        f"[KeyframeExtraction] Frame {i} compressed (adaptive): "
                        f"{original_size_kb:.1f}KB -> {compressed_size_kb:.1f}KB "
                        f"(ratio: {compressed.compression_ratio:.1%})"
                    )
                else:
                    compressed_size_kb = original_size_kb
                    logger.info(
                        f"[KeyframeExtraction] Frame {i} compressed: "
                        f"{compressed_size_kb:.1f}KB "
                        f"(ratio: {compressed.compression_ratio:.1%})"
                    )

                # 注入元数据供 Prompt 使用
                compressed.timestamp = keyframe.timestamp
                compressed.description = keyframe.description

                # 记录详细信息
                logger.debug(
                    f"[KeyframeExtraction] Frame {i} details: "
                    f"resolution={compressed.width}x{compressed.height}, "
                    f"original_resolution={compressed.original_size}, "
                    f"detail_level={compressed.detail_level}, "
                    f"description='{keyframe.description}'"
                )

                frames.append(compressed)
            except Exception as e:
                logger.warning(
                    f"[KeyframeExtraction] Failed to process frame {i} at {keyframe.timestamp}s: {e} | "
                    f"Context: {keyframe.context}, Description: {keyframe.description}"
                )
                continue

        logger.info(
            f"[KeyframeExtraction] Completed: {len(frames)}/{len(keyframes)} frames extracted successfully | "
            f"Total size: {sum(len(f.data) for f in frames) / 1024:.1f}KB"
        )
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
        """构建详细的事件内容上下文 (用于 Prompt) - 使用模板渲染"""
        from app.utils import render_template
        
        normalizer = CoordinateNormalizer(original_resolution[0], original_resolution[1])
        
        # 准备原始数据，格式化逻辑移至模板
        event_data = []
        for event in events:
            if event.action_type in ("mouse_move", "cursor_move", "touch_up"):
                continue
            
            norm_pos = normalizer.normalize(getattr(event, 'mouse_x', None), getattr(event, 'mouse_y', None))
            
            event_data.append({
                "action_name": "tap" if event.action_type == "touch_down" else event.action_type,
                "timestamp": getattr(event, 'timestamp', 0.0),
                "norm_pos": norm_pos,
                "position_desc": self._describe_position(norm_pos[0], norm_pos[1]) if norm_pos else None,
                "target": getattr(event, 'target_text', None),
                "window": getattr(event, 'window_title', None),
                "app": getattr(event, 'app_name', None),
                "key": getattr(event, 'key_name', None),
            })
        
        return render_template(
            "events/event_context.prompt.j2",
            events=event_data,
            resolution=original_resolution
        )

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
                payload = getattr(keyframe.related_event, 'payload', {}) or {}
                action_name = "tap" if keyframe.related_event.action_type == "touch_down" else keyframe.related_event.action_type
                frame.norm_events = [{
                    'action': action_name,
                    'position': pos,
                    'target_text': getattr(keyframe.related_event, 'target_text', None),
                    'timestamp': getattr(keyframe.related_event, 'timestamp', 0),
                    'package_name': payload.get('package_name')
                }]
        return frames

    async def _get_bundle_id_from_events(self, events: List[TraceEvent]) -> str:
        """
        从事件中提取包名。对于跨应用场景，返回逗号分隔的列表。
        """
        all_apps = []
        system_prefixes = (
            "com.android.systemui",
            "com.android.launcher",
            "com.google.android.inputmethod",
            "android",
            "scrcpy",
            "global_recorder"
        )

        for e in events:
            pkg = getattr(e, "app_name", None) or getattr(e, "node_name", None)
            if not pkg or pkg in ("unknown", "error", ""):
                p = e.payload if isinstance(e.payload, dict) else {}
                pkg = p.get("package_name")

            if pkg and pkg not in ("unknown", "error", ""):
                # Filter system apps but don't stop searching
                if not any(pkg.startswith(p) for p in system_prefixes):
                    if pkg not in all_apps:
                        all_apps.append(pkg)

        # Fallback to device re-poll if no user apps found
        if not all_apps:
            try:
                app_info = adb_driver.get_current_app()
                pkg = app_info.get("package")
                if pkg and pkg not in ("unknown", "error", "") and not pkg.startswith(system_prefixes):
                    all_apps.append(pkg)
            except Exception: pass

        if not all_apps:
            return "unknown"
            
        return ", ".join(all_apps)

    async def _call_vision_llm(self, task_description: str, bundle_id: str, frames: List[CompressedFrame], event_context: str) -> str:
        """构建多模态消息并调用 LLM"""
        from langchain_core.messages import HumanMessage, SystemMessage

        # 加载新的系统模板
        system_prompt = self.prompt_builder.build_multimodal_synthesis_prompt({})

        # 构建人机交互内容
        content = []
        
        # 1. 构建核心任务上下文
        app_context_label = "Target Applications" if ", " in bundle_id else "Target Application (Package Name)"
        
        context_vars = {
            "task_description": task_description,
            "app_context_label": app_context_label,
            "bundle_id": bundle_id,
            "event_context": event_context
        }
        
        task_context = self.prompt_builder.build_multimodal_context_prompt(context_vars)

        content.append({
            "type": "text", 
            "text": task_context
        })

        # 2. 关键帧详情 (附带图片) - 使用新模板
        frame_vars = []
        for frame in frames:
            f_data = {
                "timestamp": frame.timestamp,
                "description": frame.description,
                "norm_events": []
            }
            if frame.norm_events:
                for evt in frame.norm_events:
                    pos = evt.get('position')
                    pos_desc = self._describe_position(pos[0], pos[1]) if pos else ""
                    f_data["norm_events"].append({
                        "action": evt["action"],
                        "position": pos,
                        "position_desc": pos_desc,
                        "target_text": evt.get("target_text")
                    })
            frame_vars.append(f_data)

        try:
            from app.utils import render_template
            frames_narrative = render_template("vision/multimodal_frames.prompt.j2", frames=frame_vars)
            content.append({"type": "text", "text": frames_narrative})
        except Exception as e:
            logger.error(f"Failed to render Multimodal Frames template: {e}")
            content.append({"type": "text", "text": "## Keyframes Analysis\n(Error rendering frames detail)"})
            
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
        return describe_normalized_position(norm_x, norm_y)

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
        return extract_yaml_block(text)

    def _extract_instructions(self, text: str) -> Optional[str]:
        """从响应中提取 Markdown 文档部分"""
        # [v4 Meta-Clean] 动态匹配预定义的标准化标记
        result = extract_instructions_section(text)
        # 如果工具函数返回原文且没有探测到预期的 Meta 标签，则返回 None 交由调用者回退到原文
        # 这也是为了防止直接暴露纯文本响应而没有解析
        if result == text:
             # 再尝试寻找通用的 Expert 指导标记
             if "# " not in text and "## " not in text:
                 return None
        return result
