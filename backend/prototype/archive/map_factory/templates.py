"""技能模板库(最小集)。

草案 §7.8: 技能合成 = 模板库 × 地图数据实例化,**不是 LLM 现场生成代码**。
实例化是确定性的——用 map 结构化数据填模板槽位,产出可校验的技能。

三模板:
  - list_view:  界面查看/定位宏(ui 级)   -> 确定性 L1 回放
  - crud_read:  原生数据读(data 级)      -> 确定性 L1 回放(observe 族)
  - crud_write: 原生数据写(money 级)     -> 强制确认门(A2): 执行确定、触发要确认
"""
from __future__ import annotations

from .families import derive_family  # noqa: F401  (模板内聚,便于外部复用)


def _route_for(entity_map: dict, action_name: str) -> dict:
    for r in entity_map["routes"]:
        if r["source_action"] == action_name:
            return r
    raise KeyError(f"no route for action {action_name}")


def list_view(entity_map: dict, action: dict) -> dict:
    """界面查看宏: 开列表 URL -> 搜索 -> 读结果表。坐标一律归一化,element_name 优先。"""
    route = _route_for(entity_map, action["name"])
    entity = entity_map["entity"]
    steps = [
        {"step_number": 1, "type": "action", "event_type": "open_url", "source": "dom",
         "payload": {"url": route["url"]}},
        {"step_number": 2, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 1}},
        {"step_number": 3, "type": "action", "event_type": "click", "source": "dom",
         "target_selector": "搜索框", "payload": {"x": 0.5, "y": 0.1}},
        {"step_number": 4, "type": "action", "event_type": "type_text", "source": "dom",
         "payload": {"text": "{{query}}"}},
        {"step_number": 5, "type": "action", "event_type": "key_press", "source": "dom",
         "payload": {"key": "return"}},
        {"step_number": 6, "type": "extract", "event_type": "get_text", "source": "dom",
         "target_selector": "结果表格", "payload": {}},
    ]
    return {
        "name": f"查看{{query}}{entity}",
        "skill_form": "macro",
        "execution_mode": "deterministic",
        "risk_tier": action["risk_tier"],
        "trigger_patterns": [f"查看{{{{query}}}}{entity}", "找{{query}}", f"定位{{{{query}}}}{entity}"],
        "parameters": [{"name": "query", "type": "string", "required": True, "description": "商品名/货号"}],
        "macro_script": steps,
        "source_map_version": entity_map["map_version"],
    }


def crud_read(entity_map: dict, action: dict) -> dict:
    """原生数据读: SELECT。data 级,纯确定性 L1 回放(无人值守)。family=observe。"""
    table = action["touches_tables"][0]
    return {
        "name": f"查{{query}}{entity_map['entity']}价格",
        "skill_form": "native_read",
        "execution_mode": "deterministic",
        "risk_tier": action["risk_tier"],
        "family": "observe",
        "trigger_patterns": ["查{{query}}价格", "{{query}}多少钱", "{{query}}现价多少"],
        "parameters": [{"name": "query", "type": "string", "required": True}],
        "read_spec": {
            "table": table,
            "select": ["price"],
            "filter": {"goods_name": "{{query}}"},
            "rule": action["business_rule"],
        },
        "source_map_version": entity_map["map_version"],
    }


def crud_write(entity_map: dict, action: dict) -> dict:
    """原生数据写: UPDATE。money 级 -> 强制确认门(A2)。参数只吃绝对值(§10.3/§11.3)。"""
    table = action["touches_tables"][0]
    return {
        "name": f"改{{query}}{entity_map['entity']}价格",
        "skill_form": "native_write",
        "execution_mode": "deterministic",
        "risk_tier": action["risk_tier"],
        "family": "act",
        "requires_confirmation": True,  # money 强制确认门(§10.1/A2)
        "trigger_patterns": ["改{{query}}价格为{{new_price}}", "把{{query}}改成{{new_price}}元"],
        "parameters": [
            {"name": "query", "type": "string", "required": True},
            {"name": "new_price", "type": "number", "required": True, "description": "绝对值,禁止相对表达式"},
        ],
        "write_spec": {
            "table": table,
            "pk": action["pk"],
            "set": {"price": "{{new_price}}"},
            "preconditions": ["admin_session"],
            "rule": action["business_rule"],
        },
        "source_map_version": entity_map["map_version"],
    }
