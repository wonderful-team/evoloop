import json
import logging
from datetime import datetime

from sqlalchemy import delete, select

from app.core.atlas.models import AtlasApp
from app.core.atlas.ports.store import IAtlasStore
from app.core.atlas.schemas import AtlasAppInfo, AtlasAppSummary, AtlasStateDetail
from app.infrastructure.database import session_scope
from app.models.atlas import AtlasApp as AtlasAppModel
from app.models.atlas import AtlasState as AtlasStateModel
from app.models.atlas import AtlasTransition as AtlasTransitionModel

logger = logging.getLogger(__name__)


class SQLAtlasStore(IAtlasStore):
    """SQL-based Atlas Storage using existing PostgreSQL/SQLite tables."""

    async def save_app_model(self, atlas_app: AtlasApp) -> None:
        async with session_scope() as session:
            existing = (
                (
                    await session.execute(
                        select(AtlasAppModel).where(
                            AtlasAppModel.bundle_id == atlas_app.bundle_id,
                            AtlasAppModel.platform == atlas_app.platform,
                        )
                    )
                )
                .scalars()
                .first()
            )

            if existing:
                app_record = existing
                app_record.app_name = atlas_app.app_name
                app_record.version_hash = atlas_app.version_hash
                app_record.last_observed_at = datetime.now()
                # Remove old states & transitions (explicit selects — the
                # `states` relationship lazy-loads, which breaks under async)
                old_states = (
                    (
                        await session.execute(
                            select(AtlasStateModel).where(
                                AtlasStateModel.app_id == app_record.id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for s in old_states:
                    await session.delete(s)
                old_transitions = (
                    (
                        await session.execute(
                            select(AtlasTransitionModel).where(
                                AtlasTransitionModel.app_id == app_record.id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for t in old_transitions:
                    await session.delete(t)
            else:
                app_record = AtlasAppModel(
                    bundle_id=atlas_app.bundle_id,
                    app_name=atlas_app.app_name,
                    platform=atlas_app.platform,
                    version_hash=atlas_app.version_hash,
                    last_observed_at=datetime.now(),
                )
                session.add(app_record)
                await session.flush()

            for state_id, state in atlas_app.states.items():
                state_record = AtlasStateModel(
                    app_id=app_record.id,
                    state_id=state_id,
                    window_title=state.window_title,
                    screenshot_hash=state.screenshot_hash,
                    elements_json=json.dumps(
                        [e.model_dump() for e in state.elements],
                        ensure_ascii=False,
                    ),
                )
                session.add(state_record)

            for trans in atlas_app.transitions:
                trans_record = AtlasTransitionModel(
                    app_id=app_record.id,
                    from_state_id=trans.from_state,
                    to_state_id=trans.to_state,
                    action_label=trans.action.label if trans.action else "",
                    action_type=trans.action_type,
                )
                session.add(trans_record)

            await session.commit()
            logger.info(f"Saved Atlas for {atlas_app.bundle_id}")

    async def get_app_summary(
        self, bundle_id: str, platform: str = "macos"
    ) -> AtlasAppSummary | None:
        async with session_scope() as session:
            app = (
                (
                    await session.execute(
                        select(AtlasAppModel).where(
                            AtlasAppModel.bundle_id == bundle_id,
                            AtlasAppModel.platform == platform,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not app:
                return None

            states = (
                (
                    await session.execute(
                        select(AtlasStateModel).where(AtlasStateModel.app_id == app.id)
                    )
                )
                .scalars()
                .all()
            )

            return AtlasAppSummary(
                app_name=app.app_name,
                bundle_id=bundle_id,
                platform=platform,
                version_hash=app.version_hash or "",
                state_count=len(states),
                states=[{"id": s.state_id, "title": s.window_title} for s in states],
            )

    async def get_state_detail(
        self, bundle_id: str, state_id: str, platform: str = "macos"
    ) -> AtlasStateDetail | None:
        async with session_scope() as session:
            app = (
                (
                    await session.execute(
                        select(AtlasAppModel).where(
                            AtlasAppModel.bundle_id == bundle_id,
                            AtlasAppModel.platform == platform,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not app:
                return None

            state = (
                (
                    await session.execute(
                        select(AtlasStateModel).where(
                            AtlasStateModel.app_id == app.id,
                            AtlasStateModel.state_id == state_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not state:
                return None

            elements = json.loads(state.elements_json) if state.elements_json else []
            return AtlasStateDetail(
                state_id=state_id,
                window_title=state.window_title,
                elements=elements,
            )

    async def get_transitions_summary(
        self, bundle_id: str, platform: str = "macos"
    ) -> list[dict]:
        async with session_scope() as session:
            app = (
                (
                    await session.execute(
                        select(AtlasAppModel).where(
                            AtlasAppModel.bundle_id == bundle_id,
                            AtlasAppModel.platform == platform,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not app:
                return []

            transitions = (
                (
                    await session.execute(
                        select(AtlasTransitionModel).where(
                            AtlasTransitionModel.app_id == app.id
                        )
                    )
                )
                .scalars()
                .all()
            )

            return [
                {
                    "from_state": t.from_state_id,
                    "label": t.action_label,
                    "type": t.action_type,
                    "to_state": t.to_state_id,
                }
                for t in transitions
            ]

    async def list_apps(self) -> list[AtlasAppInfo]:
        async with session_scope() as session:
            apps = (await session.execute(select(AtlasAppModel))).scalars().all()
            return [
                AtlasAppInfo(
                    app_name=a.app_name,
                    bundle_id=a.bundle_id,
                    platform=a.platform,
                )
                for a in apps
            ]

    async def clear_all_data(self) -> None:
        async with session_scope() as session:
            await session.execute(delete(AtlasTransitionModel))
            await session.execute(delete(AtlasStateModel))
            await session.execute(delete(AtlasAppModel))
            await session.commit()
            logger.warning("Atlas data cleared from SQL")
