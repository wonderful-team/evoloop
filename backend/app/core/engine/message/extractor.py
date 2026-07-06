"""
AttachmentExtractor — AI 回复产出物自动提取器。

职责：
1. 扫描 AI 回复文本，检测代码块类型（echarts/mermaid/map/artifact/react）和标准 Markdown 链接（[链接](file://...) / uploads/...）
2. 将检测结果结构化为 MessageReference 数据，自动挂载到 AI 消息的引用列表
3. 无副作用：仅做数据提取，不操作数据库或文件系统
"""

import json
import logging
import re
from typing import Any

from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)

# 图片扩展名（用于区分 file 和 image 类型）
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
# 音频扩展名
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}
# 视频扩展名
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".m4v", ".mkv"}

# 代码块类型 → artifact_type 映射
ARTIFACT_CODE_BLOCK_TYPES = {
    "mermaid": "mermaid",
    "map": "map",
    "artifact": "html",
    "html": "html",
    "react": "react",
}

# 正则：匹配代码块语言标识符（```echarts ... ```）
_CODE_BLOCK_PATTERN = re.compile(r"```(\w+)\s*\n(.*?)```", re.DOTALL)

# 正则：匹配标准 Markdown 链接和图片：[text](file:///path) 或 ![text](uploads/...)
_MD_LINK_PATTERN = re.compile(r"!?\[([^\]]+)\]\((file://[^\)]+|/[^\)]+|\./[^\)]+|uploads/[^\)]+)\)")

# 正则：匹配 JSON 风格的 artifact 块
_JSON_BLOCK_PATTERN = re.compile(r"```json\s*\n?(.*?)\n?```", re.DOTALL)


class AttachmentExtractor:
    """
    扫描 AI 回复内容，自动提取产出物为 MessageReference 数据。
    """

    def extract_from_ai_response(
        self,
        content: str,
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

            artifact_id = gen_uuid()
            references.append({
                "id": gen_uuid(),
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
                    a_type = data.get("artifact_type")
                    if a_type:
                        # Key for deduplication: artifact + type + data hash
                        content_str = json.dumps(data.get("data", {}), sort_keys=True)
                        key = f"artifact:{a_type}:{hash(content_str)}"
                        if key in seen_targets:
                            continue
                        seen_targets.add(key)

                        references.append({
                            "id": gen_uuid(),
                            "type": "artifact",
                            "target_id": gen_uuid(),
                            "target_name": f"{a_type.capitalize()} 组件",
                            "metadata": {
                                "artifact_type": a_type,
                                "content": content_str,
                            },
                        })
            except (json.JSONDecodeError, TypeError):
                continue

        # --- 3. 扫描标准 Markdown 链接 ---
        for match in _MD_LINK_PATTERN.finditer(content):
            target_name = match.group(1).strip()
            target_id = match.group(2).strip()

            # 按扩展名推断类型
            lower_path = target_id.lower()
            ext = "." + lower_path.rsplit(".", 1)[-1] if "." in lower_path else ""
            if ext in IMAGE_EXTENSIONS:
                ref_type = "image"
            elif ext in AUDIO_EXTENSIONS:
                ref_type = "audio"
            elif ext in VIDEO_EXTENSIONS:
                ref_type = "video"
            else:
                ref_type = "file"

            # 移除 file:// 前缀，方便统一处理
            clean_target_id = target_id.replace("file://", "")

            # Standardized key: type + target_id
            key = f"ref:{ref_type}:{clean_target_id}"
            if key in seen_targets:
                continue
            seen_targets.add(key)

            references.append({
                "id": gen_uuid(),
                "type": ref_type,
                "target_id": target_id,
                "target_name": target_name,
                "metadata": {
                    "source_path": clean_target_id,
                    "is_local_file": True,
                    "is_standard_md_link": True
                },
            })

        return references


# 全局单例
attachment_extractor = AttachmentExtractor()
