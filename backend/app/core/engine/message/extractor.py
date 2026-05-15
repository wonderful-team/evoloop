"""
AttachmentExtractor — AI 回复产出物自动提取器。

职责：
1. 扫描 AI 回复文本，检测代码块类型（echarts/mermaid/map/artifact）和文件路径（uploads/）
2. 将检测结果结构化为 ReferenceBlock 数据，自动挂载到 AI 消息的引用列表
3. 无副作用：仅做数据提取，不操作数据库或文件系统

为什么需要这个？
- AI 生成文件或图表后，仅在文本中提及，前端无法渲染附件卡片
- 通过正则扫描，将隐式的产出物显式化为 MessageReference 记录
- 作为提示词协议的"兜底"机制，即使 AI 未按规范声明，也能自动检测
"""

import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# 图片扩展名（用于区分 file 和 image 类型）
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
# 音频扩展名
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}

# 代码块类型 → artifact_type 映射
ARTIFACT_CODE_BLOCK_TYPES = {
    "echarts": "echarts",
    "mermaid": "mermaid",
    "map": "map",
    "artifact": "html",
    "html": "html",
    "react": "react",
}

# 正则：匹配 uploads/ 路径（如 uploads/report.xlsx 或 /api/.../raw?path=uploads/...）
_PATH_PATTERN = re.compile(r"uploads/[\w\-./]+\.\w+")

# 正则：匹配代码块语言标识符（```echarts ... ```）
_CODE_BLOCK_PATTERN = re.compile(r"```(\w+)\s*\n(.*?)```", re.DOTALL)

# 正则：匹配引用标记 @[type:id]（如 @[message:uuid] 或 @[skill:skill_id]）
_REFERENCE_PATTERN = re.compile(r"@\[(message|skill):([\w\-]+)\]")


class AttachmentExtractor:
    """
    扫描 AI 回复内容，自动提取产出物为 ReferenceBlock 数据。
    """

    def extract_from_ai_response(
        self,
        content: str,
        thread_id: str,
        project_id: int = 0,
    ) -> list[dict[str, Any]]:
        """
        从 AI 回复文本中提取所有附件引用。

        Args:
            content: AI 回复的原始文本
            thread_id: 当前会话 ID（用于构造附件 URL）
            project_id: 当前项目 ID（用于构造附件 URL）

        Returns:
            list of ReferenceBlock-compatible dicts，可直接传入 repo.persist(references=...)
        """
        if not content:
            return []

        references: list[dict[str, Any]] = []
        seen_targets: set[str] = set()  # 去重：同一资源不重复注册

        # --- 1. 扫描代码块类型（Artifact）---
        for match in _CODE_BLOCK_PATTERN.finditer(content):
            lang = match.group(1).lower()
            block_content = match.group(2).strip()

            artifact_type = ARTIFACT_CODE_BLOCK_TYPES.get(lang)
            if not artifact_type:
                continue

            artifact_id = str(uuid.uuid4())
            key = f"artifact:{lang}:{hash(block_content)}"
            if key in seen_targets:
                continue
            seen_targets.add(key)

            references.append({
                "id": str(uuid.uuid4()),
                "type": "artifact",
                "target_id": artifact_id,
                "target_name": f"{lang.capitalize()} 图表",
                "metadata": {
                    "artifact_type": artifact_type,
                    "content": block_content[:500],  # 存储前 500 字符作为预览
                },
            })
            logger.debug(f"[AttachmentExtractor] Detected artifact: {artifact_type} ({artifact_id})")

        # --- 2. 扫描文件路径（File / Image）---
        for match in _PATH_PATTERN.finditer(content):
            path = match.group(0)
            if path in seen_targets:
                continue
            seen_targets.add(path)

            # 按扩展名区分类型
            lower_path = path.lower()
            ext = "." + lower_path.rsplit(".", 1)[-1] if "." in lower_path else ""

            if ext in IMAGE_EXTENSIONS:
                ref_type = "image"
            elif ext in AUDIO_EXTENSIONS:
                ref_type = "audio"
            else:
                ref_type = "file"

            filename = path.rsplit("/", 1)[-1]
            preview_url = f"/api/v1/projects/{project_id}/files/raw?path={path}&thread_id={thread_id}"

            references.append({
                "id": str(uuid.uuid4()),
                "type": ref_type,
                "target_id": preview_url,
                "target_name": filename,
                "metadata": {
                    "filename": filename,
                    "source_path": path,
                },
            })
            logger.debug(f"[AttachmentExtractor] Detected {ref_type}: {filename}")

        # --- 3. 扫描引用标记（Message / Skill）---
        for match in _REFERENCE_PATTERN.finditer(content):
            ref_type = match.group(1)
            target_id = match.group(2)
            
            key = f"ref:{ref_type}:{target_id}"
            if key in seen_targets:
                continue
            seen_targets.add(key)

            target_name = "引用消息" if ref_type == "message" else "引用技能"
            
            references.append({
                "id": str(uuid.uuid4()),
                "type": ref_type,
                "target_id": target_id,
                "target_name": f"{target_name} ({target_id[:8]})",
                "metadata": {
                    "source_id": target_id,
                    "is_auto_extracted": True
                },
            })
            logger.debug(f"[AttachmentExtractor] Detected {ref_type} reference: {target_id}")

        if references:
            logger.info(
                f"[AttachmentExtractor] Extracted {len(references)} reference(s) "
                f"from AI response (thread={thread_id})"
            )

        return references


# 全局单例，无状态可复用
attachment_extractor = AttachmentExtractor()
