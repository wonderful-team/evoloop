"""Unit tests for P2.3: EntityGrouper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.atlas.source.skeleton import (
    EntityGrouper,
    get_entity_groups,
)
from app.models.codebase import SourceFile


class TestEntityGrouper:
    def test_constructor(self):
        gen = EntityGrouper()
        assert gen is not None

    def test_extract_entity_from_suffixes(self):
        gen = EntityGrouper()
        assert gen._extract_entity("app/controller/OrderController.php") == "order"
        assert gen._extract_entity("service/UserService.php") == "user"
        assert gen._extract_entity("repository/GoodsRepository.php") == "goods"
        assert gen._extract_entity("model/order_impl.py") == "order"

    def test_extract_entity_from_category(self):
        gen = EntityGrouper()
        assert gen._extract_entity("app/model/Order.php", category="model") == "order"
        assert gen._extract_entity("controller/User.php", category="controller") == "user"

    def test_extract_entity_skips_generic_names(self):
        gen = EntityGrouper()
        assert gen._extract_entity("app/controller/BaseController.php") is None
        assert gen._extract_entity("service/CommonService.php") is None
        assert gen._extract_entity("app/common.php") is None

    def test_group_by_module_prefers_entities(self):
        gen = EntityGrouper()
        from app.core.atlas.source.skeleton.generator import ClassifiedFile

        root = ClassifiedFile(
            source_file=SourceFile(id=0, repository_id=0, path="", checksum=""),
            category="root",
            layer="root",
            risk_tier="system",
            children=[
                ClassifiedFile(
                    source_file=SourceFile(id=1, repository_id=1, path="app/controller/OrderController.php", checksum=""),
                    category="controller",
                    layer="entry_point",
                    risk_tier="ui",
                ),
                ClassifiedFile(
                    source_file=SourceFile(id=2, repository_id=1, path="app/service/OrderService.php", checksum=""),
                    category="service",
                    layer="business_logic",
                    risk_tier="business",
                ),
                ClassifiedFile(
                    source_file=SourceFile(id=3, repository_id=1, path="app/model/User.php", checksum=""),
                    category="model",
                    layer="data",
                    risk_tier="data",
                ),
                ClassifiedFile(
                    source_file=SourceFile(id=4, repository_id=1, path="app/common/Util.php", checksum=""),
                    category="library",
                    layer="shared",
                    risk_tier="business",
                ),
            ],
        )

        modules = gen._group_by_module(root)
        assert "order" in modules
        assert "user" in modules
        assert any(modules[name] for name in modules if name != "order" and name != "user")
        assert len(modules["order"]) == 2
        assert len(modules["user"]) == 1

    @pytest.mark.asyncio
    async def test_get_entity_groups_returns_dict(self):
        gen = EntityGrouper()
        mock_session = AsyncMock()
        mock_execute = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_execute)

        result = await gen.get_entity_groups(repo_id=1, session=mock_session)
        assert isinstance(result, dict)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_entity_groups_no_repo(self):
        """When repo is None, get_entity_groups should return empty dict."""
        from app.core.atlas.source.skeleton import get_entity_groups
        with patch("app.core.atlas.source.skeleton.session_scope") as mock_scope:
            mock_session = AsyncMock()
            mock_execute = MagicMock()
            mock_execute.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_execute)
            mock_scope.return_value.__aenter__.return_value = mock_session
            result = await get_entity_groups(project_id=999)
            assert result == {}
