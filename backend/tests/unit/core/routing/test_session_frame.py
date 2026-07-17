"""Session frame: anaphora resolution, clarify pending, frame lifecycle."""

import pytest

from app.core.routing.session_frame import (
    SessionFrame,
    clarify_question,
    clear_frame,
    consume_pending,
    get_frame,
    has_anaphora,
    has_connector,
    resolve_anaphora,
    set_domain_nouns,
    update_frame,
)

pytestmark = pytest.mark.unit

FRAME = SessionFrame(current_entity={"query": "夜光亚克力钥匙扣"})


@pytest.fixture
def _restore_domain_nouns():
    yield
    set_domain_nouns([])


@pytest.mark.parametrize(
    "text",
    [
        "把它的库存改成142",
        "它的价格改成10",
        "查一下它的价格",
        "给他备注一下",
        "将这个下架",
        "应该把它下架",
        "这个多少钱",
    ],
)
def test_anaphora_rewrite_hits(text: str) -> None:
    out = resolve_anaphora(text, FRAME)
    assert "夜光亚克力钥匙扣" in out
    assert "它" not in out and "这个" not in out


@pytest.mark.parametrize(
    "text",
    [
        "查一下吉他的价格",  # 吉他: entity morpheme, not a pronoun
        "把维他奶下架",  # 维他奶
        "维也纳沙发多少钱",  # 维也纳
        "把其他的都删了",  # 其他
        "他多少钱",  # bare pronoun without context -> conservative miss
        "应该下架",  # 应该: 该 excluded
    ],
)
def test_anaphora_no_false_positive(text: str) -> None:
    assert resolve_anaphora(text, FRAME) == text


def test_no_frame_no_rewrite() -> None:
    assert resolve_anaphora("把它的库存改成142", None) == "把它的库存改成142"
    empty = SessionFrame()
    assert resolve_anaphora("把它的库存改成142", empty) == "把它的库存改成142"


def test_query_already_present_no_rewrite() -> None:
    text = "夜光亚克力钥匙扣降价"
    assert resolve_anaphora(text, FRAME) == text


def test_consume_pending_splice() -> None:
    frame = SessionFrame(pending={"kind": "missing_entity", "text": "把它的库存改成142"})
    combined, consumed = consume_pending("夜光亚克力钥匙扣。", frame)
    assert consumed is True
    assert combined == "把夜光亚克力钥匙扣的库存改成142"
    assert frame.pending is None


def test_consume_pending_prefix_without_pronoun() -> None:
    frame = SessionFrame(pending={"kind": "missing_entity", "text": "改库存到142"})
    combined, consumed = consume_pending("钥匙扣", frame)
    assert consumed is True
    assert combined == "钥匙扣，改库存到142"


def test_consume_pending_no_pending() -> None:
    text, consumed = consume_pending("查一下订单", SessionFrame())
    assert consumed is False
    assert text == "查一下订单"


def test_clarify_question_domain() -> None:
    assert "订单" in clarify_question("给这个订单备注")
    assert "商品" in clarify_question("把它的库存改成142")
    assert "哪个" in clarify_question("把它删了")


def test_connector_detection() -> None:
    assert has_connector("查一下钥匙扣，然后改库存")
    assert has_connector("查完之后再降价")
    assert not has_connector("把它的库存改成142")


def test_frame_lifecycle() -> None:
    tid = "test-frame-lifecycle"
    clear_frame(tid)
    assert get_frame(tid) is None
    update_frame(tid, current_page="http://x/lists")
    update_frame(tid, current_entity={"query": "X"}, pending={"kind": "missing_entity"})
    frame = get_frame(tid)
    assert frame is not None
    assert frame.current_page == "http://x/lists"
    assert frame.current_entity == {"query": "X"}
    assert frame.pending == {"kind": "missing_entity"}
    update_frame(tid, pending=None)
    assert get_frame(tid).pending is None
    clear_frame(tid)
    assert get_frame(tid) is None


def test_has_anaphora_boundaries() -> None:
    assert has_anaphora("把它的库存改成142")
    assert has_anaphora("这个多少钱")
    assert not has_anaphora("查一下吉他的价格")
    assert not has_anaphora("应该下架")


def test_compound_uses_domain_nouns(_restore_domain_nouns) -> None:
    # Without nouns: 这个 matches bare, the noun survives the substitution
    # (conservative degradation, not corruption).
    set_domain_nouns([])
    assert resolve_anaphora("这个商品多少钱", FRAME) == "夜光亚克力钥匙扣商品多少钱"
    # Mall domain: compound swallows the noun.
    set_domain_nouns({"商品", "订单"})
    assert resolve_anaphora("这个商品多少钱", FRAME) == "夜光亚克力钥匙扣多少钱"
    assert resolve_anaphora("该订单备注一下", FRAME) == "夜光亚克力钥匙扣备注一下"
    # Switching industry re-compiles the compounds.
    set_domain_nouns({"菜品"})
    assert resolve_anaphora("这个菜品多少钱", FRAME) == "夜光亚克力钥匙扣多少钱"
    assert resolve_anaphora("这个商品多少钱", FRAME) == "夜光亚克力钥匙扣商品多少钱"
