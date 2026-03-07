import logging
import re
from typing import List, Optional

from app.core.context import ContextManager
from app.core.environment.state import get_awakened_state
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


def resolve_focus(text: str, current_focus: Optional[List[str]] = None) -> List[str]:
    """
    Resolves the entity focus from a piece of text (user message).
    This decouples the engine from platform-specific details (macOS, Android).
    """
    if not text:
        return current_focus or []

    msg_lower = text.lower()
    focus_hints = []

    # 1. Dynamic App Matching (from Environment Awareness)
    state = get_awakened_state()
    if state:
        known_app_names = set()

        # a) Knowledge-Driven Matching (Memory Core)
        # We parse the retrieved Atlas concepts. This works even if devices are offline.
        for concept in state.relevant_concepts:
            # concept.name is typically formatted like "android_layout:WeChat (com.tencent.mm)"
            name_part = concept.name.split(":", 1)[-1].strip()
            # Extract the human-readable app name before the parentheses
            if "(" in name_part:
                clean_name = name_part.split("(")[0].strip().lower()
                if len(clean_name) > 2:
                    known_app_names.add(clean_name)
            
            # Extract common tokens from the package name or full string
            tokens = re.findall(r'\b[a-z]+[a-z0-9_]*\b', name_part.lower())
            for t in tokens:
                if len(t) > 2 and t not in ["com", "android", "layout", "macos", "app", "web"]:
                    known_app_names.add(t)

        # b) Hardware-Driven Matching (Live Profiles)
        # MacOS: Get installed apps
        if state.macos:
            known_app_names.update([app.lower() for app in state.macos.installed_apps])

        # Android: Get installed package names and short names
        for device in state.android_devices:
            for pkg in device.installed_packages:
                # Extract the last part of the package name (e.g. com.tencent.mm -> mm)
                short_name = pkg.split('.')[-1].lower()
                known_app_names.add(pkg.lower())
                if len(short_name) > 2:
                    known_app_names.add(short_name)

        # Remove generic noise from pool
        noise = {"the", "and", "app", "open", "close", "run"}
        known_app_names = known_app_names - noise

        # Heuristic Match
        for app_name in known_app_names:
            if re.search(rf'(?i)\b{re.escape(app_name)}\b', msg_lower) or app_name in msg_lower:
                focus_hints.append(app_name)

    # 2. Dynamic Pronoun Resolution (via i18n)
    pronouns = i18n.get("common.pronouns", default=["it", "this", "that"])
    has_pronoun = any(re.search(rf'\b{re.escape(p)}\b', msg_lower) for p in pronouns)

    if focus_hints:
        # New explicit focus detected from environment
        return list(set(focus_hints))
    elif has_pronoun and current_focus:
        # Pronoun detected ("it", "那个"), maintain existing focus
        return current_focus

    # No clear new focus or pronoun; we return empty or keep old (decay logic is optional)
    return current_focus or []


def classify_ecosystems(focus: List[str]) -> set[str]:
    """
    Classifies a list of focused apps into ecosystems (android, macos, web).
    Used for tool masking and context prioritization.
    """
    if not focus:
        return set()

    ecosystems = set()
    state = get_awakened_state()

    # Universal Heuristics for Web apps
    web_keywords = {"chrome", "safari", "browser", "firefox", "edge", "网页", "浏览器"}

    # Mobile intent keywords — generic terms that imply mobile/Android operation.
    # These apply ONLY when there are real Android devices connected, so we don't
    # incorrectly force android mode on a pure-desktop environment.
    mobile_intent_keywords = {
        "phone", "手机", "app", "应用", "android", "mobile",
        # Common Chinese mobile apps that live exclusively on Android/iOS:
        "闲鱼", "淘宝", "微信", "抖音", "支付宝", "京东", "拼多多",
        "xianyu", "taobao", "wechat", "douyin", "alipay",
    }

    # Fast-path: if any focus item matches a mobile intent keyword AND
    # there are Android devices online, declare android ecosystem immediately.
    if state and state.android_devices:
        for item in focus:
            item_lower = item.lower()
            if item_lower in mobile_intent_keywords or any(
                kw in item_lower for kw in mobile_intent_keywords
            ):
                logger.debug(
                    f"[EcosystemClassifier] Mobile intent keyword '{item}' matched "
                    f"with {len(state.android_devices)} device(s) online → android"
                )
                ecosystems.add("android")
                break

    for item in focus:
        item_lower = item.lower()
        
        # 1. Universal Check Web
        if any(kw in item_lower for kw in web_keywords):
            ecosystems.add("web")
            
        if not state:
            continue
            
        # 2. Knowledge-Driven Ecosystem Detection (Phase 4)
        # Instead of probing hardware, we rely on the Atlas concepts retrieved from Memory.
        # This matches semantics like "android_layout:WeChat" -> Ecosystem: Android
        concept_matched = False
        for concept in state.relevant_concepts:
            c_name = concept.name.lower()
            if item_lower in c_name:
                concept_matched = True
                if "android" in c_name or "mobile" in c_name or "apk" in c_name:
                    ecosystems.add("android")
                if "macos" in c_name or "desktop" in c_name:
                    ecosystems.add("macos")
                if "web" in c_name or "browser" in c_name:
                    ecosystems.add("web")
                    
        # 3. Fallback to active hardware probe if memory is cold
        if not concept_matched:
            if "android" not in ecosystems:
                for device in state.android_devices:
                    if item_lower in [pkg.lower() for pkg in device.installed_packages] or \
                       any(item_lower == pkg.split('.')[-1].lower() for pkg in device.installed_packages):
                        ecosystems.add("android")
                        break
                        
            if "macos" not in ecosystems and state.macos:
                if any(item_lower in app.lower() for app in state.macos.installed_apps):
                    ecosystems.add("macos")

    return ecosystems
