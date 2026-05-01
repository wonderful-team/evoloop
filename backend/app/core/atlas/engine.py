import logging
from typing import Any

from app.core.atlas.adapters.neo4j_store import Neo4jAtlasStore
from app.core.atlas.models import AtlasApp, AtlasElement, AtlasState
from app.core.atlas.ports.store import IAtlasStore
from app.core.atlas.strategy import AppStrategy, AtlasStrategyStore, InteractionStrategy
from app.core.config import settings
from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
from app.utils import render_template
from app.utils.hash import compute_state_id

logger = logging.getLogger(__name__)


class AtlasEngine:
    """
    Core Cognitive Engine for Spatial Memory (App Atlas).
    Handles data accumulation (ingestion from EventBus), graph persistence, 
    and retrieval for Agent Tools.

    NOTE: In embedded mode, Atlas persistence is not available (no JSON backend
    implemented yet). All store operations become no-ops.
    """

    def __init__(self, store: IAtlasStore = None):
        if settings.EMBEDDED_MODE and store is None:
            logger.warning(
                "[AtlasEngine] Embedded mode: Atlas persistence is disabled "
                "(no file-based AtlasStore implemented)."
            )
        self.store = store or Neo4jAtlasStore()

    async def on_ui_tree_observed(self, event: Any) -> None:
        """
        Background mapping of observed UI trees into the App Atlas.
        Listens to continuous observations from the event bus.

        Phase 6: Dynamic App Handling
        - Detects if the app is "coordinate-unstable" (scrolling lists, feeds)
        - For dynamic apps: only stores infrastructure (static elements like toolbars)
        - For static apps: stores full UI map with element classification
        """
        bundle_id = event.data.get("bundle_id")
        window_title = event.data.get("window_title")
        platform = event.data.get("platform", "macos")
        elements_data = event.elements
        screenshot_hash = event.data.get("screenshot_hash")
        version_hash = event.data.get("version_hash", "")

        if not bundle_id or bundle_id == "unknown" or not elements_data:
            return

        # Phase 6: Check if this is a dynamic (coordinate-unstable) app
        try:
            dynamic_apps = await DynamicAppTriage.get_dynamic_apps(platform)
            is_dynamic = bundle_id in dynamic_apps

            if is_dynamic:
                logger.info(f"[AtlasEngine] Detected dynamic app '{bundle_id}' - storing infrastructure only")
                await self._store_dynamic_app_infrastructure(
                    bundle_id=bundle_id,
                    window_title=window_title,
                    platform=platform,
                    elements_data=elements_data,
                    version_hash=version_hash,
                    screenshot_hash=screenshot_hash
                )
                return
        except Exception as e:
            logger.debug(f"[AtlasEngine] Dynamic app check failed: {e}")

        # Optional: Merge with Live AX Tree to enrich visual/OCR nodes with os_identifiers
        if platform == "macos":
            try:
                import ast

                from app.infrastructure.drivers.macos import macos_driver
                raw_tree = macos_driver.dump_ax_tree()
                if raw_tree and "Error" not in raw_tree:
                    ax_elements = ast.literal_eval(raw_tree)
                    scale = macos_driver.get_ui_scale_factor()

                    for el_data in elements_data:
                        bounds = el_data.get("bounds", {})
                        if not bounds:
                            continue

                        # Note: If OCR provider already scaled to points, scale will be handled.
                        # If bounds are in pixels, we normalize them to points here for comparison with AX tree points.
                        cx = (bounds.get("x", 0) + bounds.get("width", 0) / 2)
                        cy = (bounds.get("y", 0) + bounds.get("height", 0) / 2)

                        # Use a small heuristic: if cx > screen_width, it's definitely pixels
                        log_w, _ = macos_driver.get_screen_size()
                        if cx > log_w and scale > 1.0:
                            cx /= scale
                            cy /= scale

                        for ax_el in ax_elements:
                            ax_bounds = ax_el.get("bounds", [])
                            if len(ax_bounds) == 4:
                                ax_x, ax_y, ax_w, ax_h = ax_bounds
                                if ax_x <= cx <= ax_x + ax_w and ax_y <= cy <= ax_y + ax_h:
                                    if "path" in ax_el:
                                        el_data["os_identifier"] = ax_el["path"]
                                    break
            except Exception as e:
                logger.debug(f"[AtlasEngine] AX Merge failed during observation: {e}")

        try:
            # We use 'name' or 'bundle_id' for app_name as default
            app_model = AtlasApp(
                app_name=bundle_id,
                bundle_id=bundle_id,
                platform=platform,
                version_hash=version_hash
            )
            state_id = self._generate_state_id(bundle_id, window_title)

            # Elements are passed as standardized dicts from the event payload
            elements = [AtlasElement.model_validate(e) for e in elements_data]

            state = AtlasState(
                state_id=state_id,
                window_title=window_title,
                elements=elements,
                screenshot_hash=screenshot_hash
            )
            app_model.add_state(state)

            await self.store.save_app_model(app_model)
            logger.info(f"[AtlasEngine] Background mapped state '{window_title}' for {bundle_id} (Version: {version_hash or 'Legacy'})")

        except Exception as e:
            logger.error(f"[AtlasEngine] Failed to index observed UI tree for {bundle_id}: {e}")

    async def query_app_atlas(self, bundle_ids: str | list[str] = None, state_id: str = None, platform: str = "macos") -> str:
        """
        Formats a structural summary of the app map or details of a specific state.
        Args:
            bundle_ids: One or more application IDs to summarize.
            state_id: If provided, returns the detailed element list for this specific state.
            platform: Filter by platform.
        """
        if state_id:
            # Handle detailed state query
            # We need to find the bundle_id for this state_id if not provided,
            # but usually it's better to require bundle_id for performance if possible.
            # For simplicity in tools, we'll try to find it.
            if isinstance(bundle_ids, str):
                target_bundle = bundle_ids
            else:
                target_bundle = bundle_ids[0] if bundle_ids else None

            if not target_bundle:
                # Fallback: list apps to find matches if needed, but Neo4j store can find by state_id
                # Neo4jAtlasStore.get_state_detail already takes bundle_id.
                return "Error: bundle_id is required when querying state_id."

            detail = await self.store.get_state_detail(target_bundle, state_id, platform=platform)
            if not detail:
                return f"No details found for state '{state_id}' in app '{target_bundle}'."

            try:
                return render_template(
                    "core/memory/atlas_detail.prompt.j2",
                    window_title=detail.get('window_title', 'Unknown'),
                    state_id=state_id,
                    bundle_id=target_bundle,
                    elements=detail.get('elements', [])
                )
            except Exception as e:
                logger.error(f"Failed to render Atlas detail template: {e}")
                # Minimal fallback
                return f"UI State Detail: {detail.get('window_title')} (ID: {state_id})"

        if not bundle_ids:
            return "Please provide bundle_id(s) or a state_id."

        if isinstance(bundle_ids, str):
            bundle_ids = [bundle_ids]

        all_outputs = []
        for bundle_id in bundle_ids:
            summary = await self.store.get_app_summary(bundle_id, platform=platform)
            if not summary:
                all_outputs.append(f"No atlas data found for application: {bundle_id}")
                continue

            # Phase 6: Version Drift Detection
            is_stale = False
            stored_hash = summary.get("version_hash", "")
            if platform == "android" and stored_hash:
                try:
                    from app.infrastructure.drivers.adb import adb_driver
                    pkg_meta = adb_driver.get_package_info(bundle_id)
                    if pkg_meta and "error" not in pkg_meta:
                        from app.core.atlas.models import AtlasApp
                        dummy = AtlasApp(app_name=bundle_id, bundle_id=bundle_id, platform="android")
                        live_hash = dummy.compute_version_hash(
                            str(pkg_meta.get("version_name", "0")),
                            str(pkg_meta.get("last_update_time", "0"))
                        )
                        if live_hash != stored_hash:
                            is_stale = True
                except Exception:
                    pass

            transitions = await self.store.get_transitions_summary(bundle_id, platform=platform)

            output = [
                f"App UI Atlas: {summary['app_name']} ({bundle_id})",
            ]

            if is_stale:
                output.append("> [!WARNING]")
                output.append("> **STALE DATA DETECTED**: The application version has changed since the last map was created. Coordinates may be inaccurate. **Priority: Use real-time perception (Vision/OCR).**")

            output.append(f"**Known States ({summary['state_count']})**:")

            for state in summary["states"]:
                output.append(f"- {state['title']} (ID: {state['id']})")

            if transitions:
                output.append("\n**Known Transitions**:")
                for t in transitions:
                    output.append(f"- {t['from_state']} --[{t['type']}: {t['label']}]--> {t['to_state']}")

            all_outputs.append("\n".join(output))

        final_result = "\n\n---\n\n".join(all_outputs)
        final_result += "\n\n💡 Tip: Use `query_app_atlas(bundle_ids='...', state_id='...')` to see all buttons/inputs in a state."
        return final_result

    async def get_app_strategy(self, bundle_id: str, platform: str = "android") -> AppStrategy | None:
        """
        Get interaction strategy for a dynamic app on a specific platform.
        Returns None if no strategy exists (not a dynamic app or not observed).
        """
        try:
            return await AtlasStrategyStore.get_strategy(bundle_id, platform)
        except Exception as e:
            logger.error(f"[AtlasEngine] Failed to get strategy for {platform}:{bundle_id}: {e}")
            return None

    async def is_dynamic_app(self, bundle_id: str, platform: str = "android") -> bool:
        """Check if an app is marked as dynamic (coordinate-unstable) for a specific platform."""
        try:
            dynamic_apps = await DynamicAppTriage.get_dynamic_apps(platform)
            return bundle_id in dynamic_apps
        except Exception as e:
            logger.debug(f"[AtlasEngine] Dynamic app check failed: {e}")
            return False

    async def list_apps(self) -> str:
        """
        Returns a formatted markdown directory of all apps with available UI maps.
        """
        apps = await self.store.list_apps()
        if not apps:
            return "No applications have UI Maps (Atlas) recorded yet. Atlas is built automatically as you perform tasks."

        output = ["App Atlas Directory", "The following applications have structural UI maps available:"]
        for app in apps:
            output.append(f"- **{app['app_name']}** (Bundle ID: `{app['bundle_id']}`, Platform: {app['platform']})")

        output.append("\n💡 You can use `query_app_atlas(bundle_id)` to retrieve detailed maps for any of these.")
        return "\n".join(output)

    async def clear_atlas(self) -> None:
        """
        Permanently deletes all historical Atlas data from the store.
        """
        logger.warning("[AtlasEngine] Permanently clearing all historical data...")
        await self.store.clear_all_data()

    def _generate_state_id(self, bundle_id: str, window_title: str) -> str:
        """Generates a stable semantic ID for a UI state."""
        # Use utility function for hash computation
        h = compute_state_id(bundle_id, window_title, length=8)
        # Clean title for readability
        clean_title = "".join(c for c in window_title if c.isalnum()).lower()[:20]
        return f"{clean_title}_{h}"

    async def _save_dynamic_app_strategy(
        self,
        bundle_id: str,
        platform: str,
        infrastructure: list[AtlasElement],
        window_title: str
    ) -> None:
        """
        Save or update strategy for a dynamic app.
        Extracts infrastructure elements and creates default strategies.
        """
        try:
            # Get existing strategy or create new
            strategy = await AtlasStrategyStore.get_strategy(bundle_id)
            if not strategy:
                strategy = AppStrategy(
                    bundle_id=bundle_id,
                    platform=platform,
                )

            # Update infrastructure from current observation
            infra_list = []
            for elem in infrastructure:
                infra_list.append({
                    "role": elem.role,
                    "label": elem.label,
                    "resource_id": elem.os_identifier,
                    "bounds": elem.bounds,
                    "category": elem.element_category,
                })

            strategy.infrastructure = infra_list

            # Add default strategies based on observed infrastructure
            existing_targets = {s.target_element for s in strategy.strategies}

            # Check for search bar
            has_search = any(
                e.element_category == "static_navigation_top" and
                ("search" in e.label.lower() or "搜索" in e.label)
                for e in infrastructure
            )
            if has_search and "find_content" not in existing_targets:
                strategy.strategies.append(InteractionStrategy(
                    strategy_type="search_then_click",
                    target_element="find_content",
                    parameters={
                        "description": "Use search bar to find dynamic content",
                        "fallback": "scroll_until_visible"
                    }
                ))

            # Check for back button
            has_back = any(
                "back" in e.label.lower() or "返回" in e.label
                for e in infrastructure
            )
            if has_back and "go_back" not in existing_targets:
                strategy.strategies.append(InteractionStrategy(
                    strategy_type="static_click",
                    target_element="go_back",
                    parameters={"description": "Click back button"}
                ))

            # Update hints
            strategy.hints["has_search_bar"] = has_search
            strategy.hints["coordinate_unstable"] = True
            strategy.hints["last_observed_title"] = window_title

            # Save to cache
            await AtlasStrategyStore.save_strategy(strategy)
            logger.debug(f"[AtlasEngine] Saved strategy for {bundle_id}")

        except Exception as e:
            logger.error(f"[AtlasEngine] Failed to save strategy: {e}")

    async def _store_dynamic_app_infrastructure(
        self,
        bundle_id: str,
        window_title: str,
        platform: str,
        elements_data: list[dict],
        version_hash: str,
        screenshot_hash: str
    ) -> None:
        """
        For dynamic apps (WeChat, etc), only store infrastructure elements.
        Infrastructure = static UI like toolbars, search bars, navigation.
        Does NOT store scrolling lists, chat items, etc.
        """
        try:
            # Convert and classify elements
            elements = []
            infrastructure_elements = []

            for e_data in elements_data:
                element = AtlasElement.model_validate(e_data)
                category = self._classify_element_category(element, platform)
                element.element_category = category

                # Mark if this is infrastructure (static, reliable)
                element.is_infrastructure = category in ["static", "static_navigation", "static_toolbar"]

                # For dynamic apps, only store infrastructure with coordinates
                if element.is_infrastructure:
                    element.coordinate_confidence = 0.9
                    infrastructure_elements.append(element)
                else:
                    # Mark dynamic elements with low coordinate confidence
                    element.coordinate_confidence = 0.0

                elements.append(element)

            if not infrastructure_elements:
                logger.debug(f"[AtlasEngine] No infrastructure elements found for {bundle_id}")
                return

            # Store with a special marker state
            app_model = AtlasApp(
                app_name=bundle_id,
                bundle_id=bundle_id,
                platform=platform,
                version_hash=version_hash,
                is_dynamic=True  # Mark as dynamic app
            )

            state_id = self._generate_state_id(bundle_id, f"{window_title}_infra")

            state = AtlasState(
                state_id=state_id,
                window_title=window_title,
                elements=infrastructure_elements,  # Only infrastructure
                screenshot_hash=screenshot_hash,
                is_infrastructure_only=True  # Marker for query logic
            )

            app_model.add_state(state)
            await self.store.save_app_model(app_model)

            # Phase 6: Also save as strategy for easier querying
            await self._save_dynamic_app_strategy(
                bundle_id=bundle_id,
                platform=platform,
                infrastructure=infrastructure_elements,
                window_title=window_title
            )

            logger.info(
                f"[AtlasEngine] Stored {len(infrastructure_elements)} infrastructure elements "
                f"for dynamic app '{bundle_id}'"
            )

        except Exception as e:
            logger.error(f"[AtlasEngine] Failed to store dynamic app infrastructure: {e}")

    def _classify_element_category(self, element: AtlasElement, platform: str) -> str:
        """
        Classify element as static/dynamic/container based on properties.
        """
        # Get properties from metadata
        metadata = element.metadata or {}

        if platform == "android":
            return self._classify_android_element(element, metadata)
        else:
            return self._classify_macos_element(element, metadata)

    def _classify_android_element(self, element: AtlasElement, metadata: dict) -> str:
        """Android-specific classification."""
        class_name = metadata.get("class", "").lower()
        scrollable = metadata.get("scrollable", False)
        resource_id = metadata.get("resource_id", "").lower()

        # 1. Check for scrollable containers
        SCROLLABLE_CLASSES = [
            "recyclerview", "listview", "scrollview",
            "viewpager", "horizontalscrollview", "webview"
        ]

        if scrollable or any(c in class_name for c in SCROLLABLE_CLASSES):
            if "recyclerview" in class_name:
                return "container_recyclerview"
            elif "listview" in class_name:
                return "container_listview"
            elif "scrollview" in class_name:
                return "container_scrollview"
            return "container_scrollable"

        # 2. Check for static navigation elements by position
        bounds = element.bounds or {}
        y = bounds.get("y", 0)
        height = bounds.get("height", 0)
        y_bottom = y + height

        # Top navigation (toolbar, actionbar)
        if y < 200 and ("toolbar" in class_name or "actionbar" in resource_id or element.clickable):
            return "static_navigation_top"

        # Bottom navigation
        if y_bottom > 1800 and element.clickable:
            return "static_navigation_bottom"

        # 3. Static interactive elements
        if element.clickable or element.role in ["button", "input"]:
            return "static"

        # 4. Text elements
        if element.label and "textview" in class_name:
            return "static_text"

        return "unknown"

    def _classify_macos_element(self, element: AtlasElement, metadata: dict) -> str:
        """macOS-specific classification."""
        role = element.role.lower() if element.role else ""
        ax_path = element.ax_path.lower() if element.ax_path else ""

        # 1. Check for scrollable containers
        if "scroll" in role or "scrollarea" in role:
            return "container_scrollable"

        if "table" in role or "outline" in role:
            return "container_table"

        # 2. Toolbar elements
        if "toolbar" in role or "toolbar" in ax_path:
            return "static_toolbar"

        # 3. Menu/Navigation
        if "menu" in role or "menubar" in ax_path:
            return "static_navigation"

        # 4. Static interactive
        if "button" in role or "textfield" in role:
            return "static"

        return "unknown"
