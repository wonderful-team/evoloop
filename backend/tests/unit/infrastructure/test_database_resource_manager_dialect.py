"""
DatabaseResourceManager 方言抽象验证 (Phase 7)

验证 DatabaseResourceManager 的方言属性（writes_table、placeholder 等）
在 EMBEDDED_MODE=true/false 两种模式下返回正确的 SQL 方言值。
"""

from unittest.mock import patch

import pytest

from app.core.config import settings


class TestDialectAbstraction:
    """验证 DatabaseResourceManager 的方言属性在不同模式下返回正确值。"""

    # ------------------------------------------------------------------
    # writes_table
    # ------------------------------------------------------------------

    def test_embedded_writes_table(self):
        """EMBEDDED_MODE=true → writes_table == 'writes'"""
        with patch.object(settings, "EMBEDDED_MODE", True):
            from app.infrastructure.database.resource_manager import db_resource_manager
            assert db_resource_manager.writes_table == "writes"

    def test_production_writes_table(self):
        """EMBEDDED_MODE=false → writes_table == 'checkpoint_writes'"""
        with patch.object(settings, "EMBEDDED_MODE", False):
            from app.infrastructure.database.resource_manager import db_resource_manager
            assert db_resource_manager.writes_table == "checkpoint_writes"

    # ------------------------------------------------------------------
    # placeholder
    # ------------------------------------------------------------------

    def test_embedded_placeholder(self):
        """EMBEDDED_MODE=true → placeholder == '?'"""
        with patch.object(settings, "EMBEDDED_MODE", True):
            from app.infrastructure.database.resource_manager import db_resource_manager
            assert db_resource_manager.placeholder == "?"

    def test_production_placeholder(self):
        """EMBEDDED_MODE=false → placeholder == '%s'"""
        with patch.object(settings, "EMBEDDED_MODE", False):
            from app.infrastructure.database.resource_manager import db_resource_manager
            assert db_resource_manager.placeholder == "%s"

    # ------------------------------------------------------------------
    # SQLAlchemy URI 切换
    # ------------------------------------------------------------------

    def test_embedded_sqlalchemy_uri(self):
        """EMBEDDED_MODE=true → SQLALCHEMY_DATABASE_URI 以 sqlite 开头"""
        with patch.object(settings, "EMBEDDED_MODE", True):
            assert settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite")

    def test_production_sqlalchemy_uri(self):
        """EMBEDDED_MODE=false → SQLALCHEMY_DATABASE_URI 以 postgresql 开头"""
        with patch.object(settings, "EMBEDDED_MODE", False):
            assert settings.SQLALCHEMY_DATABASE_URI.startswith("postgresql")

    # ------------------------------------------------------------------
    # 跨模式一致性
    # ------------------------------------------------------------------

    def test_dialect_values_never_empty(self):
        """writes_table 和 placeholder 在任何模式下都不应为空。"""
        for mode in (True, False):
            with patch.object(settings, "EMBEDDED_MODE", mode):
                from app.infrastructure.database.resource_manager import db_resource_manager
                assert db_resource_manager.writes_table
                assert db_resource_manager.placeholder
