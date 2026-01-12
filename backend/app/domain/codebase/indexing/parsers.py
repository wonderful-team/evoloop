import logging

# Language bindings
import tree_sitter_c_sharp
import tree_sitter_cpp
import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_php
import tree_sitter_python
import tree_sitter_ruby
import tree_sitter_rust
import tree_sitter_typescript
from tree_sitter import Language, Parser

logger = logging.getLogger(__name__)


class ParserRegistry:
    """
    Central registry for Tree-sitter parsers.
    """

    def __init__(self):
        self.parsers: dict[str, tuple[Parser, Language]] = {}
        self.languages: dict[str, Language] = {}
        self.lang_map = {
            "py": "python", "python": "python",
            "go": "go",
            "java": "java",
            "cpp": "cpp", "cc": "cpp", "cxx": "cpp", "h": "cpp", "hpp": "cpp",
            "rs": "rust",
            "php": "php",
            "rb": "ruby", "ruby": "ruby",
            "cs": "c_sharp", "csharp": "c_sharp",
            "js": "javascript", "javascript": "javascript",
            "ts": "typescript", "typescript": "typescript", "tsx": "typescript"
        }
        self._initialized = False

    def _initialize(self):
        """Lazy initialization of all parsers."""
        if self._initialized:
            return

        def load_parser(lang_module, lang_name, extensions, func_name="language"):
            try:
                lang_func = getattr(lang_module, func_name)
                LANG = Language(lang_func())
                parser = Parser(LANG)
                for ext in extensions:
                    self.parsers[ext] = (parser, LANG)
                self.languages[lang_name] = LANG
            except Exception as e:
                logger.warning(f"Failed to load {lang_name} parser: {e}")

        # Python
        load_parser(tree_sitter_python, "python", ["py", "python"])
        # Go
        load_parser(tree_sitter_go, "go", ["go"])
        # Java
        load_parser(tree_sitter_java, "java", ["java"])
        # C++
        load_parser(tree_sitter_cpp, "cpp", ["cpp", "cc", "cxx", "h", "hpp"])
        # Rust
        load_parser(tree_sitter_rust, "rust", ["rs"])
        # PHP
        load_parser(tree_sitter_php, "php", ["php"], func_name="language_php")
        # Ruby
        load_parser(tree_sitter_ruby, "ruby", ["rb", "ruby"])

        # C#
        load_parser(tree_sitter_c_sharp, "c_sharp", ["cs", "csharp"])

        # JavaScript
        load_parser(tree_sitter_javascript, "javascript", ["js", "javascript"])

        # TypeScript
        # Note: generic typescript binding usually has 'language_typescript' and 'language_tsx'
        try:
            ts_lang = tree_sitter_typescript.language_typescript()
            ts_parser = Parser(Language(ts_lang))
            self.parsers["ts"] = (ts_parser, Language(ts_lang))
            self.parsers["typescript"] = (ts_parser, Language(ts_lang))
            self.languages["typescript"] = Language(ts_lang)

            tsx_lang = tree_sitter_typescript.language_tsx()
            tsx_parser = Parser(Language(tsx_lang))
            self.parsers["tsx"] = (tsx_parser, Language(tsx_lang))
        except Exception as e:
             logger.warning(f"Failed to load TypeScript parser: {e}")

        self._initialized = True

    def get_parser(self, extension: str) -> tuple[Parser, Language] | None:
        """
        Get (Parser, Language) tuple for a file extension.
        Extension should be without dot (e.g. 'py').
        """
        self._initialize()
        return self.parsers.get(extension.lower())

    def get_language_key(self, extension: str) -> str | None:
        """
        Get generic language key (e.g. 'python') for an extension.
        """
        return self.lang_map.get(extension.lower())


# Global Instance
parser_registry = ParserRegistry()
