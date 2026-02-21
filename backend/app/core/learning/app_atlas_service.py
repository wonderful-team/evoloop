import logging
import json
import hashlib
from typing import Any, Optional, List

from app.core.environment.probers.app_model import AppModel, AppStateNode, UIElement, StateTransition
from app.infrastructure.database.graph.atlas_store import Neo4jAtlasStore

logger = logging.getLogger(__name__)


class AppAtlasService:
    """
    Coordinator for App Atlas operations.
    Handles data accumulation, graph persistence, and retrieval for Agent Tools.
    """

    def __init__(self, store: Neo4jAtlasStore = None):
        self.store = store or Neo4jAtlasStore()

    async def on_ui_tree_observed(self, event: Any) -> None:
        """
        Background mapping of observed UI trees into the App Atlas.
        Listens to continuous observations from find_element/dump_ui.
        """
        bundle_id = event.data.get("bundle_id")
        window_title = event.data.get("window_title")
        platform = event.data.get("platform")
        elements_data = event.elements
        screenshot_hash = event.data.get("screenshot_hash")
        
        if not bundle_id or bundle_id == "unknown" or not elements_data:
            return
            
        try:
            app_model = AppModel(app_name=bundle_id, bundle_id=bundle_id, platform=platform)
            state_id = self._generate_state_id(bundle_id, window_title)
            
            # Elements are passed as serialized dicts
            elements = [UIElement.from_dict(e) for e in elements_data]
            
            state = AppStateNode(
                state_id=state_id,
                window_title=window_title,
                elements=elements,
                screenshot_hash=screenshot_hash
            )
            app_model.add_state(state)
            
            await self.store.save_app_model(app_model)
            logger.debug(f"[AppAtlas] Background mapped state '{window_title}' for {bundle_id}")
            
        except Exception as e:
            logger.error(f"[AppAtlas] Failed to index observed UI tree for {bundle_id}: {e}")

    async def query_app_atlas(self, bundle_ids: str | List[str]) -> str:
        """
        Formats a structural summary of the app map for one or more applications.
        Used by the 'query_app_atlas' tool.
        """
        if isinstance(bundle_ids, str):
            bundle_ids = [bundle_ids]

        all_outputs = []
        for bundle_id in bundle_ids:
            summary = await self.store.get_app_summary(bundle_id)
            if not summary:
                all_outputs.append(f"No atlas data found for application: {bundle_id}")
                continue

            transitions = await self.store.get_transitions_summary(bundle_id)

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
        Used by the 'list_app_atlas' tool.
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


# Global instance
app_atlas_service = AppAtlasService()
