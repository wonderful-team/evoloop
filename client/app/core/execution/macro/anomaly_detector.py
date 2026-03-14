"""
异常检测器

检测宏执行过程中的环境异常，识别录制环境与执行环境的差异
支持 Vision LLM 智能验证
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.core.execution.macro.verification_models import AnomalyType

logger = logging.getLogger(__name__)


@dataclass
class AnomalyDetectionResult:
    """异常检测结果"""
    is_anomaly: bool
    anomaly_type: AnomalyType
    confidence: float  # 0-1
    details: Dict[str, Any]
    suggested_action: Optional[str] = None


class AnomalyDetector:
    """
    异常检测器

    负责在执行过程中检测环境与预期的差异
    """

    # 坐标漂移阈值（相对坐标差）
    COORDINATE_DRIFT_THRESHOLD = 0.1

    # 文本相似度阈值（用于选择器匹配）
    TEXT_SIMILARITY_THRESHOLD = 0.7

    def __init__(self):
        self.detection_history: List[Dict[str, Any]] = []

    async def detect_pre_execution_anomaly(
        self,
        step: Dict[str, Any],
        current_ui_state: Optional[Dict[str, Any]]
    ) -> AnomalyDetectionResult:
        """
        执行前检测：检查当前状态是否适合执行该步骤

        Returns:
            AnomalyDetectionResult: 检测结果
        """
        if not current_ui_state:
            return AnomalyDetectionResult(
                is_anomaly=False,
                anomaly_type=AnomalyType.UNKNOWN,
                confidence=0.0,
                details={},
                suggested_action="proceed_with_caution"
            )

        # 检测1: 目标元素是否存在
        target_selector = step.get("target_selector")
        if target_selector:
            element_exists = self._check_element_exists(target_selector, current_ui_state)
            if not element_exists:
                # 检查是否是弹窗遮挡
                is_obscured = self._check_if_obscured(target_selector, current_ui_state)
                if is_obscured:
                    return AnomalyDetectionResult(
                        is_anomaly=True,
                        anomaly_type=AnomalyType.ELEMENT_OBSCURED,
                        confidence=0.8,
                        details={"selector": target_selector},
                        suggested_action="dismiss_obstruction"
                    )

                # 检查是否是坐标漂移
                if step.get("payload", {}).get("x") is not None:
                    drift_detected, actual_pos = self._check_coordinate_drift(
                        step, current_ui_state
                    )
                    if drift_detected:
                        return AnomalyDetectionResult(
                            is_anomaly=True,
                            anomaly_type=AnomalyType.COORDINATE_DRIFT,
                            confidence=0.75,
                            details={
                                "expected": step["payload"],
                                "actual": actual_pos
                            },
                            suggested_action="relocate_and_retry"
                        )

                return AnomalyDetectionResult(
                    is_anomaly=True,
                    anomaly_type=AnomalyType.ELEMENT_NOT_FOUND,
                    confidence=0.9,
                    details={"selector": target_selector},
                    suggested_action="use_fallback_selector"
                )

        # 检测2: 纯坐标步骤的坐标漂移
        if step.get("payload", {}).get("x") is not None:
            drift_detected, actual_pos = self._check_coordinate_drift(
                step, current_ui_state
            )
            if drift_detected:
                return AnomalyDetectionResult(
                    is_anomaly=True,
                    anomaly_type=AnomalyType.COORDINATE_DRIFT,
                    confidence=0.7,
                    details={
                        "expected": step["payload"],
                        "actual": actual_pos
                    },
                    suggested_action="verify_target_at_position"
                )

        return AnomalyDetectionResult(
            is_anomaly=False,
            anomaly_type=AnomalyType.UNKNOWN,
            confidence=1.0,
            details={},
            suggested_action="proceed"
        )

    async def detect_post_execution_anomaly(
        self,
        step: Dict[str, Any],
        pre_state: Optional[Dict[str, Any]],
        post_state: Optional[Dict[str, Any]],
        execution_result: Any
    ) -> AnomalyDetectionResult:
        """
        执行后检测：检查执行结果是否符合预期

        Returns:
            AnomalyDetectionResult: 检测结果
        """
        # 检测1: 执行结果是否包含错误
        if execution_result and isinstance(execution_result, str):
            error_keywords = ["error", "failed", "timeout", "not found", "exception"]
            if any(kw in execution_result.lower() for kw in error_keywords):
                return AnomalyDetectionResult(
                    is_anomaly=True,
                    anomaly_type=AnomalyType.ENVIRONMENT_ERROR,
                    confidence=0.85,
                    details={"error_message": execution_result},
                    suggested_action="analyze_and_retry"
                )

        # 检测2: 使用 Vision LLM 智能分析截图（如果可用）- 优先执行，因为更准确
        screenshot_path = post_state.get("screenshot") if post_state else None
        if screenshot_path:
            vision_result = await self.analyze_with_vision_llm(screenshot_path, step)
            if vision_result and vision_result.is_anomaly:
                logger.info(f"[AnomalyDetector] Vision LLM 检测到异常: {vision_result.details.get('issue')}")
                return vision_result

        # 检测3: 状态是否变化（对于应该改变状态的步骤）
        if step.get("type") == "action" and pre_state and post_state:
            state_changed = self._check_state_change(pre_state, post_state)
            if not state_changed:
                # 可能是点击无效，或者页面卡住 - 包含更详细的坐标信息用于修正
                details = {"no_state_change_detected": True}
                payload = step.get("payload", {})
                if payload.get("x") is not None and payload.get("y") is not None:
                    details["current_coords"] = {"x": payload["x"], "y": payload["y"]}
                    details["suggested_fix"] = f"Coordinates ({payload['x']}, {payload['y']}) may be incorrect, try offset correction"

                return AnomalyDetectionResult(
                    is_anomaly=True,
                    anomaly_type=AnomalyType.STATE_MISMATCH,
                    confidence=0.6,
                    details=details,
                    suggested_action="retry_with_adjusted_coordinates"
                )

        # 检测4: 是否进入预期状态（启发式检测）
        # 对于导航/点击操作，检查是否进入了合理的页面
        target_selector = step.get("target_selector")
        event_type = step.get("event_type", "")

        if target_selector and post_state and event_type in ("tap", "click"):
            # 点击后，目标元素应该不再可见（页面已切换）
            element_still_exists = self._check_element_exists(target_selector, post_state)

            if element_still_exists:
                # 点击后目标元素还在，可能是点击无效
                return AnomalyDetectionResult(
                    is_anomaly=True,
                    anomaly_type=AnomalyType.STATE_MISMATCH,
                    confidence=0.7,
                    details={
                        "target_still_visible": True,
                        "target_selector": target_selector,
                        "message": "点击后目标元素仍然可见，可能点击无效"
                    },
                    suggested_action="retry_with_adjusted_coordinates"
                )

        return AnomalyDetectionResult(
            is_anomaly=False,
            anomaly_type=AnomalyType.UNKNOWN,
            confidence=1.0,
            details={},
            suggested_action="continue"
        )

    async def analyze_with_vision_llm(
        self,
        screenshot_path: str,
        step: Dict[str, Any],
        expected_outcome: Optional[str] = None
    ) -> Optional[AnomalyDetectionResult]:
        """
        使用 Vision LLM 智能分析截图，判断执行是否正确

        Args:
            screenshot_path: 截图文件路径
            step: 执行的步骤
            expected_outcome: 预期结果描述

        Returns:
            如果检测到异常返回 AnomalyDetectionResult，否则返回 None
        """
        try:
            from pathlib import Path
            from app.infrastructure.llm.vision import VisionLLMFactory
            from langchain_core.messages import HumanMessage, SystemMessage

            if not Path(screenshot_path).exists():
                return None

            # 初始化 Vision LLM
            llm = VisionLLMFactory.create_vision_llm(temperature=0.2)

            event_type = step.get("event_type", "")
            target = step.get("target_selector", "")
            payload = step.get("payload", {})

            # 构建 prompt
            context = f"执行了 {event_type} 操作"
            if target:
                context += f"，目标: {target}"

            prompt = f"""你是一个智能测试验证助手。请分析这张截图，判断当前页面是否符合预期。

操作上下文: {context}

请回答以下问题:
1. 当前页面是什么？（简要描述）
2. 这是否是执行上述操作后应该出现的页面？
3. 如果不是，出现了什么问题？

请以 JSON 格式返回:
{{
    "is_correct_page": true/false,
    "current_page_description": "当前页面描述",
    "issue_type": "问题类型（如无问题则留空）",
    "suggested_fix": "建议修复方案（如无问题则留空）",
    "confidence": 0.9
}}
"""

            # 创建包含图片的消息
            image_message = VisionLLMFactory.create_image_message(
                image_path=screenshot_path,
                prompt=prompt
            )

            response = await llm.ainvoke([image_message])
            content = response.content

            # 提取 JSON 部分
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if not json_match:
                return None

            result = json.loads(json_match.group())

            is_correct = result.get("is_correct_page", True)
            confidence = result.get("confidence", 0.5)

            if not is_correct and confidence > 0.7:
                return AnomalyDetectionResult(
                    is_anomaly=True,
                    anomaly_type=AnomalyType.STATE_MISMATCH,
                    confidence=confidence,
                    details={
                        "vision_analysis": True,
                        "current_page": result.get("current_page_description"),
                        "issue": result.get("issue_type"),
                        "suggested_fix": result.get("suggested_fix"),
                        "llm_raw_response": content[:500]
                    },
                    suggested_action="retry_with_vision_guidance"
                )

            return None  # 没有检测到异常

        except Exception as e:
            logger.warning(f"[Vision LLM 分析失败]: {e}")
            return None

    def _check_element_exists(
        self,
        selector: str,
        ui_state: Dict[str, Any]
    ) -> bool:
        """检查元素是否存在于当前 UI 状态"""
        elements = ui_state.get("elements", [])

        # 简单的文本包含匹配（实际应使用更复杂的选择器解析）
        for elem in elements:
            elem_text = elem.get("text", "")
            elem_id = elem.get("resource_id", "")
            elem_class = elem.get("class", "")

            if selector in [elem_text, elem_id, elem_class]:
                return True
            if selector in str(elem_text) or selector in str(elem_id):
                return True

        return False

    def _check_if_obscured(
        self,
        selector: str,
        ui_state: Dict[str, Any]
    ) -> bool:
        """检查元素是否被弹窗等遮挡"""
        # 检测是否有弹窗层
        elements = ui_state.get("elements", [])

        # 查找可能的遮挡元素（如弹窗、遮罩层）
        overlay_indicators = ["dialog", "popup", "modal", "overlay", "mask"]
        for elem in elements:
            elem_class = elem.get("class", "").lower()
            if any(ind in elem_class for ind in overlay_indicators):
                # 进一步检查这个弹窗是否遮挡了目标
                return True

        return False

    def _check_coordinate_drift(
        self,
        step: Dict[str, Any],
        ui_state: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, float]]]:
        """
        检查坐标漂移

        Returns:
            (是否漂移, 实际位置)
        """
        payload = step.get("payload", {})
        expected_x = payload.get("x")
        expected_y = payload.get("y")

        if expected_x is None or expected_y is None:
            return False, None

        # 查找预期位置附近的元素
        elements = ui_state.get("elements", [])
        target_selector = step.get("target_selector")

        for elem in elements:
            elem_x = elem.get("x")
            elem_y = elem.get("y")
            elem_text = elem.get("text", "")

            if elem_x is None or elem_y is None:
                continue

            # 如果元素文本匹配选择器，检查坐标差异
            if target_selector and target_selector in str(elem_text):
                drift_x = abs(elem_x - expected_x)
                drift_y = abs(elem_y - expected_y)

                if drift_x > self.COORDINATE_DRIFT_THRESHOLD or \
                   drift_y > self.COORDINATE_DRIFT_THRESHOLD:
                    return True, {"x": elem_x, "y": elem_y}

        return False, None

    def _check_state_change(
        self,
        pre_state: Dict[str, Any],
        post_state: Dict[str, Any]
    ) -> bool:
        """检查 UI 状态是否有显著变化"""
        # 简化的状态变化检测
        pre_elements = set(str(e) for e in pre_state.get("elements", []))
        post_elements = set(str(e) for e in post_state.get("elements", []))

        # 如果元素集合有变化，认为状态变了
        if pre_elements != post_elements:
            return True

        # 检查当前活动页面/窗口
        pre_activity = pre_state.get("current_activity")
        post_activity = post_state.get("current_activity")

        # 如果任一 activity 为空，无法判断，假设状态没变（让其他检测逻辑处理）
        if not pre_activity or not post_activity:
            return False

        if pre_activity != post_activity:
            return True

        return False

    def detect_flow_anomaly(
        self,
        expected_next_step: Dict[str, Any],
        actual_state: Dict[str, Any],
        execution_history: List[Dict[str, Any]]
    ) -> AnomalyDetectionResult:
        """
        检测流程异常：当前状态是否与预期的下一步匹配

        用于检测意外流程分叉
        """
        # 检测是否出现了预期外的页面
        current_activity = actual_state.get("current_activity", "")
        expected_activity = expected_next_step.get("payload", {}).get("package_name")

        if expected_activity and current_activity != expected_activity:
            return AnomalyDetectionResult(
                is_anomaly=True,
                anomaly_type=AnomalyType.UNEXPECTED_FLOW,
                confidence=0.8,
                details={
                    "expected_activity": expected_activity,
                    "actual_activity": current_activity
                },
                suggested_action="handle_unexpected_flow"
            )

        return AnomalyDetectionResult(
            is_anomaly=False,
            anomaly_type=AnomalyType.UNKNOWN,
            confidence=1.0,
            details={}
        )
