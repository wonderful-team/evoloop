"""技能合成器: map -> 模板实例化 -> 技能候选(草案 §7.8)。

选模板规则(确定性):
  - kind=read  且 risk=ui    -> list_view   (界面查看宏)
  - kind=read  且 risk=data  -> crud_read    (原生数据读)
  - kind=write 且 risk=money -> crud_write   (原生数据写,确认门)
不符通用模板的动作不合成(留给 agent/飞轮)——§7.8 诚实边界:工厂只铺可模板化的 CRUD/查看。
"""
from __future__ import annotations

from . import templates


def pick_template(action: dict):
    kind = action.get("kind")
    risk = action.get("risk_tier")
    if kind == "read" and risk == "ui":
        return templates.list_view
    if kind == "read" and risk == "data":
        return templates.crud_read
    if kind == "write" and risk == "money":
        return templates.crud_write
    return None  # 不符模板 -> 不合成


def synthesize(entity_map: dict) -> list[dict]:
    """对 map 里每个动作选模板、填槽 -> 技能候选(带 source_map_version 版本耦合)。"""
    skills: list[dict] = []
    for action in entity_map["actions"]:
        tmpl = pick_template(action)
        if tmpl is None:
            continue
        skills.append(tmpl(entity_map, action))
    return skills
