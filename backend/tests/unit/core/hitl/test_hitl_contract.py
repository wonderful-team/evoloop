"""hitl 与 engine.message 之间消息契约常量的一致性守护。

``hitl/constants.py`` 刻意不 import engine（保持叶子模块界限），两端同值
在此以测试期断言承诺，防止漂移导致消息分类错乱。
"""

from app.core.engine.message.category import MessageCategory
from app.core.hitl.constants import MESSAGE_CATEGORY_HITL_REQUEST


def test_hitl_request_message_category_aligned():
    assert MESSAGE_CATEGORY_HITL_REQUEST == MessageCategory.HITL_REQUEST.value
