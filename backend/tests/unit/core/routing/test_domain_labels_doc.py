"""域词汇表文档同步契约（2026-09-18）。

锁定 `docs/backend/docs/capability-packages-refactor.md`「域词汇表」小节与 L1 分类器
模型产物 `models/domain_classifier/labels.json` 的标签集一致：
模型重训导致标签集变化时本测试变红，提醒更新文档——文档永不静默过期。
"""

from __future__ import annotations

import json
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
LABELS_PATH = _BACKEND_ROOT / "models" / "domain_classifier" / "labels.json"
def _find_doc_path() -> Path:
    candidates = [
        _BACKEND_ROOT / "docs" / "capability-packages-refactor.md",
        _BACKEND_ROOT.parent.parent / "docs" / "backend" / "docs" / "capability-packages-refactor.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


DOC_PATH = _find_doc_path()


def _model_labels() -> set[str]:
    data = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    return set(data["id2name"].values())


def _doc_section() -> str:
    """「### 域词汇表」小节正文（到下一个同级标题为止）。"""
    doc = DOC_PATH.read_text(encoding="utf-8")
    return doc.split("### 域词汇表", 1)[-1].split("\n### ", 1)[0]


def test_labels_file_exists_and_nonempty():
    labels = _model_labels()
    assert "ambiguous" in labels and len(labels) >= 20


def test_domain_labels_doc_synced():
    """文档「域词汇表」小节必须以反引号形式列出当前模型的全部标签。"""
    labels = _model_labels()
    section = _doc_section()
    missing = sorted(label for label in labels if f"`{label}`" not in section)
    assert not missing, (
        f"文档「域词汇表」缺少模型标签：{missing}——"
        "labels.json 已变化（模型重训？），请同步更新 docs 小节"
    )
