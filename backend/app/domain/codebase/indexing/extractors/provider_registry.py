"""
Centralized registry for language-specific semantic providers.
Singleton pattern ensures all extractors share the same provider instances.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sem_provider import LanguageSemanticProvider


class SemanticProviderRegistry:
    """
    Singleton registry for LanguageSemanticProvider instances.
    Ensures APIExtractor and DBExtractor share the same provider objects.
    """
    _instance = None
    _providers: dict[str, "LanguageSemanticProvider"] = {}
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_initialized(self):
        """Lazily initialize default providers."""
        if self._initialized:
            return

        # Core language providers
        from .csharp_provider import CSharpSemanticProvider
        from .go_provider import GoSemanticProvider
        from .java_provider import JavaSemanticProvider

        # Extended language providers
        from .kotlin_provider import KotlinSemanticProvider
        from .php_provider import PHPSemanticProvider
        from .python_provider import PythonSemanticProvider
        from .ruby_provider import RubySemanticProvider
        from .rust_provider import RustSemanticProvider
        from .sql_provider import SQLSemanticProvider
        from .swift_provider import SwiftSemanticProvider
        from .ts_js_provider import TypeScriptSemanticProvider, JavaScriptSemanticProvider
        from .vue_provider import VueSemanticProvider

        # Register core providers
        self.register("python", PythonSemanticProvider())
        self.register("typescript", TypeScriptSemanticProvider())
        self.register("javascript", JavaScriptSemanticProvider())
        self.register("java", JavaSemanticProvider())
        self.register("go", GoSemanticProvider())
        self.register("csharp", CSharpSemanticProvider())

        # Register extended providers
        self.register("php", PHPSemanticProvider())
        self.register("ruby", RubySemanticProvider())
        self.register("rust", RustSemanticProvider())
        self.register("kotlin", KotlinSemanticProvider())
        self.register("swift", SwiftSemanticProvider())
        self.register("sql", SQLSemanticProvider())
        self.register("vue", VueSemanticProvider())

        self._initialized = True

    def register(self, lang_name: str, provider: "LanguageSemanticProvider"):
        """Register a provider for a language."""
        self._providers[lang_name] = provider

    def get(self, lang_name: str) -> "LanguageSemanticProvider | None":
        """Get provider for a language, initializing if needed."""
        self._ensure_initialized()
        return self._providers.get(lang_name)

    def get_all(self) -> dict[str, "LanguageSemanticProvider"]:
        """Get all registered providers."""
        self._ensure_initialized()
        return self._providers.copy()


# Global singleton instance
semantic_provider_registry = SemanticProviderRegistry()
