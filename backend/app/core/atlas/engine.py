import asyncio
import logging
from typing import Any

from app.core.atlas.adapters.graph_store import GraphAtlasStore
from app.core.atlas.models import AtlasApp, AtlasElement, AtlasState
from app.core.atlas.ports.store import IAtlasStore
from app.core.atlas.strategy import AppStrategy, AtlasStrategyStore, InteractionStrategy
from app.core.config import settings
from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
from app.utils import render_template
from app.core.file import compute_state_id
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.infrastructure.database.vector import get_vector_store

logger = logging.getLogger(__name__)


class AtlasEngine:
    """
    Core Cognitive Engine for Spatial Memory (App Atlas).
    Handles data accumulation (ingestion from EventBus), graph persistence, 
    and retrieval for Agent Tools.

    NOTE: In embedded mode, Atlas persistence is available via FileGraphDriver.
    """

    def __init__(self, store: IAtlasStore = None):
        if settings.EMBEDDED_MODE and store is None:
            logger.info("[AtlasEngine] Embedded mode enabled: Using FileGraph storage for Atlas.")
        self.store = store or GraphAtlasStore()

    async def on_ui_tree_observed(self, event: Any) -> None:
        """
        Background mapping of observed UI trees into the App Atlas.
        """
        bundle_id = event.data.get("bundle_id")
        window_title = event.data.get("window_title")
        platform = event.data.get("platform", "macos")
        elements_data = event.elements
        screenshot_hash = event.data.get("screenshot_hash")
        version_hash = event.data.get("version_hash", "")

        if not bundle_id or bundle_id == "unknown" or not elements_data:
            return

        # 1. Check if this is a dynamic (coordinate-unstable) app
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

        try:
            # Standard app mapping
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
            logger.info(f"[AtlasEngine] Background mapped state '{window_title}' for {bundle_id}")

        except Exception as e:
            logger.error(f"[AtlasEngine] Failed to index observed UI tree for {bundle_id}: {e}")

    async def query_app_atlas(self, bundle_ids: str | list[str] | None = None, state_id: str | None = None, platform: str = "macos") -> str:
        """
        Formats a structural summary of the app map or details of a specific state.
        """
        if state_id:
            # For detailed state query, we need to know which app it belongs to.
            # In AtlasEngine, state_id is usually retrieved from a bundle_id summary.
            # We'll use the first bundle_id as context if available.
            target_bundle = bundle_ids[0] if isinstance(bundle_ids, list) and bundle_ids else (bundle_ids if isinstance(bundle_ids, str) else None)
            
            if not target_bundle:
                # If no bundle_id provided, we attempt to find which app has this state_id
                apps = await self.store.list_apps()
                for app_info in apps:
                    detail = await self.store.get_state_detail(app_info.bundle_id, state_id, platform=platform)
                    if detail:
                        target_bundle = app_info.bundle_id
                        break
            
            if not target_bundle:
                return f"Error: State '{state_id}' not found in any application."

            detail = await self.store.get_state_detail(target_bundle, state_id, platform=platform)
            if not detail:
                return f"Error: Details for state '{state_id}' not found."

            return render_template(
                "core/memory/atlas_detail.prompt.j2",
                bundle_id=target_bundle,
                state_id=state_id,
                window_title=detail.window_title,
                elements=[e for e in detail.elements if not e.get("is_infrastructure", False)],
                infrastructure=[e for e in detail.elements if e.get("is_infrastructure", False)]
            )

        # Multi-app summary mode
        if not bundle_ids:
            # If no bundle_ids, list all apps in the atlas
            apps = await self.store.list_apps()
            if not apps:
                return "Your Atlas memory is currently empty. Perform tasks to map application UIs."
            
            return render_template(
                "core/memory/atlas_list.prompt.j2",
                apps=[{"bundle_id": a.bundle_id, "name": a.app_name, "platform": a.platform} for a in apps]
            )

        if isinstance(bundle_ids, str):
            bundle_ids = [bundle_ids]

        all_outputs = []
        for bid in bundle_ids:
            summary = await self.store.get_app_summary(bid, platform=platform)
            if not summary:
                all_outputs.append(f"### {bid}\nNo UI map available for this application.")
                continue

            output = [f"### UI Map for {bid} ({summary.platform})"]
            output.append(f"- **States**: {summary.state_count} screens mapped")
            
            if summary.states:
                output.append("- **Recorded States**: " + ", ".join(summary.states[:20])) # List of state IDs

            all_outputs.append("\n".join(output))
        
        if not all_outputs:
            return "No UI map available for the requested applications."

        final_result = "\n\n---\n\n".join(all_outputs)
        final_result += "\n\n💡 Tip: Use `query_app_atlas(bundle_ids='...', state_id='...')` to see all buttons/inputs in a state."
        return final_result

    async def list_apps(self) -> str:
        """
        Returns a formatted markdown directory of all apps with available UI maps.
        """
        apps = await self.store.list_apps()
        if not apps:
            return "No applications have UI Maps recorded yet."

        output = ["App Atlas Directory", "The following applications have structural UI maps available:"]
        for app in apps:
            output.append(f"- **{app.app_name}** (Bundle ID: `{app.bundle_id}`, Platform: {app.platform})")

        return "\n".join(output)

    async def get_app_strategy(self, bundle_id: str, platform: str = "android") -> AppStrategy | None:
        """
        Retrieves the interaction strategy for a specific app.
        """
        from app.core.atlas.config_manager import AtlasConfigManager
        data = await AtlasConfigManager.get_app_strategy(bundle_id, platform)
        if data:
            return AppStrategy.model_validate(data)
        return None

    async def is_dynamic_app(self, bundle_id: str, platform: str = "android") -> bool:
        """
        Checks if an application is classified as dynamic (coordinate-unstable).
        """
        from app.core.atlas.config_manager import AtlasConfigManager
        return await AtlasConfigManager.is_dynamic_app(bundle_id, platform)

    async def resolve_spatial_element(
        self,
        bundle_id: str,
        element_name: str,
        platform: str = "macos"
    ) -> dict | None:
        """
        Unified high-level method to resolve an element using Atlas intelligence.

        Priority:
          1. Infrastructure elements from strategy cache (dynamic apps)
          2. Interaction strategies (search/scroll, dynamic apps)
          3. Historical spatial memory from standard states (static apps)

        Returns a dict with one of:
          - {"x": int, "y": int, "source": str}          → direct coordinates
          - {"strategy": str, "parameters": dict, "source": str}  → interaction recipe
          - None  → not found
        """
        try:
            is_dynamic = await self.is_dynamic_app(bundle_id, platform)
            if is_dynamic:
                strategy = await self.get_app_strategy(bundle_id, platform)
                if strategy:
                    infra_elem = strategy.get_infrastructure_element(element_name)
                    if infra_elem and infra_elem.get("bounds"):
                        bounds = infra_elem["bounds"]
                        return {
                            "x": bounds.get("x", 0),
                            "y": bounds.get("y", 0),
                            "source": "atlas_strategy_infra"
                        }
                    strat = strategy.get_strategy_for(element_name)
                    if strat:
                        return {
                            "strategy": strat.strategy_type,
                            "parameters": strat.parameters,
                            "source": "atlas_strategy"
                        }

            # Standard Spatial Memory Fallback (static apps)
            summary = await self.store.get_app_summary(bundle_id, platform=platform)
            if summary and summary.states:
                for state in summary.states[:3]:
                    detail = await self.store.get_state_detail(
                        bundle_id, state["id"], platform=platform
                    )
                    if detail:
                        for el in detail.elements:
                            el_name = str(el.get("label") or el.get("text") or el.get("name") or "").lower()
                            if element_name.lower() in el_name:
                                if el.get("x") is not None and el.get("y") is not None:
                                    return {
                                        "x": el["x"],
                                        "y": el["y"],
                                        "source": "atlas_memory"
                                    }

            # 4. Learned Skills Fallback (Task-specific memory)
            # This covers mappings like "SearchButton" -> (x, y) learned from past traces
            try:
                embedder = EmbedderFactory.get_embedder()
                vector = await embedder.embed_query(element_name)
                
                if not vector:
                    logger.debug(f"[AtlasEngine] Skipping semantic search for {element_name}: empty vector")
                    return None
                
                vector_store = get_vector_store()
                skills = await asyncio.to_thread(
                    vector_store.search_skills,
                    query_vector=vector,
                    bundle_id=bundle_id,
                    platform=platform,
                    top_k=3
                )
                logger.info(f"[AtlasEngine] Found {len(skills)} skills for {element_name} in {bundle_id}")
                
                if skills:
                    for skill in skills:
                        logger.info(f"[AtlasEngine] Checking skill: {skill.get('name')} (Score: {skill.get('score')})")
                        # Priority 1: Exact or substring name/label match
                        s_name = str(skill.get("name") or "").lower()
                        s_label = str(skill.get("label") or "").lower()
                        if element_name.lower() in s_name or element_name.lower() in s_label:
                            if skill.get("x") is not None and skill.get("y") is not None and skill["x"] >= 0:
                                return {
                                    "x": skill["x"],
                                    "y": skill["y"],
                                    "source": "atlas_skill"
                                }
                    
                    # Priority 2: High confidence semantic match (> 0.9)
                    if len(skills) > 0 and skills[0].get("score", 0) > 0.9:
                        if skills[0].get("x") is not None and skills[0].get("y") is not None and skills[0]["x"] >= 0:
                            return {
                                "x": skills[0]["x"],
                                "y": skills[0]["y"],
                                "source": "atlas_skill_semantic"
                            }
            except Exception as se:
                import traceback
                logger.debug(f"[AtlasEngine] Skill search failed: {se}\n{traceback.format_exc()}")
        except Exception as e:
            logger.debug(f"[AtlasEngine] resolve_spatial_element failed: {e}")
        return None

    async def clear_atlas(self) -> None:
        """
        Permanently deletes all historical Atlas data from the store.
        """
        logger.warning("[AtlasEngine] Permanently clearing all historical data...")
        await self.store.clear_all_data()

    def _generate_state_id(self, bundle_id: str, window_title: str, is_infra: bool = False) -> str:
        """Generates a stable semantic ID for a UI state."""
        if is_infra:
            clean_title = "".join(c for c in window_title if c.isalnum()).lower()[:20]
            return f"{clean_title}_infra"
            
        h = compute_state_id(bundle_id, window_title, length=8)
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
        Updates the interaction strategy for a dynamic app based on its infrastructure.
        """
        try:
            strategy = await AtlasStrategyStore.get_strategy(bundle_id, platform)
            if not strategy:
                strategy = AppStrategy(bundle_id=bundle_id, platform=platform)

            # Update infrastructure elements (labels/roles only, no coords)
            infra_list = []
            for e in infrastructure:
                infra_list.append({
                    "label": e.label,
                    "role": e.role,
                    "element_category": e.element_category
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

            state_id = self._generate_state_id(bundle_id, window_title, is_infra=True)

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

    def _classify_android_element(self, element: AtlasElement, metadata: Any) -> str:
        """Android-specific classification."""
        # Ensure we have a dict for uniform access
        m = metadata.model_dump() if hasattr(metadata, "model_dump") else metadata
        
        class_name = str(m.get("class") or m.get("class_name") or "").lower()
        scrollable = m.get("scrollable", False)
        resource_id = str(m.get("resource_id") or "").lower()

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
        b = element.bounds.model_dump() if element.bounds else {}
        y = b.get("y", 0)
        height = b.get("height", 0)
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

    def _classify_macos_element(self, element: AtlasElement, metadata: Any) -> str:
        """macOS-specific classification."""
        # Ensure we have a dict for uniform access (reserved for future use)
        m = metadata.model_dump() if hasattr(metadata, "model_dump") else metadata
        
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
