"""HITL 常量（叶子模块，仅依赖标准库与枚举定义）。

集中定义 HITL 跨子系统共享的非枚举常量，消除散落各处的硬编码字符串：

- 消息契约值（category / status / action_type）
- 授权门控默认值（default REJECTED / granted_by / TTL）

审批决策令牌（APPROVED/REJECTED/CANCELLED）、双轨请求状态与批量授权状态
等枚举定义见 ``app.core.hitl.types``。
"""

from app.core.hitl.types import HITLDecision

#: HITL 请求消息契约值。与 ``engine.message.category.MessageCategory.HITL_REQUEST``
#: 保持同值：hitl 为叶子模块不依赖 engine，两端一致性由
#: ``tests/unit/core/hitl/test_hitl_contract.py`` 常量断言守护，防止漂移
#: 导致消息分类错乱。
MESSAGE_CATEGORY_HITL_REQUEST = "hitl_request"
MESSAGE_STATUS_WAITING_HUMAN = "waiting_human"
MESSAGE_ACTION_TYPE_HUMAN_REQUEST = "human_request"

#: 授权门控默认值
DEFAULT_DECISION = HITLDecision.REJECTED.value
DEFAULT_GRANTED_BY = "hitl-approval"
DEFAULT_AUTHORIZATION_TTL_DAYS = 7
DEFAULT_BATCH_GRANT_TTL_SECONDS = 300
