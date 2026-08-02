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

import asyncio
import base64
import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import yaml
from sqlalchemy import or_, select

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.engine.message.native_classes import HumanMessage, SystemMessage
from app.core.execution.macro.compiler import MacroScriptCompiler
from app.core.execution.macro.schemas import MacroVerificationResult
from app.core.execution.macro.utils import cleanup_macro_steps, verify_macro_script
from app.core.learning.prompts.builder import LearningPromptBuilder
from app.core.learning.schemas import RecordingSession
from app.core.learning.synthesizer_utils import (
    describe_normalized_position,
    extract_instructions_section,
    extract_yaml_block,
    normalize_timestamp_to_seconds,
)
from app.core.learning.workflow_synthesizer import SynthesizedSkill
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database import session_scope
from app.infrastructure.drivers.adb import adb_driver
from app.infrastructure.llm.vision import VisionLLMFactory
from app.infrastructure.video.compressor import (
    CoordinateNormalizer,
    FrameCompressor,
    KeyframeSelector,
)
from app.infrastructure.video.schemas import (
    CompressedFrame,
    KeyframeCandidate,
    VideoInfo,
)
from app.models import TraceEvent
from app.utils.template import render_template

logger = logging.getLogger(__name__)


class MultimodalSkillSynthesizer:
    """
    多模态 Skill 合成器

    同步处理流程，直接返回合成结果。
    """

    # 配置（从 settings 读取，见 __init__）
    DEFAULT_VIDEO_FPS = 15  # 默认帧率

    def __init__(self):
        self.compressor = FrameCompressor()
        # 从配置读取最大关键帧数
        self.keyframe_selector = KeyframeSelector(max_keyframes=settings.MAX_KEYFRAMES)
        self.prompt_builder = LearningPromptBuilder()
        # 仅记录用于日志/元数据的视觉模型名称；实际 LLM 在 synthesize 中异步创建
        self.model_name = SystemConfigService.get_value("VISION_MODEL") or ""

    async def synthesize(self, recording: RecordingSession) -> dict:
        """
        同步合成主流程

        Args:
            recording: 录制会话数据

        Returns:
            dict: 包含 skill 数据 and 元信息
        """
        start_time = time.time()
        logger.info(f"Starting multimodal synthesis for session {recording.session_id}")

        # Step 1: 获取视频信息
        video_info = await self._get_video_info(recording.video_path)
        logger.info(
            f"Video: {video_info.width}x{video_info.height}, {video_info.duration:.1f}s"
        )

        # Step 1.5: 提取视频音频轨并进行语音识别 (Speech-to-Text)
        voice_transcript = None
        try:
            audio_path = await self._extract_audio(recording.video_path)
            if audio_path and os.path.exists(audio_path):
                from app.infrastructure.voice import transcribe_file

                logger.info("Transcribing extracted audio track...")
                stt_result = await transcribe_file(audio_path)
                if stt_result and stt_result.text.strip():
                    voice_transcript = stt_result.text.strip()
                    logger.info(f"Audio transcription success: {voice_transcript}")
                try:
                    await asyncio.to_thread(os.unlink, audio_path)
                except Exception:
                    logger.debug("Failed to remove temporary audio file", exc_info=True)
        except Exception as e:
            logger.warning(f"Audio transcription failed or skipped: {e}")

        # Step 2: 获取事件序列
        events = await self._fetch_events(recording.session_id)
        if not events:
            raise ValueError(f"No events found for session {recording.session_id}")

        # [v3 Unified] Log event source distribution
        source_counts = {}
        for e in events:
            src = e.source
            source_counts[src] = source_counts.get(src, 0) + 1
        source_summary = ", ".join([f"{k}={v}" for k, v in source_counts.items()])
        logger.info(f"[Unified] Fetched {len(events)} events ({source_summary})")

        # Step 3: 智能选择关键帧
        keyframes = self.keyframe_selector.select_keyframes(
            events=events,
            video_duration=video_info.duration,
        )
        logger.info(f"Selected {len(keyframes)} keyframes")

        if not keyframes:
            raise ValueError("No keyframes could be selected from the recording")

        # Step 4: 提取并压缩帧
        compressed_frames = await self._extract_and_compress_frames(
            video_path=recording.video_path,
            keyframes=keyframes,
            original_resolution=(video_info.width, video_info.height),
        )
        logger.info(f"Compressed {len(compressed_frames)} frames")

        # Step 5: 构建事件上下文（用于 Prompt 文本部分）
        event_context = self._build_event_context(
            events=events, original_resolution=(video_info.width, video_info.height)
        )

        # Step 6: 关联事件到帧（用于多模态图片标注）
        frames_with_events = self._associate_events_to_frames(
            frames=compressed_frames,
            keyframes=keyframes,
            normalizer=CoordinateNormalizer(video_info.width, video_info.height),
        )

        # Step 6.5: 提取真实包名 (用于 open_app 指令)
        bundle_id = await self._get_bundle_id_from_events(events)
        logger.info(f"Target package detected: {bundle_id}")

        # Step 7: 调用多模态 LLM
        logger.info(f"Creating Vision LLM ({self.model_name})...")
        self.vision_llm = await VisionLLMFactory.create_vision_llm_async(temperature=0.3)
        try:
            llm_response = await self._call_vision_llm(
                task_description=recording.task_description,
                bundle_id=bundle_id,
                frames=frames_with_events,
                event_context=event_context,
                voice_transcript=voice_transcript,
            )
        except Exception as e:
            logger.error(f"Vision LLM call failed: {e}")
            raise RuntimeError(f"LLM analysis failed: {e}")

        # Step 8: 解析 LLM 输出
        parsed = self._parse_llm_response(llm_response, recording)
        skill_data = parsed["skill"]

        # Step 9: 辅助生成确定性宏脚本 (Fallback/Verification Basis)
        compiled_macro = await self._compile_macro_from_events(events)

        # Step 10: 验证 Dry-run (优先验证实际要返回的宏)
        target_macro = parsed["macro_script"] or compiled_macro

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

        # [Phase 15] 宏规范化 (处理 LLM 的不规范输出) 并转换为 YAML 存储
        final_steps = None
        if isinstance(target_macro, list):
            final_steps, _ = cleanup_macro_steps(target_macro)
        else:
            logger.warning(
                "Target macro is not a list, falling back to compiled_macro."
            )
            final_steps = compiled_macro

        # 如果没有有效的宏，使用编译出来的作为兜底
        if not final_steps or not isinstance(final_steps, list):
            final_steps = compiled_macro

        # Convert to YAML string for storage; the macro is returned separately
        # from the skill metadata to keep the two models decoupled.
        macro_script = None
        if final_steps:
            macro_script = await asyncio.to_thread(
                yaml.dump,
                final_steps,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        processing_time = time.time() - start_time
        logger.info(f"Synthesis completed in {processing_time:.1f}s.")

        # File export happens after DB commit via the SKILL_CREATED event
        # subscriber — synthesis itself must not touch the filesystem.

        return {
            "skill": skill_data,
            "macro_script": macro_script,
            "metadata": {
                "processing_time_seconds": processing_time,
                "frames_analyzed": len(compressed_frames),
                "events_processed": len(events),
                "video_duration": video_info.duration,
                "model": self.model_name,
            },
        }

    async def _compile_macro_from_events(self, events: list[TraceEvent]) -> list[dict]:
        """从 TraceEvent 序列编译确定性宏脚本 (使用 MacroScriptCompiler)"""
        from app.core.learning.trace_parser import TraceParser

        if not events:
            return []

        thread_id = events[0].thread_id
        session_id = events[0].recording_session_id

        parser = TraceParser(thread_id=thread_id, session_id=session_id)
        # 转换为 TraceSequence
        sequence = parser._convert_to_sequence(events)

        compiler = MacroScriptCompiler()
        macro_script = compiler.compile(sequence)
        # MacroScriptCompiler.compile returns a MacroScript object
        if hasattr(macro_script, "steps"):
            return [
                s if isinstance(s, dict) else s.model_dump(exclude_none=True)
                for s in macro_script.steps
            ]
        # Defensive: older implementations returned a YAML string
        if isinstance(macro_script, str):
            try:
                data = yaml.safe_load(macro_script)
                if isinstance(data, dict) and "steps" in data:
                    return data["steps"]
                return data if isinstance(data, list) else []
            except (ValueError, TypeError, KeyError):
                return []
        return macro_script if isinstance(macro_script, list) else []

    async def verify_macro(
        self, macro_script: str, project_id: int = DEFAULT_PROJECT_ID
    ) -> MacroVerificationResult:
        """Dry-run 验证宏脚本的有效性"""
        return await verify_macro_script(
            macro_script=macro_script,
            thread_id="multimodal_dryrun",
            project_id=project_id,
            params={"max_scrolls": 2, "is_dry_run": True},
        )

    async def _extract_audio(self, video_path: str) -> str | None:
        """FFmpeg 提取视频中的音频轨并存为临时 WAV 文件"""
        output_path = os.path.join(
            tempfile.gettempdir(), f"evoloop_audio_{os.path.basename(video_path)}.wav"
        )

        # ffmpeg -y -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 output.wav
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vn",  # 禁用视频流
            "-acodec",
            "pcm_s16le",  # 使用无损 PCM 16-bit
            "-ar",
            "16000",  # 16kHz
            "-ac",
            "1",  # 单声道
            output_path,
        ]
        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, timeout=30
            )
            if result.returncode == 0:
                if (
                    await asyncio.to_thread(os.path.exists, output_path)
                    and await asyncio.to_thread(os.path.getsize, output_path) > 1000
                ):
                    logger.info(
                        f"Successfully extracted audio from video to: {output_path}"
                    )
                    return output_path
            else:
                stderr = result.stderr.decode() if result.stderr else ""
                logger.warning(f"Audio extraction warning (ffmpeg): {stderr}")
        except Exception:
            logger.exception("Failed to extract audio track")

        return None

    async def _get_video_info(self, video_path: str) -> VideoInfo:
        """使用 ffprobe JSON 获取视频元信息（更鲁棒）"""
        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate,duration",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                video_path,
            ]
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=10
            )
            data = json.loads(result.stdout)

            stream = data["streams"][0]
            format_data = data.get("format", {})

            # 优先从 format 获取 duration
            duration = float(format_data.get("duration") or stream.get("duration", 0.0))
            width = int(stream["width"])
            height = int(stream["height"])

            # 解析帧率
            fps_str = stream.get("r_frame_rate", "15/1")
            fps = (
                float(fps_str.split("/")[0]) / float(fps_str.split("/")[1])
                if "/" in fps_str
                else float(fps_str)
            )

            return VideoInfo(duration=duration, width=width, height=height, fps=fps)
        except Exception:
            logger.exception(f"Failed to get video info for {video_path}")
            return VideoInfo(
                duration=30.0, width=1920, height=1080, fps=self.DEFAULT_VIDEO_FPS
            )

    async def _fetch_events(self, session_id: str) -> list[TraceEvent]:
        """从数据库获取事件并进行时间轴归一化"""
        async with session_scope() as session:
            stmt = (
                select(TraceEvent)
                .where(
                    or_(
                        TraceEvent.recording_session_id == session_id,
                        TraceEvent.session_id == session_id,
                    )
                )
                .order_by(TraceEvent.timestamp)
            )
            result = await session.execute(stmt)
            events = list(result.scalars().all())

            session.expunge_all()

            if not events:
                return []

            for event in events:
                if event.timestamp is not None:
                    event.timestamp = normalize_timestamp_to_seconds(event.timestamp)

            if events:
                timestamps = [e.timestamp for e in events if e.timestamp is not None]
                if timestamps:
                    logger.info(
                        f"[_fetch_events] Normalized timestamp range: {min(timestamps):.3f}s - {max(timestamps):.3f}s, count: {len(timestamps)}"
                    )

            return events

    async def _extract_and_compress_frames(
        self,
        video_path: str,
        keyframes: list[KeyframeCandidate],
        original_resolution: tuple[int, int],
    ) -> list[CompressedFrame]:
        """批量提取并压缩帧"""
        frames = []
        logger.info(
            f"[KeyframeExtraction] Starting extraction of {len(keyframes)} keyframes from video: {video_path}"
        )

        for i, keyframe in enumerate(keyframes, 1):
            try:
                # 提取单帧
                frame_path = await self._extract_single_frame(
                    video_path, keyframe.timestamp
                )

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
                    compressed = self.compressor.compress_with_target_size(
                        frame_path, target_kb=100
                    )
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
            except Exception:
                logger.exception(
                    f"[KeyframeExtraction] Failed to process frame {i} at {keyframe.timestamp}s | "
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
        output_path = Path(tempfile.gettempdir()) / f"evoloop_frame_{timestamp:.3f}.jpg"

        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            video_path,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-pix_fmt",
            "yuvj420p",  # Mac JPEG 兼容性
            str(output_path),
        ]
        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, timeout=10
            )
            if result.returncode != 0:
                stderr = result.stderr.decode() if result.stderr else ""
                raise RuntimeError(f"FFmpeg extraction failed: {stderr}")
            return str(output_path)
        except Exception:
            logger.exception(f"Failed to extract frame at {timestamp}s from {video_path}")
            raise

    def _build_event_context(
        self, events: list[TraceEvent], original_resolution: tuple[int, int]
    ) -> str:
        """构建详细的事件内容上下文 (用于 Prompt) - 使用模板渲染"""
        normalizer = CoordinateNormalizer(
            original_resolution[0], original_resolution[1]
        )

        # 准备原始数据，格式化逻辑移至模板
        event_data = []
        for event in events:
            if event.action_type in ("mouse_move", "cursor_move", "touch_up"):
                continue

            norm_pos = normalizer.normalize(event.mouse_x, event.mouse_y)

            event_data.append(
                {
                    "action_name": "tap"
                    if event.action_type == "touch_down"
                    else event.action_type,
                    "timestamp": event.timestamp or 0.0,
                    "norm_pos": norm_pos,
                    "position_desc": self._describe_position(norm_pos[0], norm_pos[1])
                    if norm_pos
                    else None,
                    "target": event.target_text,
                    "window": event.window_title,
                    "app": event.app_name,
                    "key": event.key_name,
                }
            )

        return render_template(
            "common/events/event_context.prompt.j2",
            events=event_data,
            resolution=original_resolution,
        )

    def _associate_events_to_frames(
        self,
        frames: list[CompressedFrame],
        keyframes: list[KeyframeCandidate],
        normalizer: CoordinateNormalizer,
    ) -> list[CompressedFrame]:
        """将事件语义关联到关键帧对象中"""
        for frame, keyframe in zip(frames, keyframes, strict=False):
            if keyframe.related_event:
                pos = normalizer.normalize(
                    getattr(keyframe.related_event, "mouse_x", None),
                    getattr(keyframe.related_event, "mouse_y", None),
                )
                payload = getattr(keyframe.related_event, "payload", {}) or {}
                action_name = (
                    "tap"
                    if keyframe.related_event.action_type == "touch_down"
                    else keyframe.related_event.action_type
                )
                frame.norm_events = [
                    {
                        "action": action_name,
                        "position": pos,
                        "target_text": getattr(
                            keyframe.related_event, "target_text", None
                        ),
                        "timestamp": getattr(keyframe.related_event, "timestamp", 0),
                        "package_name": payload.get("package_name"),
                    }
                ]
        return frames

    async def _get_bundle_id_from_events(self, events: list[TraceEvent]) -> str:
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
            "global_recorder",
        )

        for e in events:
            pkg = e.app_name or e.node_name
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
                if (
                    pkg
                    and pkg not in ("unknown", "error", "")
                    and not pkg.startswith(system_prefixes)
                ):
                    all_apps.append(pkg)
            except Exception as e:
                logger.debug(f"Failed to get current app from ADB: {e}")

        if not all_apps:
            return "unknown"

        return ", ".join(all_apps)

    async def _call_vision_llm(
        self,
        task_description: str,
        bundle_id: str,
        frames: list[CompressedFrame],
        event_context: str,
        voice_transcript: str | None = None,
    ) -> str:
        """构建多模态消息并调用 LLM"""
        # 加载新的系统模板
        system_prompt = self.prompt_builder.build_multimodal_synthesis_prompt({})

        # 构建人机交互内容
        content = []

        # 1. 构建核心任务上下文
        app_context_label = (
            "Target Applications"
            if ", " in bundle_id
            else "Target Application (Package Name)"
        )

        context_vars = {
            "task_description": task_description,
            "app_context_label": app_context_label,
            "bundle_id": bundle_id,
            "event_context": event_context,
            "voice_transcript": voice_transcript,
        }

        task_context = self.prompt_builder.build_multimodal_context_prompt(context_vars)

        content.append({"type": "text", "text": task_context})

        # 2. 关键帧详情 (附带图片) - 使用新模板
        frame_vars = []
        for frame in frames:
            f_data = {
                "timestamp": frame.timestamp,
                "description": frame.description,
                "norm_events": [],
            }
            if frame.norm_events:
                for evt in frame.norm_events:
                    pos = evt.get("position")
                    pos_desc = self._describe_position(pos[0], pos[1]) if pos else ""
                    f_data["norm_events"].append(
                        {
                            "action": evt["action"],
                            "position": pos,
                            "position_desc": pos_desc,
                            "target_text": evt.get("target_text"),
                        }
                    )
            frame_vars.append(f_data)

        try:
            frames_narrative = render_template("core/vision/multimodal_frames.prompt.j2", frames=frame_vars)
            content.append({"type": "text", "text": frames_narrative})
        except Exception:
            logger.exception("Failed to render Multimodal Frames template")
            content.append(
                {
                    "type": "text",
                    "text": "## Keyframes Analysis\n(Error rendering frames detail)",
                }
            )

        # 插入 Base64 图片 (每个关键帧一张)
        for frame in frames:
            if not frame.data:
                continue
            base64_img = base64.b64encode(frame.data).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"},
                }
            )

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=content)]

        response = await self.vision_llm.ainvoke(messages)
        return str(response.content)

    def _describe_position(self, norm_x: float, norm_y: float) -> str:
        """将归一化坐标转换为精细的语义描述 (5x5 风格)"""
        return describe_normalized_position(norm_x, norm_y)

    def _parse_llm_response(self, response: str, recording: RecordingSession) -> dict:
        """Parse LLM response into skill metadata and an optional raw macro."""
        yaml_content = self._extract_yaml(response)
        instructions = self._extract_instructions(response)

        try:
            metadata = yaml.safe_load(yaml_content) if yaml_content else {}
        except Exception as e:
            logger.error(f"Failed to parse LLM YAML metadata: {e}")
            metadata = {}

        # The prompt asks for macro_script as a YAML object ({version, metadata,
        # steps}); downstream (synthesize step 9-10) consumes either a step list
        # or a JSON/YAML string. Normalize here so a spec-compliant LLM response
        # never hits a pydantic str-field ValidationError.
        raw_macro = metadata.get("macro_script")
        if isinstance(raw_macro, dict):
            macro_value: object = raw_macro.get("steps", [])
        elif raw_macro is None:
            macro_value = None
        else:
            macro_value = raw_macro

        return {
            "skill": SynthesizedSkill(
                name=metadata.get("name", "unnamed_skill"),
                namespace=metadata.get("namespace", "misc"),
                description=metadata.get("description", ""),
                trigger_patterns=metadata.get("trigger_patterns", []),
                parameters=metadata.get("parameters", []),
                instructions=instructions or response,
                source_session_id=recording.session_id,
                source_thread_id=recording.thread_id,
            ),
            "macro_script": macro_value,
        }

    def _extract_yaml(self, text: str) -> str | None:
        """提取 YAML 代码块"""
        return extract_yaml_block(text)

    def _extract_instructions(self, text: str) -> str | None:
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
