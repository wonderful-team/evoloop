"""
Stopword lists for domain term extraction.

No external NLP dependencies. These are static seed lists;
Agent may supplement them dynamically per-project via DomainTermBank.
"""

# English stopwords — covers function words, prepositions, auxiliaries
EN_STOPWORDS: set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd",
    "they'll", "they're", "they've", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll",
    "we're", "we've", "were", "weren't", "what", "what's", "when", "when's",
    "where", "where's", "which", "while", "who", "who's", "whom", "why",
    "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll",
    "you're", "you've", "your", "yours", "yourself", "yourselves",
}

# Chinese stopwords — covers particles, pronouns, auxiliaries, common verbs
ZH_STOPWORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "那", "中", "为", "来", "个", "能", "以", "可", "而", "及", "与",
    "并", "从", "或", "但", "被", "把", "让", "向", "往", "于", "即", "则",
    "所示", "如下", "包括", "基于", "通过", "进行", "使用", "需要", "可以",
    "应该", "必须", "已经", "正在", "将会", "曾经", "可能", "应该", "如何",
    "什么", "哪里", "谁", "为什么", "怎么", "多少", "几", "一些", "许多",
    "所有", "每个", "任何", "其他", "另外", "之间", "之前", "之后", "之外",
    "之上", "之下", "之中", "之时", "之内", "之间",
}

ALL_STOPWORDS: set[str] = EN_STOPWORDS | ZH_STOPWORDS


def is_stopword(token: str) -> bool:
    """Check if a token is a stopword (case-insensitive for English)."""
    return token.lower() in ALL_STOPWORDS
