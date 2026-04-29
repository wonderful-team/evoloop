"""
Cross-language sentiment markers for confidence scoring.

These are NOT domain-specific terms — they express universal linguistic patterns
(obligation, permission, uncertainty, hedging) that apply across all fields.
Stored as static data (not Agent-maintained) because they represent grammatical
functions, not learnable domain vocabulary.

Usage:
    from app.core.memory.sentiment_markers import ACTION_MARKERS, VAGUE_MARKERS
    en_action = ACTION_MARKERS["en"]
    zh_vague = VAGUE_MARKERS["zh"]
"""

import re

# ── Actionability markers ─────────────────────────────────────────────
# Words/phrases that indicate imperative, mandatory, or recommended actions.
# English: use \bword\b boundary matching to avoid false positives
#          (e.g. "can" matching "scan", "cancel", "candidate")
# Chinese: substring match is generally safe for 2+ char words

ACTION_MARKERS: dict[str, set[str]] = {
    "en": {
        # Core modals / auxiliaries
        "must", "should", "shall", "ought to", "need to", "have to",
        "required to", "be required to",
        # Absolute frequency
        "always", "never", "constantly", "consistently", "invariably",
        "unfailingly", "without exception", "under no circumstances",
        # Strength adjectives
        "imperative", "mandatory", "compulsory", "obligatory",
        "essential", "critical", "vital", "crucial", "necessary",
        # Directive verbs
        "ensure", "guarantee", "enforce",
        "prohibit", "forbid", "ban", "restrict", "prevent", "avoid",
        "refrain from",
        # Negated directives
        "do not", "don't", "cannot", "can't", "will not", "won't",
        "shall not", "shan't", "must not", "mustn't",
        # Assurance / instruction patterns
        "be sure to", "make sure to", "see to it that",
        "it is necessary to", "it is essential to",
        "it is imperative that", "it is mandatory to",
    },
    "zh": {
        # 强制性
        "必须", "务必", "务须", "务求", "定要", "定须",
        "应当", "应该", "需要",
        # 绝对性
        "总是", "一直", "始终", "永远", "历来", "历来都",
        "从来不", "绝不", "决不", "切莫", "切勿", "切忌",
        # 禁止性
        "禁止", "严禁", "不准", "不得", "不许", "不可", "不能", "不要",
        "阻止", "制止", "遏止", "杜绝",
        # 确保性
        "确保", "保证", "保障", "确认", "核实", "查证",
        # 规定性
        "强制", "要求", "规定", "限定", "限于", "限于", "限定为",
        "限定在", "限定为", "仅限于",
        # 避免性
        "避免", "防止", "防范", "预防", "提防", "当心", "注意",
        "以免", "免得", "省得",
        # 建议性
        "建议", "提倡", "倡导", "倡议", "推荐", "主张", "呼吁", "号召",
    },
}

# ── Vagueness / hedging markers ───────────────────────────────────────
# Words/phrases that indicate uncertainty, speculation, or imprecision.

VAGUE_MARKERS: dict[str, set[str]] = {
    "en": {
        # Probability adverbs
        "maybe", "perhaps", "possibly", "potentially", "presumably",
        "probably", "likely", "apparently", "seemingly", "ostensibly",
        # Indefinite pronouns / placeholders
        "somehow", "somewhat", "somewhere", "sometime", "someday",
        "someone", "something", "somebody", "someone",
        # Weak modals
        "might", "could", "may",  # NOTE: "can" excluded — too many false positives
        # Tentative verbs
        "guess", "suppose", "assume", "speculate", "conjecture",
        "hypothesize", "theorize", "suspect",
        # Uncertainty adjectives
        "uncertain", "unsure", "doubtful", "questionable",
        "debatable", "arguable", "disputable", "controversial",
        # Vague descriptors
        "vague", "ambiguous", "unclear", "fuzzy", "hazy", "cloudy",
        "murky", "obscure",
        # Approximation
        "roughly", "approximately", "about", "around", "circa",
        "more or less", "give or take",
        # Hedging phrases
        "kind of", "sort of", "type of",
        "tend to", "inclined to", "prone to", "apt to", "liable to",
        "not sure", "not certain", "not clear", "not definite",
        "not specific", "not precise", "not exact", "not accurate",
    },
    "zh": {
        # 可能性
        "也许", "或许", "可能", "大概", "大约", "约莫",
        "差不多", "几乎", "险些", "差一点",
        "不一定", "不见得", "未必", "难说", "不好说",
        # 不确定性
        "不知", "不确定", "不肯定", "不清楚", "不明", "不详",
        "模糊", "含糊", "暧昧", "模棱", "模棱两可", "似是而非",
        "不明朗", "不透明", "不确切", "不精准",
        # 推测性
        "似乎", "好像", "仿佛", "貌似", "看起来", "看上去", "听起来",
        "估计", "推测", "猜测", "揣测", "臆测",
        "设想", "假定", "假如", "假设", "假若", "倘使", "倘若",
        # 不定指
        "某种", "某些", "某个", "某些方面", "一定程度上", "某种程度上",
        "或多或少", "时好时坏", "忽冷忽热", "摇摆不定", "难以确定",
        # 尝试性
        "尽量", "尽可能", "力图", "争取", "试着", "尝试", "考虑",
        "琢磨", "研究研究", "商量商量", "讨论讨论",
        # 待定性
        "待定", "待议", "待查", "待确认", "待核实", "待进一步",
        "有待", "尚需", "有待于", "有待商榷",
        # 范围模糊
        "左右", "上下", "前后", "附近", "周围", "一带", "一片",
        "等等", "之类的", "什么的", "等等",
    },
}


def build_action_pattern(words: set[str]) -> str:
    """Build a regex alternation pattern for English action words (with word boundaries)."""
    escaped = [re.escape(w) for w in sorted(words, key=len, reverse=True)]
    return r'\b(?:' + '|'.join(escaped) + r')\b'


def build_vague_pattern(words: set[str]) -> str:
    """Build a regex alternation pattern for English vague words (with word boundaries)."""
    escaped = [re.escape(w) for w in sorted(words, key=len, reverse=True)]
    return r'\b(?:' + '|'.join(escaped) + r')\b'


# Pre-compiled English patterns (module-level, for performance)
import re as _re

_ACTION_PATTERN_EN = _re.compile(build_action_pattern(ACTION_MARKERS["en"]), _re.IGNORECASE)
_VAGUE_PATTERN_EN = _re.compile(build_vague_pattern(VAGUE_MARKERS["en"]), _re.IGNORECASE)
