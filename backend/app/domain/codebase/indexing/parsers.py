import logging

from tree_sitter import Language, Parser

from app.constants import EXTENSION_MAP

logger = logging.getLogger(__name__)


class ParserRegistry:
    """
    Dynamic registry for Tree-sitter parsers.
    Supports pluggable language loaders.
    """

    def __init__(self):
        self.parsers: dict[str, tuple[Parser, Language]] = {}
        self.languages: dict[str, Language] = {}
        self._loaders: dict[str, callable] = {}
        # Derive dot-less map from constants
        self.lang_map = {ext.lstrip("."): lang for ext, lang in EXTENSION_MAP.items()}
        # Add common aliases if missing
        self.lang_map.update({
            "cpp": "cpp",
            "csharp": "csharp",
            "javascript": "javascript",
            "typescript": "typescript",
            "python": "python",
            "tsx": "tsx",
            "jsx": "javascript"  # Adjust if jsx loader is added
        })
        self._register_default_loaders()

    def _register_default_loaders(self):
        def load_python():
            import tree_sitter_python

            return tree_sitter_python.language()

        def load_go():
            import tree_sitter_go

            return tree_sitter_go.language()

        def load_java():
            import tree_sitter_java

            return tree_sitter_java.language()

        def load_cpp():
            from tree_sitter_language_pack import get_language

            return get_language("cpp")

        def load_c():
            from tree_sitter_language_pack import get_language

            return get_language("c")

        def load_rust():
            import tree_sitter_rust

            return tree_sitter_rust.language()

        def load_php():
            import tree_sitter_php

            return tree_sitter_php.language_php()

        def load_ruby():
            import tree_sitter_ruby

            return tree_sitter_ruby.language()

        def load_csharp():
            import tree_sitter_c_sharp

            return tree_sitter_c_sharp.language()

        def load_js():
            import tree_sitter_javascript

            return tree_sitter_javascript.language()

        def load_ts():
            import tree_sitter_typescript

            return tree_sitter_typescript.language_typescript()

        def load_tsx():
            import tree_sitter_typescript

            return tree_sitter_typescript.language_tsx()

        def load_kotlin():
            import tree_sitter_kotlin

            return tree_sitter_kotlin.language()

        def load_swift():
            import tree_sitter_swift

            return tree_sitter_swift.language()

        def load_sql():
            import tree_sitter_sql

            return tree_sitter_sql.language()

        def load_html():
            import tree_sitter_html

            return tree_sitter_html.language()

        def load_vue():
            from tree_sitter_language_pack import get_language

            return get_language("vue")

        def load_bash():
            from tree_sitter_language_pack import get_language

            return get_language("bash")

        def load_yaml():
            import tree_sitter_yaml

            return tree_sitter_yaml.language()

        # Core languages
        self.register_loader("python", load_python)
        self.register_loader("go", load_go)
        self.register_loader("java", load_java)
        self.register_loader("cpp", load_cpp)
        self.register_loader("c", load_c)
        self.register_loader("rust", load_rust)
        self.register_loader("php", load_php)
        self.register_loader("ruby", load_ruby)
        self.register_loader("csharp", load_csharp)
        self.register_loader("javascript", load_js)
        self.register_loader("typescript", load_ts)
        self.register_loader("tsx", load_tsx)
        # Extended languages
        self.register_loader("kotlin", load_kotlin)
        self.register_loader("swift", load_swift)
        self.register_loader("sql", load_sql)
        self.register_loader("html", load_html)  # For Vue SFC parsing
        self.register_loader("vue", load_vue)
        self.register_loader("bash", load_bash)
        self.register_loader("yaml", load_yaml)

    def register_loader(self, lang_name: str, loader_func: callable):
        """Register a lazy loader for a specific language."""
        self._loaders[lang_name] = loader_func

    def _ensure_language(self, lang_name: str) -> bool:
        """Dynamically load a language if a loader exists."""
        if lang_name in self.languages:
            return True

        if lang_name in self._loaders:
            try:
                loader = self._loaders.pop(lang_name)
                loaded = loader()
                if isinstance(loaded, Language):
                    LANG = loaded
                else:
                    LANG = Language(loaded)
                parser = Parser(LANG)
                self.languages[lang_name] = LANG

                # Link all extensions mapped to this language to this parser
                for ext, mapped_lang in self.lang_map.items():
                    if mapped_lang == lang_name:
                        self.parsers[ext] = (parser, LANG)

                # Also ensure the lang_name itself is in parsers for direct lookups
                self.parsers[lang_name] = (parser, LANG)
                return True
            except Exception as e:
                logger.error(f"Failed to dynamic load {lang_name}: {e}")
        return False

    def get_parser(self, extension: str) -> tuple[Parser, Language] | None:
        """
        Get (Parser, Language) tuple for a file extension.
        Extension should be without dot (e.g. 'py').
        """
        extension = extension.lower().lstrip(".")
        lang_name = self.lang_map.get(extension)

        if lang_name and self._ensure_language(lang_name):
            return self.parsers.get(extension)

        return None

    def get_language_key(self, extension: str) -> str | None:
        """
        Get generic language key (e.g. 'python') for an extension.
        """
        return self.lang_map.get(extension.lower().lstrip("."))


# Global Instance
parser_registry = ParserRegistry()
