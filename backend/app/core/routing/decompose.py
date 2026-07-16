"""Multi-intent decomposition for the voice router (方案甲 orchestration).

A cheap connector heuristic gates the LLM call: single-intent text (the common
case) never pays for decomposition. The LLM emits an ordered intent list with
optional dependency markers:

    {"intents": [
        {"text": "查铰链的价格"},
        {"text": "把铰链的价格降10%", "depends_on": 1,
         "param_exprs": {"new_value": "{{1.value}} * 0.9"}}
    ]}

`param_exprs` are NOT evaluated here — the deterministic resolver turns them
into absolute values at execution time, once intent 1's data exists.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from app.core.routing._errors import ROUTE_EXCEPTIONS

logger = logging.getLogger(__name__)

_CONNECTOR_RE = re.compile(
    r"然后|接着|然后再|再把|顺便|以及|还要|并且|同时|另外|之后|随后|先.+再"
    r"|\band\s+then\b|\bthen\b\s*,?|\band\s+also\b",
    re.IGNORECASE,
)
_PARAM_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_REF_RE = re.compile(r"\{\{\s*(\d+)\.([a-zA-Z0-9_\-\.]+)\s*\}\}")

_MAX_INTENTS = 4


@dataclass
class Intent:
    text: str
    depends_on: int | None = None
    param_exprs: dict[str, str] = field(default_factory=dict)


def _norm_depends_on(raw, index: int) -> int | None:
    """Small models emit depends_on as int / [int] / {"i": int} / "1" / []."""
    if raw is None or raw == [] or raw == "":
        return None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
        if raw is None:
            return None
    if isinstance(raw, dict):
        raw = raw.get("i") or raw.get("intent") or raw.get("index")
    try:
        dep = int(raw)
    except (TypeError, ValueError):
        return -1  # 非法形态 -> 整个拆分作废
    return dep if 1 <= dep < index else -1


def _parse_intents(raw: str) -> list[Intent] | None:
    """Validate the LLM's JSON; any structural problem -> None (single path)."""
    text = raw.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    items = obj.get("intents")
    if not isinstance(items, list) or not (2 <= len(items) <= _MAX_INTENTS):
        return None

    intents: list[Intent] = []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            return None
        depends = _norm_depends_on(item.get("depends_on"), i)
        if depends == -1:
            return None
        exprs = item.get("param_exprs") or {}
        if not isinstance(exprs, dict):
            return None
        for name, expr in exprs.items():
            if not _PARAM_NAME_RE.match(name) or not isinstance(expr, str):
                return None
            for ref_idx, _key in _REF_RE.findall(expr):
                if not (1 <= int(ref_idx) < i):
                    return None
        intents.append(
            Intent(text=item["text"].strip(), depends_on=depends, param_exprs=exprs)
        )
    if any(not it.text for it in intents):
        return None
    return intents


_DECOMPOSE_PROMPT = """你是语音指令的意图拆分器。把用户指令拆成按顺序执行的子意图列表。

规则：
1. 每个子意图是一句独立、完整、可执行的指令（补全省略的宾语）。
2. "告诉我 / 给我看看 / 说一下"这类汇报尾巴不是意图，不要拆出来。
3. 若某子意图的参数依赖前序意图的执行结果（如"降价10%"依赖刚查到的价格）：
   - "depends_on" 填前序意图的序号（从 1 开始的整数，不要数组、不要对象）
   - "param_exprs" 给出参数表达式，写操作的参数名固定用 new_value，
     引用形式 {{{{i.键}}}}（i 为序号，键如 value/price/stock），
     表达式只允许数值运算（+ - * / 和 round/min/max/abs）。
4. 不依赖前序结果的意图：depends_on 填 null，不要 param_exprs。
5. 只输出 JSON，不要输出思考过程：{{"intents": [...]}}，最多 {max_n} 个。
6. 忠实原句：不得添加原指令没有提到的字段或条件（用户只说"查一下X"，子意图就写"查询X的信息"，不得写成"查询X的价格/库存"）。

示例输入：查铰链价格，然后把它降价10%
示例输出：{{"intents": [{{"text": "查询铰链的价格", "depends_on": null}}, {{"text": "把铰链的价格降低10%", "depends_on": 1, "param_exprs": {{"new_value": "round({{{{1.value}}}} * 0.9, 2)"}}}}]}}

用户指令：{text}"""


async def decompose(text: str) -> list[Intent] | None:
    """Split an instruction into ordered intents, or None for single-intent.

    The connector heuristic runs first; the LLM is only consulted when the
    text looks compound. Any failure degrades to None (today's single path).
    """
    if not _CONNECTOR_RE.search(text):
        return None

    from app.core.routing.router import _create_route_llm

    prompt = _DECOMPOSE_PROMPT.format(text=text, max_n=_MAX_INTENTS)
    intents: list[Intent] | None = None
    for attempt in range(2):
        try:
            llm = await _create_route_llm()
            ai_msg = await llm.ainvoke([{"role": "user", "content": prompt}])
            raw = getattr(ai_msg, "content", "") or ""
            if not raw.strip():
                # qwen 系偶发 content 为空、正文落在 reasoning_content
                raw = (
                    getattr(ai_msg, "additional_kwargs", {}).get("reasoning_content")
                    or ""
                )
        except ROUTE_EXCEPTIONS as exc:
            logger.info("[decompose] LLM unavailable, single path: %s", exc)
            return None

        intents = _parse_intents(raw)
        if intents is not None:
            break
        logger.info(
            "[decompose] unparseable LLM output (attempt %d): %r",
            attempt + 1,
            raw[:200],
        )
    if intents is None:
        logger.info("[decompose] falling back to single path")
        return None
    logger.info(
        "[decompose] %d intents: %s",
        len(intents),
        [f"{i.text}(dep={i.depends_on})" for i in intents],
    )
    return intents
