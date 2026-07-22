"""Language-agnostic entity grouping for AppMap generation.

The grouper classifies indexed SourceFile records by path conventions and
groups them into domain entities (e.g. ``OrderController`` + ``OrderService``
+ ``OrderModel`` → ``order``).  It does **not** write AppMap records — it only
produces a grouping dict for the AppMap Agent to consume.

Use ``EntityGrouper().get_entity_groups(repo_id, session)`` to get the groups.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.codebase import SourceFile

from .llm_classifier import classify_files_with_llm

logger = logging.getLogger(__name__)

USE_LLM_CLASSIFICATION = True
MAX_UNKNOWN_FILES_FOR_LLM = 20

SKIP_TOP_DIRS = {
    "vendor",
    "node_modules",
    ".git",
    ".github",
    ".evoloop",
    "dist",
    "build",
    "out",
    "coverage",
    "htmlcov",
    "tmp",
    "temp",
    "logs",
    "cache",
    "uploads",
    "static",
    "public",
}

CATEGORY_PATH_KEYWORDS: dict[str, list[str]] = {
    "controller": ["controller", "controllers", "endpoint", "endpoints"],
    "model": ["model", "models", "entity", "entities", "bean", "beans", "domain", "po", "dto", "vo", "bo"],
    "service": ["service", "services", "business", "usecase", "use_case", "use-case", "application", "applications"],
    "repository": ["repository", "repositories", "dao", "mapper", "mappers", "data_access"],
    "view": ["view", "views", "template", "templates", "component", "components", "page", "pages", "ui", "widget", "widgets"],
    "config": ["config", "configs", "configuration", "settings", "constant", "constants", "env"],
    "route": ["route", "routes", "router", "routers", "url", "urls"],
    "middleware": ["middleware", "middlewares", "filter", "filters", "interceptor", "interceptors", "guard", "guards"],
    "test": ["test", "tests", "spec", "specs", "__tests__", "e2e", "fixture", "fixtures"],
    "library": ["lib", "libs", "utils", "util", "common", "helpers", "helper", "shared", "tools", "tool", "extend", "extends"],
    "schema": ["migration", "migrations", "schema", "ddl", "sql"],
    "asset": ["assets", "images", "img", "css", "js", "fonts", "media"],
    "third_party": ["vendor", "third_party", "thirdparty", "deps", "externals"],
}

CATEGORY_FILE_SUFFIXES: dict[str, list[str]] = {
    "controller": ["controller", "controllers"],
    "model": ["model", "models", "entity", "entities", "bean", "beans"],
    "service": ["service", "services", "usecase", "use_case", "usecase"],
    "repository": ["repository", "repositories", "dao", "mapper", "mappers"],
    "view": ["view", "views", "template", "templates", "component", "components", "page", "pages"],
    "config": ["config", "configs", "configuration", "settings", "constant", "constants"],
    "route": ["route", "routes", "router", "routers"],
    "middleware": ["middleware", "middlewares", "filter", "filters", "interceptor", "interceptors"],
    "test": ["test", "tests", "spec", "specs"],
    "entry_point": ["main", "index", "app", "server", "application", "bootstrap"],
}

CATEGORY_LAYER = {
    "controller": ("entry_point", "ui"),
    "route": ("entry_point", "ui"),
    "entry_point": ("entry_point", "ui"),
    "model": ("data", "data"),
    "repository": ("data", "data"),
    "service": ("business_logic", "business"),
    "view": ("presentation", "ui"),
    "config": ("infrastructure", "system"),
    "middleware": ("infrastructure", "system"),
    "library": ("shared", "business"),
    "schema": ("data", "data"),
    "test": ("test", "system"),
    "asset": ("asset", "ui"),
    "third_party": ("third_party", "system"),
    "unknown": ("unknown", "system"),
}

_ENTITY_SUFFIXES = [
    "controller", "controllers", "service", "services",
    "repository", "repositories", "dao", "mapper", "mappers",
    "model", "models", "entity", "entities", "bean", "beans",
    "validate", "validation", "validator", "logic",
    "action", "actions", "handler", "handlers",
    "impl", "implementation", "interface", "intf",
    "base", "abstract",
]

SKIP_APPMAP_DETAIL_CATEGORIES = {
    "service", "repository", "library", "config", "middleware",
    "test", "asset", "third_party", "schema", "unknown",
}

APPMAP_ACTION_CATEGORIES = {
    "controller",
}

# File extensions to exclude from controller classification
_FRONTEND_EXTS = {".vue", ".js", ".ts", ".jsx", ".tsx"}

_NON_CONTROLLER_STEMS = {
    "application", "app", "main", "bootstrap",
    "base", "abstract", "common",
    "util", "utils", "helper", "helpers",
}

_GENERIC_ENTITY_NAMES = {
    "base", "common", "index", "main", "app", "application",
    "default", "util", "utils", "helper", "helpers",
    "public", "home", "api", "web", "admin",
    "test", "tests", "config", "setup", "install",
    "abstract",
}

_MIN_DIRECTORY_MODULE_SIZE = 3


@dataclass
class ClassifiedFile:
    source_file: SourceFile
    category: str
    layer: str
    risk_tier: str
    is_entry_point: bool = False
    children: list[ClassifiedFile] = field(default_factory=list)


class EntityGrouper:
    """Classify indexed source files and group them by domain entity.

    This is the first stage of the AppMap pipeline.  It produces entity groups
    (e.g. ``order`` → [OrderController, OrderService, OrderModel]) that the
    AppMap Agent then turns into complete five-layer AppMap records.

    No database mutations happen in this stage.
    """

    async def get_entity_groups(
        self, repo_id: int, session: AsyncSession
    ) -> dict[str, list[ClassifiedFile]]:
        """Return ``{entity_name: [ClassifiedFile, ...]}`` for *repo_id*.

        The result is ready for the AppMap Agent to iterate over.
        """
        source_files = await self._fetch_source_files(session, repo_id)
        if not source_files:
            return {}

        tree = self._build_file_tree(source_files)
        classified = self._classify_tree(tree)
        modules = self._group_by_module(classified)

        logger.info(
            "[EntityGrouper] Grouped %d source files into %d entity groups",
            len(source_files),
            len(modules),
        )
        return modules

    async def _fetch_source_files(
        self, session: AsyncSession, repo_id: int
    ) -> list[SourceFile]:
        stmt = (
            select(SourceFile)
            .where(SourceFile.repository_id == repo_id)
            .order_by(SourceFile.path)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    def _build_file_tree(self, source_files: list[SourceFile]) -> dict[str, Any]:
        tree: dict[str, Any] = {"type": "root", "name": "", "children": {}, "files": []}
        for sf in source_files:
            parts = [p for p in sf.path.split("/") if p]
            if not parts:
                tree["files"].append(sf)
                continue
            node = tree
            for part in parts[:-1]:
                if part not in node["children"]:
                    node["children"][part] = {
                        "type": "directory",
                        "name": part,
                        "children": {},
                        "files": [],
                    }
                node = node["children"][part]
            node["files"].append(sf)
        return tree

    def _classify_tree(self, tree: dict[str, Any]) -> ClassifiedFile:
        return self._classify_node(tree, current_path="", parent_category=None)

    def _classify_node(
        self, node: dict[str, Any], current_path: str, parent_category: str | None
    ) -> ClassifiedFile:
        name = node.get("name", "")
        node_type = node.get("type", "directory")
        node_path = current_path if not name else f"{current_path}/{name}".strip("/")

        dir_category = self._category_from_path(name)
        category = dir_category or parent_category or "unknown"
        layer, risk_tier = CATEGORY_LAYER.get(category, ("unknown", "system"))

        children: list[ClassifiedFile] = []
        for child_node in node.get("children", {}).values():
            children.append(self._classify_node(child_node, node_path, category))

        files: list[SourceFile] = node.get("files", [])
        classified_files: list[ClassifiedFile] = []
        for sf in files:
            file_category = self._classify_file(sf.path, category)
            file_layer, file_risk = CATEGORY_LAYER.get(
                file_category, ("unknown", "system")
            )
            classified_files.append(
                ClassifiedFile(
                    source_file=sf,
                    category=file_category,
                    layer=file_layer,
                    risk_tier=file_risk,
                    is_entry_point=file_category in {"controller", "route", "entry_point"},
                )
            )

        children.extend(classified_files)

        return ClassifiedFile(
            source_file=SourceFile(id=0, repository_id=0, path=node_path, checksum=""),
            category=category,
            layer=layer,
            risk_tier=risk_tier,
            children=children,
        )

    def _classify_file(self, path: str, parent_category: str | None) -> str:
        path_lower = path.lower()
        for cat, keywords in CATEGORY_PATH_KEYWORDS.items():
            for kw in keywords:
                if f"/{kw}/" in f"/{path_lower}/":
                    return cat
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        for cat, suffixes in CATEGORY_FILE_SUFFIXES.items():
            for suffix in suffixes:
                if stem.endswith(suffix):
                    return cat
        return parent_category or "unknown"

    def _category_from_path(self, name: str) -> str | None:
        if not name:
            return None
        name_lower = name.lower()
        for cat, keywords in CATEGORY_PATH_KEYWORDS.items():
            if name_lower in keywords:
                return cat
        return None

    def _flatten_files(self, node: ClassifiedFile) -> list[ClassifiedFile]:
        result = []
        if node.source_file and node.source_file.id:
            result.append(node)
        for c in node.children:
            result.extend(self._flatten_files(c))
        return result

    def _extract_entity(
        self, path: str, category: str | None = None
    ) -> str | None:
        filename = os.path.basename(path)
        stem, _ = os.path.splitext(filename)
        lower_stem = stem.lower()

        for suffix in _ENTITY_SUFFIXES:
            suffix_lower = suffix.lower()
            if lower_stem.endswith(suffix_lower):
                entity = lower_stem[: -len(suffix_lower)].rstrip("_-")
                if entity and entity not in _GENERIC_ENTITY_NAMES:
                    return entity
                break

        if category in {
            "controller", "service", "model", "repository",
            "mapper", "dao", "route", "entity",
        }:
            if lower_stem not in _GENERIC_ENTITY_NAMES:
                return lower_stem

        return None

    def _group_by_module(
        self, classified_root: ClassifiedFile
    ) -> dict[str, list[ClassifiedFile]]:
        all_files = self._flatten_files(classified_root)

        def _is_interesting(cf: ClassifiedFile) -> bool:
            if cf.category in {"test", "asset", "third_party"}:
                return False
            path = cf.source_file.path
            for skip in SKIP_TOP_DIRS:
                if path == skip or path.startswith(f"{skip}/"):
                    return False
            return bool(cf.source_file.path)

        filtered_files = [f for f in all_files if _is_interesting(f)]

        entity_modules: dict[str, list[ClassifiedFile]] = defaultdict(list)
        dir_modules: dict[str, list[ClassifiedFile]] = defaultdict(list)

        for cf in filtered_files:
            entity = self._extract_entity(cf.source_file.path, cf.category)
            if entity:
                entity_modules[entity].append(cf)
            else:
                module_name = self._module_name(cf.source_file.path)
                dir_modules[module_name].append(cf)

        if dir_modules:
            meaningful: dict[str, list[ClassifiedFile]] = {}
            shared: list[ClassifiedFile] = []
            for name, files in dir_modules.items():
                if len(files) >= _MIN_DIRECTORY_MODULE_SIZE:
                    meaningful[name] = files
                else:
                    shared.extend(files)
            if shared:
                meaningful.setdefault("shared", []).extend(shared)
            dir_modules = meaningful

        merged: dict[str, list[ClassifiedFile]] = {}
        merged.update(dir_modules)
        merged.update(entity_modules)

        if not merged:
            return {"root": filtered_files or all_files}

        return merged

    def _module_name(self, path: str) -> str:
        top = path.split("/")[0]
        return top.lower()
