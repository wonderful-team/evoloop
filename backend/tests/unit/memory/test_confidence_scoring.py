"""
Unit tests for the rewritten _calculate_confidence method.

Run with: pytest tests/unit/memory/test_confidence_scoring.py -v
"""

import pytest
from unittest.mock import AsyncMock

from app.core.memory.auto_extraction import AutoMemoryExtractor


@pytest.fixture
def extractor():
    """Create an AutoMemoryExtractor."""
    mock_manager = AsyncMock()
    extractor = AutoMemoryExtractor(memory_manager=mock_manager)
    return extractor


class TestTieredScoring:
    """Tests for Tier A/B/C mutually-exclusive scoring."""

    async def test_tier_a_resource_path(self, extractor):
        score = await extractor._calculate_confidence(
            "Check app/core/auth.py for details about the JWT verification logic. "
            "This module handles token validation, expiration checks, and user "
            "session management across all protected API endpoints in the system.",
            project_id=1,
        )
        # Base 0.5 + length ~0.2 + Tier A 0.25 = ~0.95
        assert score >= 0.89

    async def test_tier_b_specific_indicators(self, extractor):
        score = await extractor._calculate_confidence(
            "Release scheduled for 2026-05-01. Version v2.1.0 includes critical "
            "security patches and performance improvements for the authentication "
            "middleware and database connection pooling components.",
            project_id=1,
        )
        # Base 0.5 + length 0.2 + Tier B 0.15 = ~0.85
        assert score >= 0.8

    async def test_tier_c_structure(self, extractor):
        score = await extractor._calculate_confidence(
            "- First step: validate the user input against the schema definition\n"
            "- Second step: process the data through the transformation pipeline\n"
            "- Third step: store results in the cache for subsequent requests",
            project_id=1,
        )
        # Base 0.5 + length 0.2 + Tier C 0.05 = ~0.75
        assert 0.7 <= score <= 0.85

    async def test_tier_c_actionable(self, extractor):
        score = await extractor._calculate_confidence(
            "You must always validate the input before processing. Never trust "
            "client-side data without server-side verification and sanitization.",
            project_id=1,
        )
        # Base 0.5 + length 0.2 + Tier C 0.05 = ~0.75
        assert score >= 0.7

    async def test_no_tier_no_bonus(self, extractor):
        score = await extractor._calculate_confidence(
            "Hello world this is a generic sentence with nothing special.",
            project_id=1,
        )
        # Base 0.5 + length ~0.1 = ~0.6 (no tier bonus)
        assert 0.55 <= score <= 0.75


class TestLengthScoring:
    """Tests for continuous length scoring."""

    async def test_ideal_length(self, extractor):
        content = "x" * 300  # 300 chars, ideal range
        score = await extractor._calculate_confidence(content, project_id=1)
        assert score >= 0.65  # base 0.5 + 0.2 = 0.7 before other factors

    async def test_short_length_penalty(self, extractor):
        content = "short"
        score = await extractor._calculate_confidence(content, project_id=1)
        # Base 0.5 - 0.15 = 0.35
        assert score < 0.5

    async def test_very_long_penalty(self, extractor):
        content = "x" * 1500
        score = await extractor._calculate_confidence(content, project_id=1)
        # Base 0.5 - 0.1 = 0.4
        assert score < 0.5

    async def test_length_continuity_at_boundary(self, extractor):
        """No断崖跳跃 at 100 chars boundary."""
        score_99 = await extractor._calculate_confidence("x" * 99, project_id=1)
        score_100 = await extractor._calculate_confidence("x" * 100, project_id=1)
        score_101 = await extractor._calculate_confidence("x" * 101, project_id=1)

        # Should be monotonically increasing around the ideal threshold
        assert score_100 >= score_99
        assert score_101 >= score_100


class TestLLMConfidenceCeiling:
    """Tests for LLM confidence trust ceiling behavior."""

    async def test_low_llm_confidence_caps_score(self, extractor):
        score = await extractor._calculate_confidence(
            "x" * 300,  # Would normally score high
            llm_confidence=0.2,
            project_id=1,
        )
        assert score <= 0.6

    async def test_high_llm_confidence_boosts_score(self, extractor):
        score = await extractor._calculate_confidence(
            "x" * 300,
            llm_confidence=0.9,
            project_id=1,
        )
        # Base ~0.7 * 1.1 = 0.77
        assert score >= 0.75
        assert score <= 1.0

    async def test_mid_llm_confidence_no_effect(self, extractor):
        score_no_llm = await extractor._calculate_confidence("x" * 300, project_id=1)
        score_mid = await extractor._calculate_confidence(
            "x" * 300,
            llm_confidence=0.5,
            project_id=1,
        )
        assert abs(score_no_llm - score_mid) < 0.01


class TestVagueWordPenalty:
    """Tests for capped vague-word penalty."""

    async def test_vague_words_capped(self, extractor):
        score = await extractor._calculate_confidence(
            "maybe perhaps somehow might could be something",
            project_id=1,
        )
        # 6 vague words but capped at 3 * 0.05 = 0.15 penalty
        # Base 0.5 + length ~0.05 - 0.15 = ~0.4
        assert score >= 0.35  # Not driven below 0.3 by extreme penalty

    async def test_no_vague_words_no_penalty(self, extractor):
        score = await extractor._calculate_confidence(
            "Always validate input strictly.",
            project_id=1,
        )
        assert score >= 0.6


class TestResourcePathRegex:
    """Tests for domain-agnostic resource path detection."""

    async def test_code_path_triggers_tier_a(self, extractor):
        score = await extractor._calculate_confidence(
            "The src/components/Button.tsx file contains the core rendering logic. "
            "It handles user interactions, state updates, and event delegation for "
            "all button variants across the application interface.",
            project_id=1,
        )
        assert score >= 0.9  # Tier A

    async def test_document_path_triggers_tier_a(self, extractor):
        score = await extractor._calculate_confidence(
            "The contracts/agreement_v2.pdf file needs legal review before signing. "
            "It contains updated terms for data processing and liability coverage.",
            project_id=1,
        )
        assert score >= 0.9  # Tier A

    async def test_no_path_no_tier_a(self, extractor):
        score = await extractor._calculate_confidence(
            "test.py is a common word not a path",  # No slash
            project_id=1,
        )
        # Should NOT be Tier A — no / in path
        assert score < 0.9


class TestClamping:
    """Tests for score clamping."""

    async def test_minimum_clamp(self, extractor):
        # Extremely bad content: very short + max vague penalty
        score = await extractor._calculate_confidence("maybe", project_id=1)
        assert score >= 0.1

    async def test_maximum_clamp(self, extractor):
        # Perfect content with high LLM confidence
        score = await extractor._calculate_confidence(
            "x" * 300,
            llm_confidence=0.95,
            project_id=1,
        )
        assert score <= 1.0


class TestComplexRealWorldScenarios:
    """Complex scenario-based tests with realistic content."""

    async def test_chinese_technical_document(self, extractor):
        """Real-world Chinese software architecture discussion."""
        content = (
            "在微服务架构中，服务网格（Service Mesh）通过 Sidecar 代理模式实现了"
            "流量管理、安全通信和可观测性。Istio 是目前最流行的实现，它使用 Envoy"
            "作为数据平面，Pilot 作为控制平面。我们团队在生产环境使用了 Istio 1.18，"
            "部署在 Kubernetes 集群上，通过 VirtualService 和 DestinationRule 管理"
            "服务间的流量路由。mTLS 默认开启，所有服务间通信都经过双向 TLS 认证。"
            "配置文件位于 k8s/istio/config.yaml，建议参考官方文档进行升级。"
        )
        score = await extractor._calculate_confidence(content, project_id=1)
        # Tier A (resource path) + ideal length
        assert score >= 0.9

    async def test_legal_contract_analysis(self, extractor):
        """Legal domain content with dates, versions, and actionable terms."""
        content = (
            "根据合同第 3.2 条，乙方须在 2026-06-30 前完成交付。"
            "若因不可抗力导致延期，应在 5 个工作日内提供书面说明。"
            "违约责任按合同总金额的 0.05% / 日计算，上限为合同总额的 20%。"
            "争议解决方式：提交甲方所在地仲裁委员会仲裁。"
            "合同版本：v3.1.2，签署日期：2026-04-15。"
        )
        score = await extractor._calculate_confidence(content, project_id=1)
        # Tier B (dates + numbers + versions) + ideal length
        assert 0.75 <= score <= 0.95

    async def test_mixed_quality_content(self, extractor):
        """Content with both strong and weak signals — should land in middle."""
        content = (
            "The API might need some changes. Perhaps we should consider using"
            " a different approach. The current implementation somehow works but"
            " could be improved. We need to refactor the auth module before"
            " the next release scheduled for 2026-05-15."
        )
        score = await extractor._calculate_confidence(content, project_id=1)
        # 3 vague words (capped at 0.15 penalty) + date (Tier B 0.15)
        # Base 0.5 + length ~0.2 - 0.15 + 0.15 = ~0.7
        assert 0.6 <= score <= 0.8

    async def test_medical_diagnosis_record(self, extractor):
        """Medical content with domain-specific Chinese terms."""
        content = (
            "患者入院时表现为心室颤动，心率 180 次/分，血压 80/50 mmHg。"
            "心电图显示心房扑动与心室颤动同时存在，QT 间期延长至 520ms。"
            "立即给予胺碘酮 150mg 静脉推注，15 分钟后转为窦性心律。"
            "后续治疗方案：口服胺碘酮 200mg tid，监测肝功能和甲状腺功能。"
            "建议 1 周后复查动态心电图，评估是否需要射频消融。"
        )
        score = await extractor._calculate_confidence(content, project_id=1)
        # Tier B (numbers) + ideal length
        assert score >= 0.8

    async def test_extreme_length_boundaries(self, extractor):
        """Verify no discontinuities across all length ranges."""
        scores = []
        for length in [10, 29, 30, 31, 50, 99, 100, 101, 300, 500, 501, 999, 1000, 1001]:
            content = "x" * length
            score = await extractor._calculate_confidence(content, project_id=1)
            scores.append((length, score))

        # Score should generally increase then decrease
        # Short should be lower than ideal
        assert scores[0][1] < scores[6][1]  # 10 chars < 100 chars
        assert scores[3][1] < scores[6][1]  # 31 chars < 100 chars
        # Ideal should be higher than very long
        assert scores[6][1] > scores[-1][1]  # 100 chars > 1001 chars
        # Clamp should prevent extremes
        for _, s in scores:
            assert 0.1 <= s <= 1.0

    async def test_llm_confidence_extremes(self, extractor):
        """Verify LLM confidence ceiling at all score levels."""
        # Low-quality content with low LLM confidence → should be heavily capped
        low_score = await extractor._calculate_confidence(
            "maybe perhaps somehow",
            llm_confidence=0.1,
            project_id=1,
        )
        assert low_score <= 0.6

        # Same content with high LLM confidence → slight boost but still bounded
        high_score = await extractor._calculate_confidence(
            "maybe perhaps somehow",
            llm_confidence=0.95,
            project_id=1,
        )
        # High LLM conf can't save truly bad content, but allows slight boost
        assert high_score > low_score
        assert high_score <= 0.7

    async def test_multiple_resource_paths(self, extractor):
        """Content with multiple file paths — still Tier A, not stacked."""
        content = (
            "Modify src/auth/login.ts, src/auth/token.ts, and"
            " tests/auth/login.spec.ts to support OAuth2 flow."
            " Also update docs/api/auth.md with the new endpoints."
        )
        score = await extractor._calculate_confidence(content, project_id=1)
        # Multiple paths should NOT stack — still just Tier A (+0.25)
        assert score >= 0.85
        assert score <= 0.95  # Not over 0.95 since only one Tier bonus

    async def test_cross_language_mixed_content(self, extractor):
        """Chinese + English interleaved technical discussion."""
        content = (
            "在实现分布式缓存时，我们选择了 Redis Cluster 作为存储后端。"
            "缓存一致性（Cache Consistency）通过 Cache-Aside 模式保证："
            "读取时先查缓存，miss 后回源并写入 Redis；写入时先更新 DB，"
            "再删除缓存。为了避免缓存穿透，我们使用了布隆过滤器。"
            "相关代码在 src/cache/bloom_filter.py 中实现。"
        )
        score = await extractor._calculate_confidence(content, project_id=1)
        # Tier A (resource path) + ideal length
        assert score >= 0.9
