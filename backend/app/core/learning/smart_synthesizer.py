"""
Smart Replay Synthesizer - Intelligent skill generation from annotated recordings.

Combines user annotations, video frames, and event sequences to generate
high-quality skills with detailed instructions and optimized macro scripts.
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from app.core.config import settings
from app.core.learning.frame_extractor import FrameExtractor
from app.core.learning.macro_optimizer import MacroOptimizer
from app.core.learning.trace_parser import TraceParser, TraceSequence
from app.core.vision.engine import vision_engine
from app.core.vision.types import VisionTask, UIElement
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.llm.factory import LLMFactory
from app.models import RecordingAnnotation, SynthesisJob, TraceEvent

logger = logging.getLogger(__name__)


@dataclass
class FrameAnalysis:
    """Analysis result for a single video frame"""
    timestamp_ms: int
    frame_path: str
    scene_description: str
    ui_elements: list[str] = field(default_factory=list)
    user_action_intent: str = ""
    data_of_interest: list[dict] = field(default_factory=list)
    related_events: list[dict] = field(default_factory=list)


@dataclass
class TaskPhase:
    """A distinct phase of the task"""
    name: str
    start_time_ms: int
    end_time_ms: int
    description: str
    key_actions: list[str] = field(default_factory=list)
    data_extracted: list[str] = field(default_factory=list)
    annotations: list[int] = field(default_factory=list)  # annotation ids
    is_repeatable: bool = False


@dataclass
class CriticalStep:
    """A critical step in the workflow"""
    type: str  # "action" | "extract" | "loop"
    step_number: int
    description: str
    source: str  # "dom" | "mobile" | "desktop"

    # For actions
    action_type: str | None = None
    selector: str | None = None
    payload: dict = field(default_factory=dict)

    # For extracts
    extract_type: str | None = None
    data_key: str | None = None
    region: dict | None = None  # {x, y, width, height}

    # For loops
    loop_condition: dict | None = None
    max_iterations: int = 100
    sub_steps: list = field(default_factory=list)


@dataclass
class GeneratedSkill:
    """Final generated skill"""
    name: str
    description: str
    namespace: str
    trigger_patterns: list[str]
    instructions: str
    execution_mode: str
    macro_script: list[dict]
    parameters: list[dict] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "namespace": self.namespace,
            "trigger_patterns": self.trigger_patterns,
            "instructions": self.instructions,
            "execution_mode": self.execution_mode,
            "macro_script": self.macro_script,
            "parameters": self.parameters,
            "preconditions": self.preconditions,
        }


class SmartSynthesizer:
    """
    Intelligent skill synthesizer that combines:
    - User annotations on video
    - Task goal description
    - Event sequence analysis
    - Vision-based frame understanding
    """

    def __init__(
        self,
        job_id: int,
        session_id: str,
        thread_id: str | None,
        task_goal: str,
        annotations: list[RecordingAnnotation],
    ):
        self.job_id = job_id
        self.session_id = session_id
        self.thread_id = thread_id
        self.task_goal = task_goal
        self.annotations = annotations

        self.video_path: str | None = None
        self.events: list[TraceEvent] = []
        self.video_info: dict = {}
        self.task_phases: list[TaskPhase] = []

    async def synthesize(self) -> GeneratedSkill:
        """
        Main synthesis pipeline
        """
        logger.info(f"[Job {self.job_id}] Starting smart synthesis for goal: {self.task_goal}")

        # Phase 1: Load data
        await self._update_status("loading_data", 5)
        await self._load_data()

        # Phase 2: Extract keyframes
        await self._update_status("extracting_keyframes", 15)
        keyframes = await self._extract_keyframes()

        # Phase 3: Analyze frames with Vision LLM
        await self._update_status("analyzing_frames", 35)
        frame_analyses = await self._analyze_frames_with_annotations(keyframes)

        # Phase 4: Understand task phases
        await self._update_status("understanding_phases", 55)
        phases = await self._understand_task_phases(frame_analyses)
        self.task_phases = phases  # Save for later use in macro generation

        # Phase 5: Identify critical steps
        await self._update_status("identifying_steps", 70)
        critical_steps = await self._identify_critical_steps(phases)

        # Phase 6: Generate macro script
        await self._update_status("generating_macro", 80)
        macro_script = await self._generate_optimized_macro(critical_steps)

        # Phase 7: Generate skill metadata
        await self._update_status("generating_metadata", 90)
        skill = await self._generate_skill_metadata(phases, macro_script)

        await self._update_status("completed", 100)
        logger.info(f"[Job {self.job_id}] Synthesis completed: {skill.name}")

        return skill

    async def _update_status(self, phase: str, progress: int):
        """Update job status in database"""
        try:
            async with session_scope() as db:
                stmt = select(SynthesisJob).where(SynthesisJob.id == self.job_id)
                result = await db.execute(stmt)
                job = result.scalar_one()

                job.status = "processing"
                job.current_phase = phase
                job.progress_percent = progress
                await db.commit()

            logger.debug(f"[Job {self.job_id}] Phase: {phase}, Progress: {progress}%")
        except Exception as e:
            logger.warning(f"Failed to update job status: {e}")

    async def _load_data(self):
        """Load video path and events"""
        # Get video path from recording session
        # This would typically be stored with the session
        # For now, we look for the most recent video in the recordings directory
        recordings_dir = os.path.expanduser("~/.evoloop/recordings")
        if os.path.exists(recordings_dir):
            videos = sorted(
                [f for f in os.listdir(recordings_dir) if f.endswith('.mp4')],
                key=lambda x: os.path.getmtime(os.path.join(recordings_dir, x)),
                reverse=True
            )
            if videos:
                self.video_path = os.path.join(recordings_dir, videos[0])

        # Load events
        async with session_scope() as db:
            stmt = select(TraceEvent).where(
                TraceEvent.recording_session_id == self.session_id
            ).order_by(TraceEvent.step_number)

            result = await db.execute(stmt)
            self.events = list(result.scalars().all())

        logger.info(f"[Job {self.job_id}] Loaded {len(self.events)} events, video: {self.video_path}")

    async def _extract_keyframes(self) -> list[dict]:
        """
        Extract key video frames using FrameExtractor (FFmpeg),
        forcing inclusion of annotation timestamps
        """
        if not self.video_path or not os.path.exists(self.video_path):
            logger.warning(f"Video not found: {self.video_path}")
            return []

        # Estimate duration from file size and assume 30fps as fallback
        # FrameExtractor handles actual frame extraction
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", self.video_path],
                capture_output=True, text=True, timeout=5
            )
            duration_ms = float(result.stdout.strip()) * 1000
        except:
            duration_ms = 60000  # Default 1 minute

        self.video_info = {
            "duration_ms": duration_ms,
        }

        # Collect forced timestamps from annotations
        forced_timestamps = set()
        for ann in self.annotations:
            forced_timestamps.add(ann.video_timestamp_ms)
            # Also add slightly before and after for context
            forced_timestamps.add(max(0, ann.video_timestamp_ms - 500))
            forced_timestamps.add(min(int(duration_ms), ann.video_timestamp_ms + 500))

        # Add event timestamps
        event_timestamps = set()
        for event in self.events:
            if event.timestamp:
                event_timestamps.add(int(event.timestamp * 1000))

        # Combine and sort
        all_keyframes = sorted(forced_timestamps | event_timestamps)

        # Limit to reasonable number
        if len(all_keyframes) > 20:
            # Sample evenly but keep forced timestamps
            forced_set = forced_timestamps
            other_frames = sorted(event_timestamps - forced_set)

            # Keep all forced, sample others
            samples_needed = 20 - len(forced_set)
            if samples_needed > 0 and other_frames:
                step = max(1, len(other_frames) // samples_needed)
                sampled = other_frames[::step][:samples_needed]
                all_keyframes = sorted(forced_set | set(sampled))

        # Extract frames using FrameExtractor (FFmpeg)
        extractor = FrameExtractor(self.video_path, session_id=self.session_id)
        frame_paths = await asyncio.get_event_loop().run_in_executor(
            None, extractor.extract_frames, all_keyframes
        )

        # Build keyframes list
        keyframes = []
        for ts_ms, frame_path in zip(all_keyframes, frame_paths):
            if frame_path and os.path.exists(frame_path):
                keyframes.append({
                    "timestamp_ms": ts_ms,
                    "frame_path": frame_path,
                })

        # Save keyframes info to job
        await self._save_intermediate_result("keyframes", keyframes)

        logger.info(f"[Job {self.job_id}] Extracted {len(keyframes)} keyframes")
        return keyframes

    async def _analyze_frames_with_annotations(
        self,
        keyframes: list[dict]
    ) -> list[FrameAnalysis]:
        """
        Use Vision LLM to analyze each keyframe, considering annotations
        """
        analyses = []

        for i, frame in enumerate(keyframes):
            # Find annotations near this frame
            frame_annotations = [
                ann for ann in self.annotations
                if abs(ann.video_timestamp_ms - frame["timestamp_ms"]) < 1000
            ]

            # Build vision prompt
            prompt = self._build_vision_prompt(frame, frame_annotations)

            # Call Vision LLM (if multimodal available)
            try:
                analysis = await self._call_vision_llm(
                    frame["frame_path"],
                    prompt,
                    frame_annotations
                )
            except Exception as e:
                logger.warning(f"Vision analysis failed for frame {i}: {e}")
                analysis = {
                    "scene_description": "Frame analysis failed",
                    "ui_elements": [],
                    "intent": "",
                    "data_regions": [],
                }

            # Find related events
            related_events = [
                {
                    "type": e.action_type,
                    "timestamp": e.timestamp,
                    "payload": e.action_payload,
                }
                for e in self.events
                if e.timestamp and abs(e.timestamp * 1000 - frame["timestamp_ms"]) < 500
            ]

            analyses.append(FrameAnalysis(
                timestamp_ms=frame["timestamp_ms"],
                frame_path=frame["frame_path"],
                scene_description=analysis.get("scene_description", ""),
                ui_elements=analysis.get("ui_elements", []),
                user_action_intent=analysis.get("intent", ""),
                data_of_interest=[
                    {
                        "type": ann.annotation_type,
                        "note": ann.user_note,
                        "region": {
                            "x": ann.region_x,
                            "y": ann.region_y,
                            "width": ann.region_width,
                            "height": ann.region_height,
                        } if ann.region_x else None,
                    }
                    for ann in frame_annotations
                ],
                related_events=related_events,
            ))

        # Save analyses
        await self._save_intermediate_result("frame_analyses", [
            {
                "timestamp_ms": a.timestamp_ms,
                "scene_description": a.scene_description,
                "ui_elements": a.ui_elements,
                "intent": a.user_action_intent,
                "data_of_interest": a.data_of_interest,
            }
            for a in analyses
        ])

        return analyses

    def _build_vision_prompt(
        self,
        frame: dict,
        annotations: list[RecordingAnnotation]
    ) -> str:
        """Build prompt for Vision LLM"""
        prompt_parts = [
            f"Task Goal: {self.task_goal}",
            "",
            "Analyze this screenshot from a user's recording session.",
            "Describe:",
            "1. What is currently shown on screen",
            "2. What UI elements are visible (list them)",
            "3. What the user might be trying to do at this moment",
        ]

        if annotations:
            prompt_parts.append("")
            prompt_parts.append("The user has marked the following regions of interest:")
            for i, ann in enumerate(annotations):
                note = f" - Note: {ann.user_note}" if ann.user_note else ""
                if ann.region_x is not None:
                    prompt_parts.append(
                        f"- Region {i+1}: Bounding box at "
                        f"({ann.region_x:.0f}, {ann.region_y:.0f}) "
                        f"size {ann.region_width:.0f}x{ann.region_height:.0f}"
                        f"{note}"
                    )
                else:
                    prompt_parts.append(f"- Point {i+1}: Marked at this timestamp{note}")

        prompt_parts.append("")
        prompt_parts.append("Respond in JSON format:")
        prompt_parts.append(json.dumps({
            "scene_description": "Brief description of what's on screen",
            "ui_elements": ["List of visible UI elements like buttons, forms, etc"],
            "intent": "What the user is likely trying to accomplish",
            "data_regions": [
                {
                    "description": "What data appears to be in each marked region",
                    "suggested_selector": "CSS selector or accessibility identifier if identifiable",
                }
            ],
        }, indent=2))

        return "\n".join(prompt_parts)

    async def _call_vision_llm(
        self,
        frame_path: str,
        prompt: str,
        annotations: list[RecordingAnnotation]
    ) -> dict:
        """
        Call Vision-capable LLM to analyze frame using the existing VisionEngine.
        """
        try:
            # Use the existing VisionEngine to analyze the frame
            # This automatically routes to the appropriate provider (GPT-4V, Claude, etc.)
            result = await vision_engine.process(
                task=VisionTask.ANALYZE,
                image_source=frame_path,
                prompt=prompt
            )

            # Parse the VisionResult into the expected format
            # UIElement list contains detected elements, we'll format them
            ui_elements = []
            for element in result.elements:
                element_desc = f"{element.element_type}"
                if element.text:
                    element_desc += f" (text: '{element.text[:50]}')"
                if element.attributes:
                    element_desc += f" {element.attributes}"
                ui_elements.append(element_desc)

            # Extract data regions from annotations with bounding box info
            data_regions = []
            for i, ann in enumerate(annotations):
                region_info = {
                    "description": ann.user_note or f"Annotation {i+1}",
                    "region": {
                        "x": ann.region_x,
                        "y": ann.region_y,
                        "width": ann.region_width,
                        "height": ann.region_height,
                    } if ann.region_x else None,
                }
                data_regions.append(region_info)

            return {
                "scene_description": result.text or "UI screenshot analysis",
                "ui_elements": ui_elements,
                "intent": self._infer_intent_from_annotations(annotations),
                "data_regions": data_regions,
                "raw_vision_result": {
                    "text": result.text,
                    "element_count": len(result.elements),
                    "metadata": result.metadata,
                }
            }

        except Exception as e:
            logger.warning(f"Vision analysis failed for frame: {e}")
            # Fallback to context-based analysis
            return self._fallback_frame_analysis(frame_path, annotations)

    def _infer_intent_from_annotations(self, annotations: list[RecordingAnnotation]) -> str:
        """Infer user intent from annotations"""
        if not annotations:
            return ""

        # Combine user notes to understand intent
        notes = [ann.user_note for ann in annotations if ann.user_note]
        if notes:
            return f"User is interested in: {', '.join(notes)}"

        # Default based on annotation type
        types = [ann.annotation_type for ann in annotations]
        if "extract_region" in types:
            return "Extracting data from marked regions"
        return "Reviewing marked regions"

    def _fallback_frame_analysis(
        self,
        frame_path: str,
        annotations: list[RecordingAnnotation]
    ) -> dict:
        """Fallback analysis when vision engine fails"""
        timestamp_ms = self._get_timestamp_from_frame(frame_path)

        # Build context from events
        event_context = self._get_event_context_at_timestamp(timestamp_ms)

        return {
            "scene_description": f"Frame at {timestamp_ms}ms. Events: {event_context}",
            "ui_elements": [],
            "intent": self._infer_intent_from_annotations(annotations),
            "data_regions": [
                {
                    "description": ann.user_note or f"Region {i+1}",
                    "suggested_selector": None,
                }
                for i, ann in enumerate(annotations)
            ],
        }

    def _get_timestamp_from_frame(self, frame_path: str) -> int:
        """Extract timestamp from frame filename"""
        try:
            basename = os.path.basename(frame_path)
            # frame_{timestamp}.jpg
            timestamp = int(basename.replace("frame_", "").replace(".jpg", ""))
            return timestamp
        except:
            return 0

    def _get_event_context_at_timestamp(self, timestamp_ms: int) -> str:
        """Get event context at a specific timestamp"""
        nearby_events = [
            e for e in self.events
            if e.timestamp and abs(e.timestamp * 1000 - timestamp_ms) < 1000
        ]

        if not nearby_events:
            return "No events near this timestamp"

        descriptions = []
        for e in nearby_events[:3]:
            desc = f"{e.action_type}"
            if e.target_text:
                desc += f" on '{e.target_text[:50]}'"
            descriptions.append(desc)

        return "; ".join(descriptions)

    async def _understand_task_phases(
        self,
        frame_analyses: list[FrameAnalysis]
    ) -> list[TaskPhase]:
        """
        Understand the overall task flow and identify phases
        """
        # Build narrative of the task
        narrative_parts = [
            f"Task Goal: {self.task_goal}",
            "",
            "Frame-by-frame analysis:",
        ]

        for i, analysis in enumerate(frame_analyses):
            narrative_parts.append(f"\n--- Frame {i+1} ({analysis.timestamp_ms}ms) ---")
            narrative_parts.append(f"Scene: {analysis.scene_description}")
            narrative_parts.append(f"Intent: {analysis.user_action_intent}")

            if analysis.data_of_interest:
                narrative_parts.append("Marked regions:")
                for data in analysis.data_of_interest:
                    note = f" ({data.get('note')})" if data.get('note') else ""
                    narrative_parts.append(f"  - {data.get('type')}{note}")

            if analysis.related_events:
                narrative_parts.append("Events:")
                for evt in analysis.related_events[:2]:
                    narrative_parts.append(f"  - {evt.get('type')}")

        narrative = "\n".join(narrative_parts)

        # Call LLM to understand phases
        prompt = f"""
Analyze the following task recording and identify distinct phases.

{narrative}

Based on the goal "{self.task_goal}" and the sequence above:
1. What are the distinct phases of this task?
2. Which steps are essential vs. redundant?
3. Are there any repeatable patterns (like iterating through a list)?
4. What data needs to be extracted and when?

Respond in JSON format:
{{
    "phases": [
        {{
            "name": "Phase name (e.g., 'Login', 'Search', 'Extract Data')",
            "start_time_ms": 0,
            "end_time_ms": 5000,
            "description": "What happens in this phase",
            "key_actions": ["action1", "action2"],
            "data_extracted": ["field1", "field2"],
            "is_repeatable": false
        }}
    ],
    "overall_pattern": "Description of the overall workflow",
    "redundant_steps": ["steps that could be removed"],
    "suggested_improvements": ["improvements for robustness"]
}}
"""

        llm = LLMFactory.create_llm()
        messages = [
            SystemMessage(content="You are a task analysis expert for UI automation."),
            HumanMessage(content=prompt),
        ]

        try:
            response = await llm.ainvoke(messages)
            content = response.content

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

            phases = [
                TaskPhase(
                    name=p.get("name", f"Phase {i+1}"),
                    start_time_ms=p.get("start_time_ms", 0),
                    end_time_ms=p.get("end_time_ms", 0),
                    description=p.get("description", ""),
                    key_actions=p.get("key_actions", []),
                    data_extracted=p.get("data_extracted", []),
                    is_repeatable=p.get("is_repeatable", False),
                )
                for i, p in enumerate(result.get("phases", []))
            ]

            # Save phase analysis
            await self._save_intermediate_result("phase_analysis", result)

            return phases

        except Exception as e:
            logger.exception(f"Phase understanding failed: {e}")
            # Fallback: create single phase
            return [TaskPhase(
                name="Main Task",
                start_time_ms=0,
                end_time_ms=self.video_info.get("duration_ms", 0),
                description=self.task_goal,
            )]

    async def _identify_critical_steps(
        self,
        phases: list[TaskPhase]
    ) -> list[CriticalStep]:
        """
        Identify critical steps from phases and events
        """
        steps = []
        step_number = 1

        for phase in phases:
            # Add phase start marker
            steps.append(CriticalStep(
                type="action",
                step_number=step_number,
                description=f"Start: {phase.name}",
                source="dom",
                action_type="comment",
            ))
            step_number += 1

            # Find events in this phase
            phase_events = [
                e for e in self.events
                if e.timestamp and phase.start_time_ms <= e.timestamp * 1000 <= phase.end_time_ms
            ]

            # Convert events to steps
            for event in phase_events:
                step = self._event_to_critical_step(event, step_number)
                if step:
                    steps.append(step)
                    step_number += 1

            # Add extract steps for data marked in this phase
            phase_annotations = [
                ann for ann in self.annotations
                if phase.start_time_ms <= ann.video_timestamp_ms <= phase.end_time_ms
            ]

            for ann in phase_annotations:
                steps.append(CriticalStep(
                    type="extract",
                    step_number=step_number,
                    description=f"Extract: {ann.user_note or 'data'}",
                    source="dom",  # Assume DOM for now, could be detected
                    extract_type="get_text",
                    data_key=f"data_{ann.id}",
                    region={
                        "x": ann.region_x,
                        "y": ann.region_y,
                        "width": ann.region_width,
                        "height": ann.region_height,
                    } if ann.region_x else None,
                ))
                step_number += 1

        return steps

    def _event_to_critical_step(
        self,
        event: TraceEvent,
        step_number: int
    ) -> CriticalStep | None:
        """Convert a TraceEvent to a CriticalStep"""
        # Filter out non-UI events
        if event.action_type in ("node_start", "llm_output", "tool_result"):
            return None

        # Determine source
        source = "dom"
        if event.source == "global":
            source = "mobile" if event.app_name else "desktop"

        # Map action types
        action_type = event.action_type
        if action_type == "click":
            action_type = "click"
        elif action_type == "input":
            action_type = "input"
        elif action_type == "navigate":
            action_type = "navigate"

        payload = {}
        if event.action_payload:
            try:
                payload = json.loads(event.action_payload)
            except:
                pass

        return CriticalStep(
            type="action",
            step_number=step_number,
            description=f"{action_type} on {event.target_text or 'element'}",
            source=source,
            action_type=action_type,
            selector=event.target_selector,
            payload=payload,
        )

    async def _generate_optimized_macro(
        self,
        critical_steps: list[CriticalStep]
    ) -> list[dict]:
        """
        Generate optimized macro script using LLM for intelligent step planning.
        Falls back to rule-based generation if LLM fails.
        """
        # Build context for LLM
        url = self._extract_url_from_goal(self.task_goal)

        # Build annotation context
        annotation_context = []
        for ann in self.annotations:
            annotation_context.append({
                "timestamp_ms": ann.video_timestamp_ms,
                "type": ann.annotation_type,
                "note": ann.user_note,
                "region": {
                    "x": ann.region_x,
                    "y": ann.region_y,
                    "width": ann.region_width,
                    "height": ann.region_height,
                } if ann.region_x else None,
            })

        # Build phase context
        phase_context = []
        for phase in self.task_phases:
            phase_context.append({
                "name": phase.name,
                "description": phase.description,
                "repeatable": phase.is_repeatable,
            })

        prompt = f"""Generate a macro script for the following automation task.

Task Goal: {self.task_goal}

Target URL: {url or "Not specified in goal"}

User Annotations (marked regions of interest on video):
```json
{json.dumps(annotation_context, ensure_ascii=False, indent=2)}
```

Task Phases:
```json
{json.dumps(phase_context, ensure_ascii=False, indent=2)}
```

Generate a JSON array of macro steps. Each step should have:
- step_number: integer sequence
- type: "action" | "extract" | "dump"
- For actions: event_type, source, target_selector, payload, description
- For extract: extract_type, key, source, target_selector OR target_region, payload

Action types: "navigate", "click", "input", "scroll", "wait", "screenshot"
Extract types: "get_text", "get_attribute", "get_inner_html"

Think step by step:
1. What is the first step? (usually navigate to URL if provided)
2. What waits are needed for page loads?
3. What scrolling is needed for infinite scroll pages?
4. What data should be extracted based on annotations?
5. What is the final step? (usually dump to save data)

Respond with ONLY a JSON array:
```json
[
  {{"step_number": 1, "type": "action", "event_type": "navigate", "source": "dom", "target_selector": null, "payload": {{"url": "..."}}, "description": "Navigate to target website"}},
  {{"step_number": 2, "type": "action", "event_type": "wait", "source": "dom", "target_selector": null, "payload": {{"duration": 3}}, "description": "Wait for page to load"}},
  ...
]
```
"""

        try:
            llm = LLMFactory.create_llm()
            messages = [
                SystemMessage(content="You are an expert at generating UI automation macro scripts. Output valid JSON only."),
                HumanMessage(content=prompt),
            ]

            response = await llm.ainvoke(messages)
            content = response.content

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            macro_script = json.loads(content)

            # Validate structure
            if isinstance(macro_script, list) and len(macro_script) > 0:
                logger.info(f"[Job {self.job_id}] Generated macro script with {len(macro_script)} steps via LLM")
                return macro_script

        except Exception as e:
            logger.warning(f"[Job {self.job_id}] LLM macro generation failed: {e}, falling back to rule-based")

        # Fallback: Generate basic macro from critical steps
        return await self._generate_fallback_macro(critical_steps)

    async def _generate_fallback_macro(
        self,
        critical_steps: list[CriticalStep]
    ) -> list[dict]:
        """
        Fallback rule-based macro generation when LLM fails.
        """
        macro = []
        step_number = 1

        # Add navigation if URL is present in goal
        url = self._extract_url_from_goal(self.task_goal)
        if url:
            macro.append({
                "step_number": step_number,
                "type": "action",
                "event_type": "navigate",
                "source": "dom",
                "target_selector": None,
                "payload": {"url": url},
                "description": f"Navigate to {url}",
            })
            step_number += 1

            macro.append({
                "step_number": step_number,
                "type": "action",
                "event_type": "wait",
                "source": "dom",
                "target_selector": None,
                "payload": {"duration": 3},
                "description": "Wait for page to load",
            })
            step_number += 1

        # Add steps from critical_steps
        for step in critical_steps:
            if step.action_type == "comment":
                continue
            if step.type == "action":
                macro.append({
                    "step_number": step_number,
                    "type": "action",
                    "event_type": step.action_type,
                    "source": step.source,
                    "target_selector": step.selector,
                    "payload": step.payload,
                    "description": step.description,
                })
                step_number += 1
            elif step.type == "extract":
                macro.append({
                    "step_number": step_number,
                    "type": "extract",
                    "extract_type": step.extract_type or "get_text",
                    "key": step.data_key,
                    "source": step.source,
                    "target_selector": step.selector,
                    "target_region": step.region,
                    "payload": {},
                })
                step_number += 1

        # Add dump step if we have extract steps
        if any(s.type == "extract" for s in critical_steps):
            macro.append({
                "step_number": step_number,
                "type": "dump",
                "payload": {},
            })

        logger.info(f"[Job {self.job_id}] Generated fallback macro with {len(macro)} steps")
        return macro

    def _extract_url_from_goal(self, goal: str) -> str | None:
        """Extract URL from task goal using regex"""
        import re
        # Match URLs in parentheses or standalone
        url_patterns = [
            r'https?://[^\s\)）]+',  # Standard URLs
            r'\((https?://[^\)]+)\)',  # URLs in parentheses
            r'（(https?://[^）]+)）',  # URLs in Chinese parentheses
        ]
        for pattern in url_patterns:
            match = re.search(pattern, goal)
            if match:
                url = match.group(1) if '(' in pattern else match.group(0)
                return url.rstrip(')）')
        return None

    async def _generate_skill_metadata(
        self,
        phases: list[TaskPhase],
        macro_script: list[dict]
    ) -> GeneratedSkill:
        """
        Generate skill name, description, instructions, etc.
        """
        # Build phase summary
        phase_summary = "\n".join([
            f"- {p.name}: {p.description} ({'repeatable' if p.is_repeatable else 'one-time'})"
            for p in phases
        ])

        # Build macro summary
        action_count = len([m for m in macro_script if m.get("type") == "action"])
        extract_count = len([m for m in macro_script if m.get("type") == "extract"])

        prompt = f"""
Generate a skill configuration based on the following task analysis.

Task Goal: {self.task_goal}

Phases:
{phase_summary}

Macro Script Summary:
- {action_count} action steps
- {extract_count} data extraction steps

Generate:
1. A concise skill name (3-5 words, snake_case)
2. A clear one-sentence description
3. An appropriate namespace (e.g., "web/site-name/task-type")
4. 2-3 trigger patterns (what the user might say to invoke this)
5. A detailed expert skill guide (心法) in Markdown format

The guide should include:
- Mental Model: What's the high-level strategy?
- Contextual Anchors: How to verify we're in the right state?
- Strategic Guidance: Step-by-step with visual cues
- Error Recovery: What to do when things go wrong

Respond in YAML format:
```yaml
name: skill_name_here
description: One sentence describing what this skill does
namespace: web/example/data-extraction
trigger_patterns:
  - "Extract data from example.com"
  - "Get prices from example"
instructions: |
  ## 1. Mental Model
  ...

  ## 2. Contextual Anchors
  ...

  ## 3. Strategic Guidance
  ...

  ## 4. Error Recovery
  ...
```
"""

        llm = LLMFactory.create_llm()
        messages = [
            SystemMessage(content="You are an expert at documenting UI automation skills."),
            HumanMessage(content=prompt),
        ]

        try:
            response = await llm.ainvoke(messages)
            content = response.content

            # Extract YAML
            if "```yaml" in content:
                content = content.split("```yaml")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            import yaml
            result = yaml.safe_load(content)

            # Determine execution mode
            # If all steps are deterministic UI actions, use deterministic mode
            has_llm_decisions = any(
                "decision" in str(m.get("description", "")).lower()
                for m in macro_script
            )
            execution_mode = "agentic" if has_llm_decisions else "deterministic"

            return GeneratedSkill(
                name=result.get("name", "unnamed_skill"),
                description=result.get("description", ""),
                namespace=result.get("namespace", "misc"),
                trigger_patterns=result.get("trigger_patterns", [self.task_goal]),
                instructions=result.get("instructions", ""),
                execution_mode=execution_mode,
                macro_script=macro_script,
            )

        except Exception as e:
            logger.exception(f"Skill metadata generation failed: {e}")

            # Fallback
            return GeneratedSkill(
                name="auto_generated_skill",
                description=self.task_goal,
                namespace="misc",
                trigger_patterns=[self.task_goal],
                instructions=f"# {self.task_goal}\n\nAuto-generated skill.",
                execution_mode="agentic",
                macro_script=macro_script,
            )

    async def _save_intermediate_result(self, key: str, data: Any):
        """Save intermediate result to job record"""
        try:
            async with session_scope() as db:
                stmt = select(SynthesisJob).where(SynthesisJob.id == self.job_id)
                result = await db.execute(stmt)
                job = result.scalar_one()

                if key == "keyframes":
                    job.keyframes = data
                elif key == "frame_analyses":
                    job.frame_analyses = data
                elif key == "phase_analysis":
                    job.phase_analysis = data
                elif key == "extracted_insights":
                    job.extracted_insights = data

                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to save intermediate result {key}: {e}")
