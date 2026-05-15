"""
AttachmentExtractor — AI 回复产出物自动提取器。

职责：
1. 扫描 AI 回复文本，检测代码块类型（echarts/mermaid/map/artifact/react）和引用语法（[REF: ...] 或 uploads/）
2. 将检测结果结构化为 ReferenceBlock 数据，自动挂载到 AI 消息的引用列表
3. 无副作用：仅做数据提取，不操作数据库或文件系统
"""

import logging
import re
import uuid
import json
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

# 正则：匹配 uploads/ 路径（如 uploads/report.xlsx）
_PATH_PATTERN = re.compile(r"uploads/[\w\-./]+\.\w+")

# 正则：匹配代码块语言标识符（```echarts ... ```）
_CODE_BLOCK_PATTERN = re.compile(r"```(\w+)\s*\n(.*?)```", re.DOTALL)

# 正则：匹配引用标记 @[type:id]（如 @[message:uuid] 或 @[skill:skill_id]）
_REFERENCE_PATTERN = re.compile(r"@\[(message|skill):([\w\-]+)\]")

# 正则：匹配标准引用标记 [REF: type=TYPE id=ID name=NAME]
_REF_TAG_PATTERN = re.compile(r"\[REF:\s+type=(\w+)\s+(?:id|path)=([\w\-./]+)(?:\s+name=[\"']?([^\]\"']+)[\"']?)?\]")

# 正则：匹配 JSON 风格的 artifact 块
_JSON_BLOCK_PATTERN = re.compile(r"```json\s*\n?(.*?)\n?```", re.DOTALL)


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
        """
        if not content:
            return []

        references: list[dict[str, Any]] = []
        seen_targets: set[str] = set()  # 去重：统一资源标识符

        # --- 1. 扫描代码块类型（Markdown Artifacts）---
        for match in _CODE_BLOCK_PATTERN.finditer(content):
            lang = match.group(1).lower()
            block_content = match.group(2).strip()

            artifact_type = ARTIFACT_CODE_BLOCK_TYPES.get(lang)
            if not artifact_type:
                continue

            # Key for deduplication: type + content hash
            key = f"artifact:{lang}:{hash(block_content)}"
            if key in seen_targets:
                continue
            seen_targets.add(key)

            artifact_id = str(uuid.uuid4())
            references.append({
                "id": str(uuid.uuid4()),
                "type": "artifact",
                "target_id": artifact_id,
                "target_name": f"{lang.capitalize()} 组件",
                "metadata": {
                    "artifact_type": artifact_type,
                    "content": block_content[:1000],
                },
            })

        # --- 2. 扫描 JSON 风格的 Blocks (Artifacts) ---
        for match in _JSON_BLOCK_PATTERN.finditer(content):
            try:
                data = json.loads(match.group(1).strip())
                if data.get("type") == "artifact":
                    a_type = data.get("category") or data.get("artifact_type")
                    if a_type:
                        # Key for deduplication: artifact + type + data hash
                        content_str = json.dumps(data.get("data", {}), sort_keys=True)
                        key = f"artifact:{a_type}:{hash(content_str)}"
                        if key in seen_targets:
                            continue
                        seen_targets.add(key)

                        references.append({
                            "id": str(uuid.uuid4()),
                            "type": "artifact",
                            "target_id": str(uuid.uuid4()),
                            "target_name": f"{a_type.capitalize()} 组件",
                            "metadata": {
                                "artifact_type": a_type,
                                "content": content_str,
                            },
                        })
            except (json.JSONDecodeError, TypeError):
                continue

        # --- 3. 扫描标准引用标记 [REF: ...] ---
        for match in _REF_TAG_PATTERN.finditer(content):
            ref_type = match.group(1)
            target_id = match.group(2)
            target_name = match.group(3) or target_id.rsplit("/", 1)[-1]

            # Standardized key: type + target_id
            key = f"ref:{ref_type}:{target_id}"
            if key in seen_targets:
                continue
            seen_targets.add(key)

            references.append({
                "id": str(uuid.uuid4()),
                "type": ref_type,
                "target_id": target_id,
                "target_name": target_name,
                "metadata": {
                    "source_id": target_id,
                    "is_standard_ref": True
                },
            })

        # --- 4. 扫描文件路径（Legacy uploads/ 路径）---
        for match in _PATH_PATTERN.finditer(content):
            path = match.group(0)
            
            # 按扩展名推断类型
            lower_path = path.lower()
            ext = "." + lower_path.rsplit(".", 1)[-1] if "." in lower_path else ""
            if ext in IMAGE_EXTENSIONS:
                ref_type = "image"
            elif ext in AUDIO_EXTENSIONS:
                ref_type = "audio"
            else:
                ref_type = "file"

            # Check standardized key to avoid duplicate with [REF]
            key = f"ref:{ref_type}:{path}"
            if key in seen_targets:
                continue
            seen_targets.add(key)

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

        # --- 5. 扫描 Legacy 引用标记 @[type:id] ---
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

        return references


# 全局单例
attachment_extractor = AttachmentExtractor()
