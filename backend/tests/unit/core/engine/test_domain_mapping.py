"""域映射（domain_mapping）单元测试：通用域 → intent/modules。

宿主/项目声明域（如 mall_ops）的 modules 解析走 capability profile
（profile-first），引擎 domain_mapping 不注册业务域（通用性原则）。
"""

from app.core.engine.domain_mapping import DEFAULT_INTENT_MODULES, resolve_domain


def test_unknown_domain_falls_back_to_default():
    intent, modules = resolve_domain("not_a_domain")
    assert (intent, modules) == DEFAULT_INTENT_MODULES


def test_none_domain_falls_back_to_default():
    assert resolve_domain(None) == DEFAULT_INTENT_MODULES


def test_engine_mapping_stays_domain_agnostic():
    """通用性回归锁：引擎映射表不注册业务域。"""
    from app.core.engine.domain_mapping import DOMAIN_TO_INTENT_MODULES

    assert "mall_ops" not in DOMAIN_TO_INTENT_MODULES
