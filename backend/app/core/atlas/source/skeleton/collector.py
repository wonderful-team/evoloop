#!/usr/bin/env python3
"""AppMap Collector Script — reference template.

Usage:
    python collect_appmaps.py /path/to/project --sql b2c_mall.sql

Output JSON to /tmp/appmap_extracted.json.  STDOUT is minimal (one summary
line) so the Agent can read it without truncation.

Customisation
=============
Update FRAMEWORK config below to match your project:
  - controller_dirs : directories containing controller files
  - view_dirs       : directories containing HTML view files
  - sql_path        : relative path to the SQL schema file
  - entity_re       : regex to extract entity name from controller filename
  - route_pattern   : how to build URLs from controller + method

The script is framework-agnostic — adapt the config, not the logic.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

# ═══════════════════════════════════════════════════════════
# FRAMEWORK CONFIG  —  edit these for your project
# ═══════════════════════════════════════════════════════════

CONTROLLER_DIRS = [
    "app/*/controller",
    "app/*api*/controller",
    "addon/*/controller",
    "addon/*/*/controller",
]

VIEW_DIRS = [
    "app/*/view",
    "addon/*/view",
    "addon/*/*/view",
]

SQL_PATH = "b2c_mall.sql"  # relative to project root, or None

# Extract entity name from controller filename.
# Default: "GoodsController.php" → "goods", "Member.php" → "member"
ENTITY_RE = re.compile(r"^(.*?)(?:Controller)?(?:\..*)?$", re.IGNORECASE)

# Build route URL from entity + action name.
# ThinkPHP convention: /{module}/{controller}/{action}
ROUTE_TEMPLATE = "/{entity}/{action}"

# Regex patterns for action methods in controller files
ACTION_METHOD_RE = re.compile(
    r"^\s*(?:public\s+)?function\s+(\w+)\s*[\(]"
)

# Regex patterns for HTML element selectors
HTML_ELEMENT_RE = re.compile(
    r'<input[^>]*?\s+(?:id|name|lay-filter)\s*=\s*["\']([^"\']+)["\']'
    r'|<select[^>]*?\s+(?:id|name|lay-filter)\s*=\s*["\']([^"\']+)["\']'
    r'|<textarea[^>]*?\s+(?:id|name|lay-filter)\s*=\s*["\']([^"\']+)["\']'
    r'|<button[^>]*?\s+(?:id|name|lay-filter)\s*=\s*["\']([^"\']+)["\']'
    r'|<a[^>]*?\s+(?:id|name|lay-filter)\s*=\s*["\']([^"\']+)["\']'
    r'|<form[^>]*?\s+(?:id|name|lay-filter)\s*=\s*["\']([^"\']+)["\']'
    r'|<table[^>]*?\s+(?:id|name|lay-filter)\s*=\s*["\']([^"\']+)["\']'
    r'|<div[^>]*?\s+(?:id|name|lay-filter)\s*=\s*["\']([^"\']+)["\']'
    r'|<span[^>]*?\s+(?:id|name|lay-filter)\s*=\s*["\']([^"\']+)["\']'
)

# Infer selector_type from HTML attribute
SELECTOR_TYPES = {
    "id": "id",
    "name": "name",
    "lay-filter": "lay-filter",
}

# Business terms for risk_tier heuristics
MONEY_KEYWORDS = ["price", "stock", "balance", "refund", "amount", "money",
                  "salary", "payment", "withdraw", "recharge"]
DATA_KEYWORDS = ["save", "update", "delete", "remove", "create", "add", "edit",
                 "set", "change", "status"]

# ═══════════════════════════════════════════════════════════
# COLLECTOR LOGIC  —  normally does not need editing
# ═══════════════════════════════════════════════════════════


def find_files(root: str, patterns: list[str]) -> list[str]:
    """Glob-like file finder (no external dependency)."""
    results = []
    for pat in patterns:
        parts = pat.split("/")
        # Resolve wildcards via os.walk
        base = root
        for i, part in enumerate(parts):
            if "*" in part:
                # Walk current base for matching dirs
                try:
                    entries = os.listdir(base)
                except OSError:
                    continue
                for e in entries:
                    child = os.path.join(base, e)
                    if not os.path.isdir(child):
                        continue
                    if re.match(f"^{part.replace('*', '.*')}$", e, re.I):
                        suffix = "/".join(parts[i + 1:])
                        if suffix:
                            results.extend(find_files(child, [suffix]))
                        else:
                            results.append(child)
                return results
            else:
                base = os.path.join(base, part)
                if not os.path.isdir(base):
                    return results
        results.append(base)
    return results


def extract_actions(filepath: str, entity: str) -> list[dict]:
    """Extract action methods from a controller file."""
    actions = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return actions

    for lineno, line in enumerate(lines, 1):
        m = ACTION_METHOD_RE.search(line)
        if m:
            name = m.group(1)
            if name.startswith("_"):
                continue  # skip private/protected
            if name in ("__construct", "__destruct", "__init"):
                continue

            kind = "write"
            risk = "ui"
            lower = name.lower()
            if any(kw in lower for kw in MONEY_KEYWORDS):
                kind = "write"
                risk = "money"
            elif any(kw in lower for kw in ("list", "page", "index", "get", "search", "find")):
                kind = "read"
            elif any(kw in lower for kw in DATA_KEYWORDS):
                kind = "write"
                risk = "data"

            actions.append({
                "name": name,
                "kind": kind,
                "risk_tier": risk,
                "business_rule": "",
                "controller": filepath,
                "line": lineno,
                "touches_tables": [],
                "set_fields": [],
                "pk": "",
            })
    return actions


def extract_elements(filepath: str) -> list[dict]:
    """Extract UI element symbols from an HTML view file."""
    elements = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return elements

    seen = set()
    for match in HTML_ELEMENT_RE.finditer(content):
        name = next(g for g in match.groups() if g)
        if name in seen:
            continue
        seen.add(name)

        # Determine selector_type from the matched attribute
        attr = match.group(0)
        selector_type = "id"
        if 'name=' in attr:
            selector_type = "name"
        elif 'lay-filter=' in attr:
            selector_type = "lay-filter"

        # Count line number (approximate by counting newlines before match)
        line = content[:match.start()].count("\n") + 1

        elements.append({
            "name": name,
            "page": filepath,
            "line": line,
            "binds": "",
            "selector_type": selector_type,
        })
    return elements


def parse_schema(sql_path: str) -> dict[str, dict]:
    """Parse CREATE TABLE statements from a SQL file."""
    tables = {}
    try:
        with open(sql_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return tables

    # Find each CREATE TABLE block
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\(",
        re.IGNORECASE,
    )
    for m in pattern.finditer(content):
        table_name = m.group(1)
        # Extract column names from the block
        block_start = m.end()
        depth = 1
        pos = block_start
        while depth > 0 and pos < len(content):
            if content[pos] == "(":
                depth += 1
            elif content[pos] == ")":
                depth -= 1
            pos += 1
        block = content[block_start: pos - 1]

        cols = []
        pk = ""
        for line in block.split("\n"):
            line = line.strip().rstrip(",")
            # Skip constraints, keys, indexes
            if not line or line.startswith(("KEY", "INDEX", "CONSTRAINT", "UNIQUE", "PRIMARY", "FOREIGN", ")")):
                if "PRIMARY KEY" in line.upper():
                    pk_match = re.search(r"`(\w+)`", line)
                    if pk_match:
                        pk = pk_match.group(1)
                continue
            col_match = re.match(r"`?(\w+)`?\s", line)
            if col_match:
                cols.append(col_match.group(1))

        tables[table_name] = {
            "table": table_name,
            "pk": pk,
            "cols": cols,
        }
    return tables


def build_routes(entity: str, actions: list[dict]) -> list[dict]:
    """Build route entries from entity + actions."""
    routes = []
    for a in actions:
        url = ROUTE_TEMPLATE.format(entity=entity, action=a["name"])
        method = "GET" if a["kind"] == "read" else "POST"
        routes.append({
            "name": f"{entity}_{a['name']}",
            "url": url,
            "method": method,
            "source_action": a["name"],
        })
    return routes


def guess_entity(filepath: str) -> str | None:
    """Guess entity name from controller file path."""
    basename = os.path.splitext(os.path.basename(filepath))[0]
    m = ENTITY_RE.match(basename)
    if m:
        entity = m.group(1).lower()
        if entity and entity not in {
            "base", "common", "index", "main", "app", "default",
            "util", "helper", "public", "home", "api", "admin",
            "test", "config", "setup", "install", "abstract",
        }:
            return entity
    return None


async def collect(project_root: str, sql_path: str | None = None, output_path: str = "/tmp/appmap_extracted.json") -> dict:
    """Run the full collection and return the entities dict.

    Framework-agnostic: configure FRAMEWORK CONFIG at the top of this file
    to match your project conventions.
    """
    if not sql_path:
        candidate = os.path.join(project_root, SQL_PATH) if SQL_PATH else None
        if candidate and os.path.isfile(candidate):
            sql_path = candidate

    # 1. Find all controller files
    controller_files = []
    for d in find_files(project_root, CONTROLLER_DIRS):
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith((".php", ".py", ".java", ".ts", ".js", ".go", ".rb")):
                    controller_files.append(os.path.join(d, f))

    # 2. Find all view files
    view_files = []
    for d in find_files(project_root, VIEW_DIRS):
        if os.path.isdir(d):
            for sub in sorted(os.listdir(d)):
                subdir = os.path.join(d, sub)
                if os.path.isdir(subdir):
                    for f in os.listdir(subdir):
                        if f.endswith((".html", ".htm", ".vue", ".jsp", ".ftl", ".blade.php")):
                            view_files.append(os.path.join(subdir, f))

    # 3. Parse SQL schema
    schema_tables = {}
    if sql_path and os.path.isfile(sql_path):
        schema_tables = parse_schema(sql_path)

    # 4. Group by entity
    entities: dict[str, dict] = {}

    for cf in controller_files:
        entity = guess_entity(cf)
        if not entity:
            continue
        if entity not in entities:
            entities[entity] = {
                "aliases": [entity],
                "platform": "web",
                "routes": [],
                "actions": [],
                "elements": [],
                "db_tables": [],
                "extra": {},
            }
        actions = extract_actions(cf, entity)
        entities[entity]["actions"].extend(actions)
        entities[entity]["routes"].extend(build_routes(entity, actions))

    # Attach view elements to entities based on view directory structure.
    for vf in view_files:
        parts = vf.replace(project_root, "").lstrip("/").split("/")
        view_entity = None
        for i, p in enumerate(parts):
            if p.lower() in ("view", "views") and i + 1 < len(parts):
                candidate = parts[i + 1].lower()
                if candidate in entities:
                    view_entity = candidate
                elif candidate.rstrip("s") in entities:
                    view_entity = candidate.rstrip("s")
                break
        if view_entity:
            elements = extract_elements(vf)
            entities[view_entity]["elements"].extend(elements)

    # Attach schema tables to entities
    for tname, tdata in schema_tables.items():
        t_clean = tname.lower().replace("_", "").replace("-", "")
        for ename in entities:
            e_clean = ename.lower().replace("_", "").replace("-", "")
            if t_clean.startswith(e_clean) or e_clean.startswith(t_clean):
                entities[ename]["db_tables"].append(tdata)
                for a in entities[ename]["actions"]:
                    if tname not in a["touches_tables"]:
                        a["touches_tables"].append(tname)
                break

    # Set fields from element × DB column intersection
    db_cols_by_entity = {}
    for ename, edata in entities.items():
        cols = set()
        pk = ""
        for t in edata.get("db_tables", []):
            for c in t.get("cols", []):
                cols.add(c)
            if t.get("table") == ename and t.get("pk"):
                pk = t["pk"]
        db_cols_by_entity[ename] = (cols, pk)

    for ename, edata in entities.items():
        db_cols, pk = db_cols_by_entity.get(ename, (set(), ""))
        if not db_cols:
            continue
        el_names = {el.get("name", "").lower() for el in edata.get("elements", [])}
        common = db_cols & el_names
        if not common:
            continue
        for a in edata["actions"]:
            if a["kind"] == "write" and not a.get("set_fields"):
                a["set_fields"] = sorted(c for c in common if c != pk)
                if pk and pk in common:
                    a["pk"] = pk

    # Remove empty entities
    empty = [e for e, d in entities.items()
             if not d.get("actions") and not d.get("routes") and not d.get("db_tables")]
    for e in empty:
        del entities[e]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)

    return entities


def main():
    if len(sys.argv) < 2:
        print("Usage: collect_appmaps.py <project_root> [--sql <sql_path>]")
        sys.exit(1)

    root = sys.argv[1]
    sql_path = None
    if "--sql" in sys.argv:
        idx = sys.argv.index("--sql")
        sql_path = os.path.join(root, sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else None

    entities = asyncio.run(collect(project_root=root, sql_path=sql_path))

    total_actions = sum(len(e["actions"]) for e in entities.values())
    total_elements = sum(len(e["elements"]) for e in entities.values())
    total_routes = sum(len(e["routes"]) for e in entities.values())
    total_tables = sum(len(e["db_tables"]) for e in entities.values())

    print(
        f"✅ Collected {len(entities)} entities, "
        f"{total_actions} actions, {total_elements} elements, "
        f"{total_routes} routes, {total_tables} db_tables "
        f"→ /tmp/appmap_extracted.json"
    )


if __name__ == "__main__":
    main()
