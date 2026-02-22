import logging
import hashlib
from typing import Any, List, Union

from app.core.atlas.models import AtlasApp, AtlasState, AtlasElement
from app.core.atlas.ports.store import IAtlasStore
from app.core.atlas.adapters.neo4j_store import Neo4jAtlasStore

logger = logging.getLogger(__name__)


class AtlasEngine:
    """
    Core Cognitive Engine for Spatial Memory (App Atlas).
    Handles data accumulation (ingestion from EventBus), graph persistence, 
    and retrieval for Agent Tools.
    """

    def __init__(self, store: IAtlasStore = None):
        self.store = store or Neo4jAtlasStore()

    async def on_ui_tree_observed(self, event: Any) -> None:
        """
        Background mapping of observed UI trees into the App Atlas.
        Listens to continuous observations from the event bus.
        """
        bundle_id = event.data.get("bundle_id")
        window_title = event.data.get("window_title")
        platform = event.data.get("platform", "macos")
        elements_data = event.elements
        screenshot_hash = event.data.get("screenshot_hash")
        
        if not bundle_id or bundle_id == "unknown" or not elements_data:
            return
            
        try:
            # We use 'name' or 'bundle_id' for app_name as default
            app_model = AtlasApp(app_name=bundle_id, bundle_id=bundle_id, platform=platform)
            state_id = self._generate_state_id(bundle_id, window_title)
            
            # Elements are passed as standardized dicts from the event payload
            elements = [AtlasElement.from_dict(e) for e in elements_data]
            
            state = AtlasState(
                state_id=state_id,
                window_title=window_title,
                elements=elements,
                screenshot_hash=screenshot_hash
            )
            app_model.add_state(state)
            
            await self.store.save_app_model(app_model)
            logger.debug(f"[AtlasEngine] Background mapped state '{window_title}' for {bundle_id}")
            
        except Exception as e:
            logger.error(f"[AtlasEngine] Failed to index observed UI tree for {bundle_id}: {e}")

    async def query_app_atlas(self, bundle_ids: Union[str, List[str]], platform: str = "macos") -> str:
        """
        Formats a structural summary of the app map for one or more applications.
        """
        if isinstance(bundle_ids, str):
            bundle_ids = [bundle_ids]

        all_outputs = []
        for bundle_id in bundle_ids:
            summary = await self.store.get_app_summary(bundle_id, platform=platform)
            if not summary:
                all_outputs.append(f"No atlas data found for application: {bundle_id}")
                continue

            transitions = await self.store.get_transitions_summary(bundle_id, platform=platform)

            output = [
                f"### 🗺️ App UI Atlas: {summary['app_name']} ({bundle_id})",
                f"**Known States ({summary['state_count']})**:"
            ]

            for state in summary["states"]:
                output.append(f"- {state['title']} (ID: {state['id']})")

            if transitions:
                output.append("\n**Known Transitions**:")
                for t in transitions:
                    output.append(f"- {t['from_state']} --[{t['type']}: {t['label']}]--> {t['to_state']}")
            
            all_outputs.append("\n".join(output))

        if not all_outputs:
            return "No bundle IDs provided or found."

        final_result = "\n\n---\n\n".join(all_outputs)
        final_result += "\n\n💡 Tip: Use AX paths extracted from individual states to target specific buttons."
        return final_result

    async def list_apps(self) -> str:
        """
        Returns a formatted markdown directory of all apps with available UI maps.
        """
        apps = await self.store.list_apps()
        if not apps:
            return "No applications have UI Maps (Atlas) recorded yet. Atlas is built automatically as you perform tasks."

        output = ["### 📚 App Atlas Directory", "The following applications have structural UI maps available:"]
        for app in apps:
            output.append(f"- **{app['app_name']}** (Bundle ID: `{app['bundle_id']}`, Platform: {app['platform']})")

        output.append("\n💡 You can use `query_app_atlas(bundle_id)` to retrieve detailed maps for any of these.")
        return "\n".join(output)

    def _generate_state_id(self, bundle_id: str, window_title: str) -> str:
        """Generates a stable semantic ID for a UI state."""
        raw = f"{bundle_id}:{window_title}"
        h = hashlib.md5(raw.encode()).hexdigest()[:8]
        # Clean title for readability
        clean_title = "".join(c for c in window_title if c.isalnum()).lower()[:20]
        return f"{clean_title}_{h}"
